# Smart Sentinel Data Downloader (`sentinel-dl`)

[![Documentation](https://img.shields.io/badge/docs-lokeshsk.github.io-06b6d4.svg)](https://lokeshsk.github.io/Smart-Sentinel-Data-Downloader/)
[![PyPI version](https://img.shields.io/badge/pypi-v1.0.0-blue.svg)](https://pypi.org/project/smart-sentinel-downloader/)
[![Python versions](https://img.shields.io/badge/python-3.8%20%7C%203.9%20%7C%203.10%20%7C%203.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue)](https://pypi.org/project/smart-sentinel-downloader/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

A fast, selective, and robust Python SDK and CLI tool for discovering and downloading **Sentinel-1** and **Sentinel-2** satellite data from the **Copernicus Data Space Ecosystem (CDSE)**.

Download complete `.SAFE` ZIP products or extract **specific spectral bands directly** without wasting gigabytes of bandwidth.

📖 **Full Documentation Website:** [https://lokeshsk.github.io/Smart-Sentinel-Data-Downloader/](https://lokeshsk.github.io/Smart-Sentinel-Data-Downloader/)  
👤 **Author Website:** [https://lokeshsk.github.io](https://lokeshsk.github.io)

---

## ⚡ Why Smart Sentinel Downloader?

| Feature | Legacy SciHub / Raw CDSE HTTP | Smart Sentinel Downloader (`sentinel-dl`) |
| :--- | :--- | :--- |
| **Download Size** | Full product ZIP only (~1.1 GB) | **Selective Band Download (~100 MB) — Save 90% bandwidth** |
| **Catalog Search** | Manual web browser copying | **Built-in STAC & OData Search CLI** |
| **Global Terminal Access** | Script in folder only | **System-wide `sentinel-dl` binary + `python -m smart_sentinel`** |
| **Python SDK** | Standalone scripts | **Importable Python library (`import smart_sentinel`)** |
| **Download Resume** | Often restarts from 0% | **Byte-range HTTP resumption (`Range: bytes=...`)** |
| **Integrity Check** | None or manual check | **Automatic MD5 / SHA256 checksum verification** |
| **Composites** | Manual GIS stacking | **Automated 3-Band RGB & False Color GeoTIFF generation** |
| **GIS Export** | None | **Export search footprints to GeoJSON / CSV for QGIS** |
| **File Safety** | Half-written files on crash | **Atomic file writes (`.part` staging)** |

---

## 📦 Installation & Global System Setup

### 1. Global Terminal CLI Access (Install Everywhere)

Install once, and the `sentinel-dl` (and `smart-sentinel`) commands become available globally in any terminal:

```bash
# Install globally via standard pip
pip install smart-sentinel-downloader

# Or install globally in editable mode from source
pip install -e .

# Or install as an isolated global CLI via Astral uv tool
uv tool install smart-sentinel-downloader
```

### 2. Standalone Module Execution
If you prefer running via Python directly without modifying PATH binaries:
```bash
python3 -m smart_sentinel --help
```

### 3. Programmatic Python Import
Once installed, use it anywhere in Python (scripts, Jupyter Notebooks, PyTorch/TensorFlow pipelines):
```python
import smart_sentinel
from smart_sentinel import CDSEClient, Downloader
```

### 4. Optional Geospatial Extras
For on-the-fly GeoTIFF/COG conversion, automated 3-band RGB composites, and NDVI computation:
```bash
pip install "smart-sentinel-downloader[geo]"
# or with uv:
uv pip install "smart-sentinel-downloader[geo]"
```

---

## 🔑 Authentication

Create a free account at the [Copernicus Data Space Ecosystem](https://dataspace.copernicus.eu/).

Create a `.env` file in your working directory (or set environment variables):
```env
SENTINEL_USER=your_email@example.com
SENTINEL_PASS=your_password
```

Verify your authentication:
```bash
sentinel-dl auth
```

---

## 🚀 Command-Line Interface (CLI)

Both `sentinel-dl` and `smart-sentinel` command names are supported.

### 1. Catalog Search & Discovery (`search`)
Search CDSE STAC catalog by bounding box, date range, and cloud cover without opening a web browser:

```bash
# Search for Sentinel-2 scenes over Rome with <15% cloud cover
sentinel-dl search \
  --bbox 12.3 41.7 12.7 42.1 \
  --start 2024-05-01 \
  --end 2024-05-31 \
  --max-cloud 15 \
  --limit 5
```

# Search and export footprints to GeoJSON for QGIS / ArcGIS
sentinel-dl search \
  --bbox 12.3 41.7 12.7 42.1 \
  --start 2024-05-01 \
  --end 2024-05-31 \
  --max-cloud 15 \
  --export footprints.geojson

# Search and export tabular summary to CSV
sentinel-dl search --bbox 77.1 28.5 77.3 28.7 --start 2024-06-01 --export scenes.csv

# Direct Search & Download: Add --download to instantly fetch matched scenes
sentinel-dl search --bbox 77.1 28.5 77.3 28.7 --start 2024-06-01 --download --bands rgb
```

---

### 2. Selective Band Download (`download`)
Download only the bands you need (saves up to 90% storage and time):

```bash
# Download True Color (TCI) and RGB bands using a Product UUID
sentinel-dl download b44fc1ca-4852-488f-a492-929a2e483c4a --bands rgb

# Download NDVI bands (Red B04 & NIR B08)
sentinel-dl download S2B_MSIL2A_20240113T062129_N0510_R034_T41RMH_20240113T083904 --bands ndvi

# Download custom bands and cloud mask (SCL)
sentinel-dl download b44fc1ca-4852-488f-a492-929a2e483c4a --bands B02,B03,B04,B08,SCL

# Download and automatically generate a 3-band True Color RGB GeoTIFF composite
sentinel-dl download b44fc1ca-4852-488f-a492-929a2e483c4a --composite rgb

# Download and generate a False Color Infrared (CIR) composite (B08 NIR + B04 Red + B03 Green)
sentinel-dl download b44fc1ca-4852-488f-a492-929a2e483c4a --composite false-color
```

### 3. Full Product ZIP Download
Download complete `.SAFE` product archives with automatic resume:

```bash
sentinel-dl download b44fc1ca-4852-488f-a492-929a2e483c4a --type full
```

### 4. Batch Download from Text File
Download multiple products listed in a text file (`sample_ids.txt`):

```bash
sentinel-dl download --file sample_ids.txt --workers 8 --output-dir my_data
```

---

### 5. Product Inspection (`info`)
Inspect internal file hierarchy, available bands, resolution, and sizes before downloading:

```bash
sentinel-dl info b44fc1ca-4852-488f-a492-929a2e483c4a
```

---

## 🎨 Band Presets Reference

| Mission | Preset Name | Included Bands / Files | Description |
| :--- | :--- | :--- | :--- |
| **Sentinel-2** | `rgb` | `TCI`, `B04`, `B03`, `B02` | Natural True Color Image + 10m RGB bands |
| **Sentinel-2** | `tci` | `TCI` | 10m True Color Image (visual preview) |
| **Sentinel-2** | `vnir` | `B02`, `B03`, `B04`, `B08` | Visible & Near Infrared (10m) |
| **Sentinel-2** | `ndvi` | `B04`, `B08` | Red + NIR for vegetation indices |
| **Sentinel-2** | `ndwi` | `B03`, `B08` | Green + NIR for water bodies |
| **Sentinel-2** | `swir` | `B11`, `B12`, `B8A` | Short-Wave Infrared for moisture & burn scars |
| **Sentinel-2** | `scl` | `SCL` | 20m Scene Classification Layer (cloud mask) |
| **Sentinel-2** | `10m` | `B02`, `B03`, `B04`, `B08`, `TCI` | All 10-meter spatial resolution assets |
| **Sentinel-1** | `vh` | `VH` | Cross-polarization SAR TIFF |
| **Sentinel-1** | `vv` | `VV` | Co-polarization SAR TIFF |
| **Sentinel-1** | `dual`| `VH`, `VV` | Dual polarization SAR pair |

---

## 🐍 Python SDK Usage

Use `smart_sentinel` programmatically in your Python scripts, Jupyter Notebooks, or automated pipelines:

```python
from smart_sentinel import AuthenticationManager, CDSEClient, Downloader

# 1. Initialize client
auth = AuthenticationManager(username="user@example.com", password="password")
client = CDSEClient(auth_manager=auth)

# 2. Search for scenes
scenes = client.search(
    collection="SENTINEL-2",
    bbox=[12.3, 41.7, 12.7, 42.1],
    start_date="2024-05-01",
    end_date="2024-05-15",
    max_cloud_cover=10.0,
    limit=5
)

for scene in scenes:
    print(f"Found: {scene.name} ({scene.cloud_cover}% clouds)")

# 3. Download selective bands
downloader = Downloader(client=client, download_dir="./downloads")
results = downloader.download_selective_bands(
    product_id_or_name=scenes[0].id,
    bands="rgb"
)

for res in results:
    print(f"Downloaded: {res.filename} -> {res.output_path}")
```

---

## 🛠️ Geospatial Post-Processing (Optional)

Convert Sentinel-2 JPEG2000 (`.jp2`) to standard **Cloud-Optimized GeoTIFF (COG)** or compute **NDVI**:

```python
from pathlib import Path
from smart_sentinel.processors import convert_jp2_to_geotiff, calculate_ndvi

# Convert JP2 to GeoTIFF
geotiff = convert_jp2_to_geotiff(Path("downloads/T41RMH_B04_10m.jp2"))

# Compute NDVI GeoTIFF
ndvi = calculate_ndvi(
    b04_path=Path("downloads/T41RMH_B04_10m.jp2"),
    b08_path=Path("downloads/T41RMH_B08_10m.jp2"),
    output_path=Path("downloads/ndvi.tif")
)
```
*(Requires `pip install "smart-sentinel-downloader[geo]"`)*

---

## 🧪 Testing

Run the automated test suite locally:
```bash
uv run pytest -v
```

Run linter:
```bash
uv run ruff check .
```

---

## 🤝 Contributing

Contributions are welcome! Please check out [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on development, testing, and PR submissions.

---

## 📄 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

---

## 🌟 Acknowledgments
- [Copernicus Data Space Ecosystem (CDSE)](https://dataspace.copernicus.eu/) for providing open Earth Observation data.
- European Space Agency (ESA) for the Sentinel satellite missions.
