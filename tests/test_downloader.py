"""
Unit tests for Downloader: resumable HTTP transfers, atomic writes, and checksum verification.
"""

import hashlib

import pytest
import responses

from smart_sentinel.downloader import Downloader, DownloadError


@responses.activate
def test_download_url_to_file_success(tmp_path, mock_client):
    """Verify clean file download, size validation, and atomic replace."""
    content = b"SATELLITE_BAND_DATA_BINARY_STREAM_12345"
    expected_md5 = hashlib.md5(content).hexdigest()
    download_url = "https://download.dataspace.copernicus.eu/odata/v1/Nodes(123)/$value"

    responses.add(
        responses.GET,
        download_url,
        body=content,
        status=200,
        headers={"Content-Length": str(len(content))},
    )

    downloader = Downloader(client=mock_client, download_dir=tmp_path)
    dest_file = tmp_path / "band.jp2"

    saved = downloader.download_url_to_file(
        url=download_url,
        destination=dest_file,
        expected_size=len(content),
        expected_checksum=expected_md5,
        verify_checksum=True,
    )

    assert saved.exists()
    assert saved.read_bytes() == content
    # Part file should be gone after atomic replace
    assert not (tmp_path / "band.jp2.part").exists()


@responses.activate
def test_download_resume_with_range_header(tmp_path, mock_client):
    """Verify resumed download when a partial .part file already exists."""
    initial_content = b"INITIAL_CHUNK_"
    remaining_content = b"REMAINING_CHUNK"
    full_content = initial_content + remaining_content

    dest_file = tmp_path / "scene.zip"
    part_file = tmp_path / "scene.zip.part"

    # Pre-write partial file
    part_file.write_bytes(initial_content)

    download_url = "https://zipper.dataspace.copernicus.eu/odata/v1/Products(999)/$value"

    def request_callback(request):
        # Verify Range header was sent
        assert "Range" in request.headers
        assert request.headers["Range"] == f"bytes={len(initial_content)}-"
        return (206, {"Content-Length": str(len(remaining_content))}, remaining_content)

    responses.add_callback(
        responses.GET,
        download_url,
        callback=request_callback,
    )

    downloader = Downloader(client=mock_client, download_dir=tmp_path)
    saved = downloader.download_url_to_file(
        url=download_url,
        destination=dest_file,
        expected_size=len(full_content),
        resume=True,
        verify_checksum=False,
    )

    assert saved.exists()
    assert saved.read_bytes() == full_content


@responses.activate
def test_checksum_mismatch_raises_error(tmp_path, mock_client):
    """Verify that a corrupted payload failing MD5 validation is rejected."""
    corrupted_content = b"CORRUPTED_BYTES"
    download_url = "https://download.dataspace.copernicus.eu/odata/v1/Nodes(bad)/$value"

    responses.add(
        responses.GET,
        download_url,
        body=corrupted_content,
        status=200,
    )

    downloader = Downloader(client=mock_client, download_dir=tmp_path, retries=1)
    dest_file = tmp_path / "test.tif"

    with pytest.raises(DownloadError, match="Checksum mismatch|Failed to download"):
        downloader.download_url_to_file(
            url=download_url,
            destination=dest_file,
            expected_size=len(corrupted_content),
            expected_checksum="incorrect_md5_hash_value",
            verify_checksum=True,
        )

    # Destination should not exist if corrupted
    assert not dest_file.exists()
