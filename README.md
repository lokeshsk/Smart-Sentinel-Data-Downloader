# Sentinel Smart Downloader

A flexible and efficient Python tool for downloading Sentinel-1 and Sentinel-2 data from the Copernicus Data Space Ecosystem (CDSE). Download complete products as ZIP files or extract specific files without downloading the entire archive.

## Features

### Dual Download Modes

1. **Full Product Download** (`sentinel_zip_downloader.py`)
   - Download complete Sentinel-1 and Sentinel-2 products as ZIP files
   - Resume interrupted downloads automatically
   - Parallel downloads with configurable workers
   - Robust retry logic with exponential backoff

2. **Selective File Download** (`sentinel_downloader.py`)
   - Extract specific files without downloading entire products
   - **Sentinel-2**: TCI (True Color Image) 10m JP2 files
   - **Sentinel-1**: VH polarization TIFF files
   - Saves bandwidth and storage

### Key Capabilities

- **Auto-detection**: Automatically identifies Sentinel-1 vs Sentinel-2 products
- **UUID & Name Support**: Works with both product UUIDs and full product names
- **Resume Support**: Continue interrupted downloads from where they left off
- **Rate Limit Handling**: Automatically handles API rate limits
- **Parallel Downloads**: Multi-threaded downloading for efficiency
- **Progress Tracking**: Real-time progress bars for each download
- **Organized Storage**: Automatic organization by mission type
- **Production Ready**: Comprehensive error handling and logging

## Requirements

- Python 3.7+
- Copernicus Data Space Ecosystem account ([Register here](https://dataspace.copernicus.eu/))

## Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/sentinel-smart-downloader.git
   cd sentinel-smart-downloader
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure credentials**
   
   Create a `.env` file in the project root:
   ```env
   SENTINEL_USER=your_email@example.com
   SENTINEL_PASS=your_password
   ```

## Usage

### Full Product Download (ZIP)

Download complete Sentinel products as ZIP files:

```bash
python sentinel_zip_downloader.py ids.txt
```

**Output structure:**
```
downloads/
├── sentinel1/
│   └── S1A_IW_GRDH_1SDV_20240115T123456_....zip
└── sentinel2/
    └── S2B_MSIL2A_20260113T062129_....zip
```

### Selective File Download

Download specific files from products without downloading the entire archive:

```bash
# Auto-detect mission type
python sentinel_downloader.py ids.txt

# Force specific mission
python sentinel_downloader.py ids.txt --mission sentinel1
python sentinel_downloader.py ids.txt --mission sentinel2

# Custom settings
python sentinel_downloader.py ids.txt --workers 8 --output-dir my_data
```

**Output structure:**
```
sentinel_downloads/
├── s1_vh/
│   └── T41RMH_20260113T062129_VH_10m.tiff
└── s2_tci/
    └── T41RMH_20260113T062129_TCI_10m.jp2
```

### Product IDs File Format

Create a text file (e.g., `ids.txt`) with one product ID per line:

```text
# Sentinel-2 products (UUIDs)
b44fc1ca-4852-488f-a492-929a2e483c4a
1a71615d-e32e-48e4-8a4e-5e154eb67bcd

# Sentinel-1 products (full names)
S1A_IW_GRDH_1SDV_20240115T123456_20240115T123521_052345_064F8A_1234

# Comments are supported (lines starting with #)
```

**Supported ID formats:**
- Product UUIDs (e.g., `b44fc1ca-4852-488f-a492-929a2e483c4a`)
- Full product names (e.g., `S2B_MSIL2A_20260113T062129_N0511_R034_T41RMH_20260113T083904`)

## Configuration

### Command-line Options

**Selective Downloader:**
```bash
python sentinel_downloader.py --help

Options:
  --mission {auto,sentinel1,sentinel2}  Mission type (default: auto-detect)
  --workers N                           Number of parallel workers (default: 4)
  --output-dir DIR                      Output directory (default: sentinel_downloads)
```

### Configuration Variables

Edit the `CONFIG` dictionary in the scripts to customize:

```python
CONFIG = {
    "workers": 10,           # Number of parallel download threads
    "chunk_mb": 16,          # Download chunk size in MB
    "max_retries": 3,        # Maximum retry attempts
    "download_dir": "downloads",  # Output directory
    "timeout": 120,          # Request timeout in seconds
    "backoff_429": 30,       # Wait time on rate limit (seconds)
}
```

## 📊 Examples

### Example 1: Download Sentinel-2 TCI Files

```bash
# Create ids.txt with Sentinel-2 product IDs
echo "b44fc1ca-4852-488f-a492-929a2e483c4a" > s2_ids.txt

# Download TCI files
python sentinel_downloader.py s2_ids.txt --mission sentinel2
```

### Example 2: Download Sentinel-1 Full Products

```bash
# Create ids.txt with Sentinel-1 product IDs
echo "S1A_IW_GRDH_1SDV_20240115T123456_20240115T123521_052345_064F8A_1234" > s1_ids.txt

# Download complete ZIP files
python sentinel_zip_downloader.py s1_ids.txt
```

### Example 3: Mixed Products with Auto-detection

```bash
# Create mixed ids file
cat > mixed_ids.txt << EOF
b44fc1ca-4852-488f-a492-929a2e483c4a  # Sentinel-2
S1A_IW_GRDH_1SDV_20240115T123456_...  # Sentinel-1
EOF

# Auto-detect and download
python sentinel_downloader.py mixed_ids.txt
```

## Troubleshooting

### Authentication Errors

**Problem:** `401 Unauthorized` or `403 Forbidden`

**Solution:** 
- Verify your credentials in `.env` file
- Ensure your CDSE account is active
- Token automatically refreshes every 10 minutes

### Rate Limiting

**Problem:** `429 Too Many Requests`

**Solution:**
- Script automatically waits 30 seconds when rate limited
- Reduce number of workers: `--workers 2`
- Increase `backoff_429` in CONFIG

### Incomplete Downloads

**Problem:** Download stops before completion

**Solution:**
- Simply re-run the script - downloads will resume automatically
- Check your internet connection
- Increase timeout in CONFIG

### File Not Found in Product

**Problem:** `TCI_10m.jp2 not found` or `VH TIFF not found`

**Solution:**
- Verify the product type matches the expected files
- For Sentinel-2 L2A products, TCI files should be present
- For Sentinel-1 GRD products with dual polarization, VH should be present
- Check product metadata on [Copernicus Browser](https://dataspace.copernicus.eu/browser/)

## Project Structure

```
sentinel-smart-downloader/
├── sentinel_downloader.py          # Selective file downloader
├── sentinel_zip_downloader.py      # Full product ZIP downloader
├── requirements.txt                # Python dependencies
├── .env                            # Credentials (create this)
├── .env.example                    # Example credentials file
├── ids.txt                         # Product IDs (create this)
├── README.md                       # This file
├── downloads/                      # ZIP downloads output
│   ├── sentinel1/
│   └── sentinel2/
└── sentinel_downloads/             # Selective downloads output
    ├── s1_vh/
    └── s2_tci/
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

### Adding New File Types

To add support for new file types, edit `FILE_PATTERNS` in `sentinel_downloader.py`:

```python
FILE_PATTERNS = {
    "sentinel1": {
        "pattern": lambda name: "vh" in name.lower() and name.lower().endswith(".tiff"),
        "description": "VH polarization TIFF",
        "subdir": "s1_vh"
    },
    # Add your new pattern here
}
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- [Copernicus Data Space Ecosystem](https://dataspace.copernicus.eu/) for providing free access to Sentinel data
- ESA for the Sentinel missions

## Support

- **Issues**: [GitHub Issues](https://github.com/yourusername/sentinel-smart-downloader/issues)
- **Discussions**: [GitHub Discussions](https://github.com/yourusername/sentinel-smart-downloader/discussions)

## 🔗 Related Projects

- [sentinelsat](https://github.com/sentinelsat/sentinelsat) - Python library for Sentinel data search and download
- [eodag](https://github.com/CS-SI/eodag) - Earth Observation Data Access Gateway

---
