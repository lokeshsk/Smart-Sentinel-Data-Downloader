"""
Unit tests for geospatial post-processors: composite creation and NDVI.
"""

import pytest

from smart_sentinel.processors import (
    HAS_RASTERIO,
    check_rasterio_available,
    create_composite_from_downloaded,
)


def test_check_rasterio_available_behavior():
    """Verify behavior of rasterio check depending on environment."""
    if not HAS_RASTERIO:
        with pytest.raises(ImportError, match="smart-sentinel-downloader\\[geo\\]"):
            check_rasterio_available()
    else:
        # Should not raise
        check_rasterio_available()


def test_create_composite_from_downloaded_handles_missing_bands(tmp_path):
    """Verify graceful handling when required bands are missing from folder."""
    if not HAS_RASTERIO:
        pytest.skip("rasterio not installed")

    # Directory with no files
    result = create_composite_from_downloaded(tmp_path, composite_type="rgb")
    assert result is None
