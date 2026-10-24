"""
Configuration settings and constants for CDSE API endpoints.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

# CDSE Service Endpoints
IDENTITY_URL = os.getenv(
    "CDSE_IDENTITY_URL",
    "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
)
CATALOGUE_URL = os.getenv(
    "CDSE_CATALOGUE_URL",
    "https://catalogue.dataspace.copernicus.eu/odata/v1"
)
DOWNLOAD_URL = os.getenv(
    "CDSE_DOWNLOAD_URL",
    "https://download.dataspace.copernicus.eu/odata/v1"
)
ZIPPER_URL = os.getenv(
    "CDSE_ZIPPER_URL",
    "https://zipper.dataspace.copernicus.eu/odata/v1"
)
STAC_URL = os.getenv(
    "CDSE_STAC_URL",
    "https://stac.dataspace.copernicus.eu/v1"
)
S3_ENDPOINT = os.getenv(
    "CDSE_S3_ENDPOINT",
    "https://eodata.dataspace.copernicus.eu"
)

# Operational Defaults
DEFAULT_WORKERS = int(os.getenv("SENTINEL_WORKERS", "4"))
DEFAULT_CHUNK_MB = int(os.getenv("SENTINEL_CHUNK_MB", "8"))
DEFAULT_TIMEOUT = int(os.getenv("SENTINEL_TIMEOUT", "120"))
DEFAULT_RETRIES = int(os.getenv("SENTINEL_MAX_RETRIES", "3"))
DEFAULT_DOWNLOAD_DIR = Path(os.getenv("SENTINEL_DOWNLOAD_DIR", "downloads"))
DEFAULT_BACKOFF_429 = int(os.getenv("SENTINEL_BACKOFF_429", "30"))
TOKEN_REFRESH_SECONDS = int(os.getenv("SENTINEL_TOKEN_REFRESH_SECONDS", "540"))  # 9 minutes

# Sentinel-2 Standard Band Definitions
S2_BAND_PRESETS = {
    "rgb": ["TCI", "B04", "B03", "B02"],
    "tci": ["TCI"],
    "vnir": ["B02", "B03", "B04", "B08"],
    "ndvi": ["B04", "B08"],
    "ndwi": ["B03", "B08"],
    "swir": ["B11", "B12", "B8A"],
    "scl": ["SCL"],
    "10m": ["B02", "B03", "B04", "B08", "TCI"],
    "20m": ["B05", "B06", "B07", "B8A", "B11", "B12", "SCL"],
    "all": [
        "B01", "B02", "B03", "B04", "B05", "B06", "B07", "B08",
        "B8A", "B09", "B11", "B12", "TCI", "SCL", "AOT", "WVP"
    ],
}

# Sentinel-1 Polarization Definitions
S1_POLARIZATION_PRESETS = {
    "vh": ["vh"],
    "vv": ["vv"],
    "dual": ["vh", "vv"],
    "hh": ["hh"],
    "hv": ["hv"],
    "all": ["vh", "vv", "hh", "hv"],
}
