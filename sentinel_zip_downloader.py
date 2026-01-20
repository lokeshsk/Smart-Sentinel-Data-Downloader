"""
Sentinel ZIP Downloader
Downloads complete Sentinel-1 and Sentinel-2 products as ZIP files from Copernicus Data Space Ecosystem.

Usage:
    python sentinel_zip_downloader.py ids.txt

Requirements:
    - .env file with SENTINEL_USER and SENTINEL_PASS credentials
    - ids.txt file with one product ID per line (UUIDs or product names)
"""

import os
import sys
import time
import logging
import threading
from queue import Queue
from pathlib import Path

import requests
from tqdm import tqdm
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Load credentials
load_dotenv()

SENTINEL_USER = os.getenv("SENTINEL_USER")
SENTINEL_PASS = os.getenv("SENTINEL_PASS")

if not SENTINEL_USER or not SENTINEL_PASS:
    logger.error("Missing credentials: set SENTINEL_USER and SENTINEL_PASS in .env")
    sys.exit(1)

# Configuration
CONFIG = {
    "workers": 10,
    "chunk_mb": 16,
    "max_retries": 3,
    "download_dir": "downloads",
    "timeout": 120,
    "backoff_429": 30,
    "token_refresh_seconds": 600,
}

# API endpoints
IDENTITY_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
CATALOGUE_URL = "https://catalogue.dataspace.copernicus.eu/odata/v1"
ZIPPER_URL = "https://zipper.dataspace.copernicus.eu/odata/v1"


class CDSEDownloader:
    """
    Copernicus Data Space Ecosystem ZIP downloader
    Supports both Sentinel-1 and Sentinel-2 products
    """

    def __init__(self, username, password):
        self.username = username
        self.password = password
        
        self.token = None
        self.token_timestamp = 0
        self.lock = threading.Lock()
        
        self.download_dir = Path(CONFIG["download_dir"])
        self.download_dir.mkdir(exist_ok=True)

    def get_token(self):
        """Get authentication token, refreshing if necessary"""
        with self.lock:
            if self.token and time.time() - self.token_timestamp < CONFIG["token_refresh_seconds"]:
                return self.token

            logger.debug("Requesting new authentication token")
            
            try:
                response = requests.post(
                    IDENTITY_URL,
                    data={
                        "grant_type": "password",
                        "username": self.username,
                        "password": self.password,
                        "client_id": "cdse-public",
                    },
                    timeout=30,
                )
                response.raise_for_status()
                
                self.token = response.json()["access_token"]
                self.token_timestamp = time.time()
                
                return self.token
                
            except requests.exceptions.RequestException as e:
                raise Exception(f"Authentication failed: {e}")

    def get_product_metadata(self, product_id):
        """Fetch product metadata from catalogue"""
        url = f"{CATALOGUE_URL}/Products({product_id})"
        headers = {"Authorization": f"Bearer {self.get_token()}"}
        
        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to fetch metadata for {product_id}: {e}")

    def _detect_mission(self, product_name):
        """Detect mission type from product name"""
        name_upper = product_name.upper()
        
        if name_upper.startswith("S1"):
            return "Sentinel-1"
        elif name_upper.startswith("S2"):
            return "Sentinel-2"
        else:
            return "Unknown"

    def download_product(self, product_id):
        """
        Download complete product as ZIP with resume support and retry logic
        Supports both Sentinel-1 and Sentinel-2
        """
        
        # Get product metadata
        try:
            metadata = self.get_product_metadata(product_id)
        except Exception as e:
            logger.error(f"Failed to get metadata: {e}")
            raise
        
        product_name = metadata.get("Name", product_id)
        file_size = metadata.get("ContentLength", 0)
        mission = self._detect_mission(product_name)
        
        # Create mission-specific subdirectory
        if mission == "Sentinel-1":
            output_dir = self.download_dir / "sentinel1"
        elif mission == "Sentinel-2":
            output_dir = self.download_dir / "sentinel2"
        else:
            output_dir = self.download_dir / "unknown"
        
        output_dir.mkdir(exist_ok=True)
        
        zip_filename = f"{product_name}.zip"
        output_path = output_dir / zip_filename
        
        logger.info(f"Downloading {mission} product: {product_name}")
        if file_size > 0:
            logger.info(f"Expected size: {file_size / 1024 / 1024 / 1024:.2f} GB")
        
        # Check existing download progress
        downloaded_bytes = 0
        if output_path.exists():
            downloaded_bytes = output_path.stat().st_size
            if file_size > 0 and downloaded_bytes == file_size:
                logger.info(f"File already exists with correct size: {zip_filename}")
                return str(output_path)
            elif downloaded_bytes > 0:
                logger.info(f"Resuming download from {downloaded_bytes / 1024 / 1024:.1f} MB")
        
        download_url = f"{ZIPPER_URL}/Products({product_id})/$value"
        
        # Retry loop
        for attempt in range(1, CONFIG["max_retries"] + 1):
            try:
                headers = {
                    "Authorization": f"Bearer {self.get_token()}",
                }
                
                # Add range header for resume
                if downloaded_bytes > 0:
                    headers["Range"] = f"bytes={downloaded_bytes}-"
                
                with requests.get(
                    download_url,
                    headers=headers,
                    stream=True,
                    timeout=CONFIG["timeout"],
                ) as response:
                    
                    # Handle authentication errors
                    if response.status_code in [401, 403]:
                        logger.warning("Authentication expired, refreshing token")
                        self.token = None
                        time.sleep(2)
                        continue
                    
                    # Handle rate limiting
                    if response.status_code == 429:
                        logger.warning(f"Rate limited, waiting {CONFIG['backoff_429']}s")
                        time.sleep(CONFIG["backoff_429"])
                        continue
                    
                    response.raise_for_status()
                    
                    # Open file in append or write mode
                    mode = "ab" if downloaded_bytes > 0 else "wb"
                    
                    chunk_size = CONFIG["chunk_mb"] * 1024 * 1024
                    
                    with open(output_path, mode) as f, tqdm(
                        desc=zip_filename[:50],
                        total=file_size,
                        initial=downloaded_bytes,
                        unit="B",
                        unit_scale=True,
                        unit_divisor=1024,
                    ) as progress_bar:
                        
                        for chunk in response.iter_content(chunk_size=chunk_size):
                            if chunk:
                                f.write(chunk)
                                progress_bar.update(len(chunk))
                
                # Verify file size
                final_size = output_path.stat().st_size
                
                if file_size > 0 and final_size != file_size:
                    logger.warning(f"Size mismatch: {final_size} != {file_size}")
                    downloaded_bytes = final_size
                    if attempt < CONFIG["max_retries"]:
                        logger.info(f"Retrying download (attempt {attempt + 1}/{CONFIG['max_retries']})")
                        time.sleep(5 * attempt)
                        continue
                    else:
                        raise Exception(f"Size mismatch after {CONFIG['max_retries']} attempts")
                
                logger.info(f"Successfully downloaded: {zip_filename}")
                return str(output_path)
                
            except requests.exceptions.RequestException as e:
                logger.error(f"Attempt {attempt}/{CONFIG['max_retries']} failed: {e}")
                
                if attempt < CONFIG["max_retries"]:
                    wait_time = 5 * attempt
                    logger.info(f"Waiting {wait_time}s before retry")
                    time.sleep(wait_time)
                    
                    # Update downloaded bytes for resume
                    if output_path.exists():
                        downloaded_bytes = output_path.stat().st_size
                else:
                    raise Exception(f"Download failed after {CONFIG['max_retries']} attempts: {e}")
            
            except Exception as e:
                logger.error(f"Unexpected error on attempt {attempt}: {e}")
                if attempt < CONFIG["max_retries"]:
                    time.sleep(5 * attempt)
                else:
                    raise
        
        raise Exception(f"Download failed after {CONFIG['max_retries']} attempts")


def download_worker(queue, downloader):
    """Worker thread for downloading products"""
    while True:
        product_id = queue.get()
        
        try:
            output_file = downloader.download_product(product_id)
            logger.info(f"✓ SUCCESS: {product_id} -> {output_file}")
            
        except Exception as e:
            logger.error(f"✗ FAILED: {product_id} - {e}")
        
        finally:
            queue.task_done()


def read_product_ids(filepath):
    """Read product IDs from text file"""
    try:
        with open(filepath, 'r') as f:
            ids = [
                line.strip() 
                for line in f 
                if line.strip() and not line.strip().startswith("#")
            ]
        
        if not ids:
            raise ValueError("No product IDs found in file")
        
        return ids
        
    except FileNotFoundError:
        logger.error(f"File not found: {filepath}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error reading file: {e}")
        sys.exit(1)


def main():
    """Main entry point"""
    if len(sys.argv) < 2:
        print("Usage: python sentinel_zip_downloader.py ids.txt")
        print("\nDownloads complete Sentinel-1 and Sentinel-2 products as ZIP files")
        print("Supports resume for interrupted downloads")
        sys.exit(1)
    
    ids_file = sys.argv[1]
    product_ids = read_product_ids(ids_file)
    
    logger.info("=" * 70)
    logger.info("Sentinel ZIP Downloader")
    logger.info("=" * 70)
    logger.info(f"Products to download: {len(product_ids)}")
    logger.info(f"Output directory: {CONFIG['download_dir']}")
    logger.info(f"Worker threads: {CONFIG['workers']}")
    logger.info(f"Chunk size: {CONFIG['chunk_mb']} MB")
    logger.info(f"Max retries: {CONFIG['max_retries']}")
    logger.info("=" * 70)
    
    # Initialize downloader
    downloader = CDSEDownloader(SENTINEL_USER, SENTINEL_PASS)
    
    # Create download queue and workers
    download_queue = Queue()
    
    for _ in range(CONFIG["workers"]):
        thread = threading.Thread(
            target=download_worker,
            args=(download_queue, downloader),
            daemon=True
        )
        thread.start()
    
    # Add products to queue
    for product_id in product_ids:
        download_queue.put(product_id)
    
    # Wait for completion
    download_queue.join()
    
    logger.info("=" * 70)
    logger.info("All downloads completed")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()