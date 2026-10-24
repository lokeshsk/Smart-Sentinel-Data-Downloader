"""
Robust, resumable download engine for CDSE products and selective assets.
"""

import hashlib
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Optional

import requests
from tqdm import tqdm

from smart_sentinel.client import CDSEClient
from smart_sentinel.config import (
    DEFAULT_BACKOFF_429,
    DEFAULT_CHUNK_MB,
    DEFAULT_DOWNLOAD_DIR,
    DEFAULT_RETRIES,
    DEFAULT_TIMEOUT,
    DEFAULT_WORKERS,
    ZIPPER_URL,
)
from smart_sentinel.models import DownloadResult

logger = logging.getLogger(__name__)


class DownloadError(Exception):
    """Raised when a download fails permanently."""


class Downloader:
    """Manages high-throughput, resumable downloads of full ZIPs and individual bands."""

    def __init__(
        self,
        client: Optional[CDSEClient] = None,
        download_dir: Optional[Path] = None,
        workers: int = DEFAULT_WORKERS,
        chunk_mb: int = DEFAULT_CHUNK_MB,
        retries: int = DEFAULT_RETRIES,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        self.client = client or CDSEClient()
        self.download_dir = Path(download_dir or DEFAULT_DOWNLOAD_DIR)
        self.workers = workers
        self.chunk_size = chunk_mb * 1024 * 1024
        self.retries = retries
        self.timeout = timeout
        self.download_dir.mkdir(parents=True, exist_ok=True)

    def _verify_file_hash(self, file_path: Path, expected_hash: str, algorithm: str = "MD5") -> bool:
        """Computes and compares the cryptographic hash of a local file."""
        hasher = hashlib.md5() if algorithm.upper() == "MD5" else hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                hasher.update(chunk)
        calculated = hasher.hexdigest().lower()
        return calculated == expected_hash.lower()

    def download_url_to_file(
        self,
        url: str,
        destination: Path,
        expected_size: int = 0,
        expected_checksum: Optional[str] = None,
        checksum_algorithm: str = "MD5",
        resume: bool = True,
        progress_desc: Optional[str] = None,
        verify_checksum: bool = True,
    ) -> Path:
        """
        Downloads a stream from a URL into an atomic destination file with HTTP Range resume support.
        """
        destination.parent.mkdir(parents=True, exist_ok=True)
        part_file = destination.with_suffix(destination.suffix + ".part")

        # Check if completed destination already exists and is valid
        if destination.exists():
            current_size = destination.stat().st_size
            if expected_size > 0 and current_size == expected_size:
                if expected_checksum and verify_checksum:
                    if self._verify_file_hash(destination, expected_checksum, checksum_algorithm):
                        logger.info(f"File exists with matching checksum: {destination.name}")
                        return destination
                else:
                    logger.info(f"File exists with matching size: {destination.name}")
                    return destination

        downloaded_bytes = 0
        if resume and part_file.exists():
            downloaded_bytes = part_file.stat().st_size
            if expected_size > 0 and downloaded_bytes > expected_size:
                # Corrupted part file that exceeds expected size; reset
                part_file.unlink()
                downloaded_bytes = 0

        for attempt in range(1, self.retries + 1):
            token = self.client.auth.get_token()
            headers = {"Authorization": f"Bearer {token}"}

            if resume and downloaded_bytes > 0:
                headers["Range"] = f"bytes={downloaded_bytes}-"

            try:
                with requests.get(url, headers=headers, stream=True, timeout=self.timeout) as resp:
                    if resp.status_code in (401, 403):
                        logger.warning("Auth token expired, refreshing...")
                        self.client.auth.get_token(force_refresh=True)
                        time.sleep(1)
                        continue

                    if resp.status_code == 429:
                        logger.warning(f"Rate limited (429). Backing off for {DEFAULT_BACKOFF_429}s...")
                        time.sleep(DEFAULT_BACKOFF_429)
                        continue

                    if resp.status_code == 416:  # Range Not Satisfiable
                        if part_file.exists() and expected_size > 0 and part_file.stat().st_size == expected_size:
                            break
                        # Reset and retry from 0
                        part_file.unlink(missing_ok=True)
                        downloaded_bytes = 0
                        continue

                    resp.raise_for_status()

                    mode = "ab" if (resp.status_code == 206 and downloaded_bytes > 0) else "wb"
                    if mode == "wb":
                        downloaded_bytes = 0

                    total_size = expected_size or int(resp.headers.get("Content-Length", 0)) + downloaded_bytes
                    desc = (progress_desc or destination.name)[:40]

                    with open(part_file, mode) as f, tqdm(
                        desc=desc,
                        total=total_size,
                        initial=downloaded_bytes,
                        unit="B",
                        unit_scale=True,
                        unit_divisor=1024,
                        leave=False,
                    ) as bar:
                        for chunk in resp.iter_content(chunk_size=self.chunk_size):
                            if chunk:
                                f.write(chunk)
                                bar.update(len(chunk))

                # Validate downloaded part file
                final_size = part_file.stat().st_size
                if expected_size > 0 and final_size != expected_size:
                    raise DownloadError(f"Size mismatch: got {final_size} bytes, expected {expected_size}")

                if expected_checksum and verify_checksum:
                    if not self._verify_file_hash(part_file, expected_checksum, checksum_algorithm):
                        part_file.unlink(missing_ok=True)
                        raise DownloadError(f"Checksum mismatch for {destination.name}")

                # Atomic replace
                os.replace(part_file, destination)
                logger.info(f"✓ Downloaded: {destination.name}")
                return destination

            except (requests.exceptions.RequestException, DownloadError) as exc:
                logger.warning(f"[Attempt {attempt}/{self.retries}] Error downloading {destination.name}: {exc}")
                if attempt == self.retries:
                    raise DownloadError(f"Failed to download {destination.name} after {self.retries} attempts: {exc}")
                time.sleep(2 * attempt)
                if part_file.exists():
                    downloaded_bytes = part_file.stat().st_size

        raise DownloadError(f"Download failed for {destination.name}")

    def download_product_zip(
        self,
        product_id_or_name: str,
        output_dir: Optional[Path] = None,
        verify_checksum: bool = True,
    ) -> DownloadResult:
        """
        Downloads a full Sentinel product as a .zip archive using the CDSE Zipper service.
        """
        product = self.client.get_product(product_id_or_name)
        target_dir = Path(output_dir or self.download_dir) / product.mission
        target_dir.mkdir(parents=True, exist_ok=True)

        zip_filename = f"{product.name}.zip"
        dest_path = target_dir / zip_filename
        download_url = f"{ZIPPER_URL}/Products({product.id})/$value"

        try:
            saved_path = self.download_url_to_file(
                url=download_url,
                destination=dest_path,
                expected_size=product.content_length,
                expected_checksum=product.checksum,
                checksum_algorithm=product.checksum_algorithm or "MD5",
                progress_desc=zip_filename,
                verify_checksum=verify_checksum,
            )
            return DownloadResult(
                product_id=product.id,
                filename=zip_filename,
                output_path=str(saved_path),
                bytes_downloaded=saved_path.stat().st_size,
                status="SUCCESS",
            )
        except Exception as exc:
            logger.error(f"Failed to download product ZIP {product.name}: {exc}")
            return DownloadResult(
                product_id=product.id,
                filename=zip_filename,
                status="FAILED",
                error_message=str(exc),
            )

    def download_selective_bands(
        self,
        product_id_or_name: str,
        bands: Optional[str] = None,
        output_dir: Optional[Path] = None,
        verify_checksum: bool = True,
        composite: Optional[str] = None,
    ) -> List[DownloadResult]:
        """
        Downloads only the specific band files matching criteria without downloading the full SAFE zip.
        Optionally generates an RGB, FalseColor, or SWIR GeoTIFF composite.
        """
        product = self.client.get_product(product_id_or_name)

        # Auto-expand bands if a composite type was requested without explicit bands
        if composite and not bands:
            comp_lower = composite.lower()
            if comp_lower in ("rgb", "true-color"):
                bands = "B04,B03,B02"
            elif comp_lower in ("false-color", "cir"):
                bands = "B08,B04,B03"
            elif comp_lower in ("swir", "geology"):
                bands = "B12,B8A,B04"

        target_files = self.client.find_files_for_bands(product, requested_bands=bands)

        if not target_files:
            logger.warning(f"No matching files found in product {product.name} for bands: {bands}")
            return []

        target_dir = Path(output_dir or self.download_dir) / product.mission / product.name
        target_dir.mkdir(parents=True, exist_ok=True)

        results: List[DownloadResult] = []
        for pfile in target_files:
            dest_path = target_dir / pfile.name
            try:
                saved_path = self.download_url_to_file(
                    url=pfile.download_url,
                    destination=dest_path,
                    expected_size=pfile.content_length,
                    expected_checksum=pfile.checksum,
                    checksum_algorithm=pfile.checksum_algorithm or "MD5",
                    progress_desc=pfile.name,
                    verify_checksum=verify_checksum,
                )
                results.append(
                    DownloadResult(
                        product_id=product.id,
                        filename=pfile.name,
                        output_path=str(saved_path),
                        bytes_downloaded=saved_path.stat().st_size,
                        status="SUCCESS",
                    )
                )
            except Exception as exc:
                logger.error(f"Failed downloading band file {pfile.name}: {exc}")
                results.append(
                    DownloadResult(
                        product_id=product.id,
                        filename=pfile.name,
                        status="FAILED",
                        error_message=str(exc),
                    )
                )

        # Generate composite if requested
        if composite and product.is_sentinel2:
            try:
                from smart_sentinel.processors import create_composite_from_downloaded
                composite_file = create_composite_from_downloaded(target_dir, composite_type=composite)
                if composite_file:
                    results.append(
                        DownloadResult(
                            product_id=product.id,
                            filename=composite_file.name,
                            output_path=str(composite_file),
                            bytes_downloaded=composite_file.stat().st_size,
                            status="SUCCESS",
                        )
                    )
            except Exception as exc:
                logger.warning(f"Could not generate {composite} composite: {exc}")

        return results

    def download_batch(
        self,
        product_ids: List[str],
        download_type: str = "selective",
        bands: Optional[str] = None,
        output_dir: Optional[Path] = None,
        verify_checksum: bool = True,
        composite: Optional[str] = None,
    ) -> List[DownloadResult]:
        """
        Downloads a batch of products concurrently across worker threads.
        """
        all_results: List[DownloadResult] = []

        def _task(pid: str):
            if download_type == "full":
                return [self.download_product_zip(pid, output_dir=output_dir, verify_checksum=verify_checksum)]
            else:
                return self.download_selective_bands(
                    pid,
                    bands=bands,
                    output_dir=output_dir,
                    verify_checksum=verify_checksum,
                    composite=composite,
                )

        logger.info(f"Starting batch download of {len(product_ids)} items with {self.workers} workers...")

        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            future_to_pid = {executor.submit(_task, pid): pid for pid in product_ids}
            for future in as_completed(future_to_pid):
                pid = future_to_pid[future]
                try:
                    res_list = future.result()
                    all_results.extend(res_list)
                except Exception as exc:
                    logger.error(f"Batch worker failed for {pid}: {exc}")
                    all_results.append(
                        DownloadResult(
                            product_id=pid,
                            filename="batch",
                            status="FAILED",
                            error_message=str(exc),
                        )
                    )

        return all_results
