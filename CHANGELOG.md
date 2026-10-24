# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-10-24

### 🚀 Major Architectural Overhaul
- **Modular Package**: Refactored the entire codebase into a clean, reusable Python package (`smart_sentinel`) installable via `pip install .` or `pip install smart-sentinel-downloader`.
- **Packaging with Astral `uv`**: Full support for `uv`, `pyproject.toml` (PEP 621), and automated wheel builds with `hatchling`.
- **Unified CLI (`sentinel-dl`)**: Replaced 5 fragmented standalone scripts with a unified command-line tool with rich visual output and subcommands (`auth`, `search`, `download`, `info`).

### ✨ New Features
- **STAC & OData Catalog Search**: Added `sentinel-dl search` allowing direct querying by bounding box (`--bbox`), acquisition date range (`--start`, `--end`), and maximum cloud cover percentage (`--max-cloud`).
- **Flexible Band Selection & Presets**: Download preset band groups (`rgb`, `vnir`, `ndvi`, `swir`, `10m`, `20m`, `all`) or custom comma-separated band lists (`--bands B02,B03,B04,B08,SCL`).
- **Sentinel-1 Polarizations**: Added preset and granular selection for Sentinel-1 polarizations (`VH`, `VV`, `HH`, `HV`).
- **Cryptographic Checksum Verification**: Added automatic MD5 and SHA256 integrity validation comparing downloaded bytes against CDSE API metadata.
- **Search Export to GeoJSON & CSV**: Search results can now be exported directly (`--export results.geojson` or `--export results.csv`) for instant visualization in QGIS, ArcGIS, or spreadsheet tools.
- **Automated RGB & False-Color Compositing**: Added `--composite rgb`, `--composite false-color`, and `--composite swir` to automatically merge constituent spectral bands into georeferenced 3-band GeoTIFFs.
- **Product Inspection (`sentinel-dl info`)**: Inspect product metadata, footprint, size, and internal file hierarchy without downloading.
- **Geospatial Post-Processing (`smart_sentinel.processors`)**: Optional modules for converting Sentinel-2 JPEG2000 (`.jp2`) to standard GeoTIFF/Cloud-Optimized GeoTIFF (COG) and on-the-fly NDVI computation.

### 🐛 Bug Fixes & Reliability
- **UUID Auto-Detection Bug**: Fixed crash in mission auto-detection when given UUIDs by resolving UUIDs to product names via OData metadata before mission identification.
- **Resumable HTTP Range Downloads**: Implemented HTTP `Range` request support for both full ZIP archives and individual band files.
- **Atomic File Writes**: All downloads stream to `.part` files first and atomically rename upon complete transfer and checksum validation, preventing corrupt files on unexpected interruption.
- **Thread-Safe Multi-Bar UX**: Cleaned up concurrency output to avoid terminal interleaving.
- **Authentication**: Robust token refresh with automatic retry on 401/403 and exponential backoff on 429 rate limits.

---

## [0.1.0] - Prior Release
- Initial prototype scripts for Sentinel-1 and Sentinel-2 downloads.

