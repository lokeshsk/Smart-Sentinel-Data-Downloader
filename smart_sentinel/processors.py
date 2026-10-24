"""
Optional geospatial post-processing tools: JP2 to GeoTIFF/COG conversion, spectral indices, and RGB composites.
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import rasterio
    HAS_RASTERIO = True
except ImportError:
    HAS_RASTERIO = False


def check_rasterio_available() -> None:
    """Verifies that rasterio is installed before running geospatial conversions."""
    if not HAS_RASTERIO:
        raise ImportError(
            "Geospatial processing requires 'rasterio'.\n"
            "Install optional geospatial dependencies using:\n"
            "  pip install 'smart-sentinel-downloader[geo]'\n"
            "or with uv:\n"
            "  uv add rasterio"
        )


def convert_jp2_to_geotiff(
    jp2_path: Path,
    output_geotiff: Optional[Path] = None,
    compress: str = "deflate",
    cog: bool = False,
) -> Path:
    """
    Converts a Sentinel-2 JP2 band file into standard GeoTIFF or Cloud-Optimized GeoTIFF (COG).
    Preserves geospatial transform and CRS metadata.
    """
    check_rasterio_available()
    jp2_path = Path(jp2_path)
    output_geotiff = output_geotiff or jp2_path.with_suffix(".tif")

    with rasterio.open(jp2_path) as src:
        profile = src.profile.copy()
        profile.update(
            driver="GTiff",
            compress=compress,
            tiled=True,
            blockxsize=256,
            blockysize=256,
        )

        with rasterio.open(output_geotiff, "w", **profile) as dst:
            for band_idx in range(1, src.count + 1):
                dst.write(src.read(band_idx), band_idx)

    logger.info(f"✓ Converted {jp2_path.name} -> {output_geotiff.name}")
    return output_geotiff


def calculate_ndvi(b04_path: Path, b08_path: Path, output_path: Path) -> Path:
    """
    Computes Normalized Difference Vegetation Index (NDVI) from Red (B04) and NIR (B08) bands:
    NDVI = (NIR - Red) / (NIR + Red)
    """
    check_rasterio_available()
    import numpy as np

    b04_path = Path(b04_path)
    b08_path = Path(b08_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with rasterio.open(b04_path) as red_ds, rasterio.open(b08_path) as nir_ds:
        red = red_ds.read(1).astype("float32")
        nir = nir_ds.read(1).astype("float32")

        # Avoid divide by zero
        denominator = nir + red
        ndvi = np.where(denominator != 0, (nir - red) / denominator, 0)

        profile = red_ds.profile.copy()
        profile.update(
            dtype="float32",
            count=1,
            driver="GTiff",
            nodata=0,
            compress="deflate",
        )

        with rasterio.open(output_path, "w", **profile) as dst:
            dst.write(ndvi, 1)

    logger.info(f"✓ Generated NDVI: {output_path.name}")
    return output_path


def create_rgb_composite(
    red_path: Path,
    green_path: Path,
    blue_path: Path,
    output_path: Path,
    compress: str = "deflate",
) -> Path:
    """
    Combines Red, Green, and Blue single-band raster files into a 3-band GeoTIFF composite.
    Preserves spatial CRS and georeferencing metadata.
    """
    check_rasterio_available()
    red_path, green_path, blue_path = Path(red_path), Path(green_path), Path(blue_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with rasterio.open(red_path) as src_r:
        profile = src_r.profile.copy()
        profile.update(
            driver="GTiff",
            count=3,
            compress=compress,
            tiled=True,
            blockxsize=256,
            blockysize=256,
        )

        with rasterio.open(green_path) as src_g, rasterio.open(blue_path) as src_b:
            r_data = src_r.read(1)
            g_data = src_g.read(1)
            b_data = src_b.read(1)

            with rasterio.open(output_path, "w", **profile) as dst:
                dst.write(r_data, 1)
                dst.write(g_data, 2)
                dst.write(b_data, 3)
                try:
                    from rasterio.enums import ColorInterp
                    dst.colorinterp = (ColorInterp.red, ColorInterp.green, ColorInterp.blue)
                except Exception:
                    pass

    logger.info(f"✓ Generated 3-Band Composite: {output_path.name}")
    return output_path


def create_composite_from_downloaded(
    directory: Path,
    composite_type: str = "rgb",
    output_path: Optional[Path] = None,
) -> Optional[Path]:
    """
    Finds matching band files in a product directory and merges them into a 3-band GeoTIFF composite.
    Supports:
      - 'rgb': Red=B04, Green=B03, Blue=B02
      - 'false-color': NIR=B08, Red=B04, Green=B03
      - 'swir': SWIR=B12, Narrow NIR=B8A, Red=B04
    """
    check_rasterio_available()
    directory = Path(directory)

    # Locate candidate files
    files = list(directory.glob("*.*"))

    def _find_band(band_code: str) -> Optional[Path]:
        band_code_lower = band_code.lower()
        for f in files:
            fname = f.name.lower()
            if (f.suffix.lower() in (".jp2", ".tif", ".tiff") and
                (f"_{band_code_lower}_" in fname or f"_{band_code_lower}." in fname or fname.startswith(f"{band_code_lower}_"))):
                return f
        return None

    composite_lower = composite_type.lower()
    if composite_lower in ("rgb", "true-color"):
        b_r, b_g, b_b = _find_band("B04"), _find_band("B03"), _find_band("B02")
        suffix_name = "RGB"
    elif composite_lower in ("false-color", "cir"):
        b_r, b_g, b_b = _find_band("B08"), _find_band("B04"), _find_band("B03")
        suffix_name = "FalseColor"
    elif composite_lower in ("swir", "geology"):
        b_r, b_g, b_b = _find_band("B12"), _find_band("B8A"), _find_band("B04")
        suffix_name = "SWIR"
    else:
        logger.warning(f"Unsupported composite type: {composite_type}")
        return None

    if not b_r or not b_g or not b_b:
        missing = []
        if not b_r:
            missing.append("Band 1")
        if not b_g:
            missing.append("Band 2")
        if not b_b:
            missing.append("Band 3")
        logger.warning(
            f"Cannot generate composite {composite_type}: missing bands ({', '.join(missing)}) in {directory}"
        )
        return None

    target_out = output_path or (directory / f"{directory.name}_{suffix_name}.tif")
    return create_rgb_composite(b_r, b_g, b_b, target_out)
