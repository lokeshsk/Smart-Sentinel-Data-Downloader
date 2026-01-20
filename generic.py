"""
Sentinel Data Downloader
Downloads specific files from Sentinel-1 and Sentinel-2 products from Copernicus Data Space Ecosystem
without downloading the entire SAFE product.

Supported missions:
    - Sentinel-1: Downloads VH polarization TIFF files
    - Sentinel-2: Downloads True Color Image (TCI) JP2 files

Usage:
    python sentinel_downloader.py ids.txt [--mission sentinel1|sentinel2]
    
    If --mission is not specified, the script auto-detects based on product ID format.

Requirements:
    - .env file with SENTINEL_USER and SENTINEL_PASS credentials
    - ids.txt file with one Sentinel product ID per line
"""

import os
import sys
import time
import logging
import argparse
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

# Load environment variables
load_dotenv()

SENTINEL_USER = os.getenv("SENTINEL_USER")
SENTINEL_PASS = os.getenv("SENTINEL_PASS")

if not SENTINEL_USER or not SENTINEL_PASS:
    logger.error("Missing credentials: set SENTINEL_USER and SENTINEL_PASS in .env file")
    sys.exit(1)

# Configuration
CONFIG = {
    "workers": 4,
    "download_dir": "sentinel_downloads",
    "timeout": 120,
    "token_refresh_seconds": 600,
    "chunk_size_mb": 1,
}

# API endpoints
IDENTITY_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
CATALOGUE_URL = "https://catalogue.dataspace.copernicus.eu/odata/v1"
DOWNLOAD_URL = "https://download.dataspace.copernicus.eu/odata/v1"

# Mission-specific file patterns
FILE_PATTERNS = {
    "sentinel1": {
        "pattern": lambda name: "vh" in name.lower() and name.lower().endswith(".tiff"),
        "description": "VH polarization TIFF",
        "subdir": "s1_vh"
    },
    "sentinel2": {
        "pattern": lambda name: "TCI_10m.jp2" in name,
        "description": "TCI 10m JP2",
        "subdir": "s2_tci"
    }
}


class CopernicusAPIError(Exception):
    """Custom exception for API errors"""
    pass


class AuthenticationManager:
    """Handles authentication token management for Copernicus API"""
    
    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.token = None
        self.token_timestamp = 0
        self.lock = threading.Lock()
    
    def get_token(self):
        """Get valid authentication token, refreshing if necessary"""
        with self.lock:
            if self.token and time.time() - self.token_timestamp < CONFIG["token_refresh_seconds"]:
                return self.token
            
            logger.info("Requesting new authentication token")
            
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
                logger.info("Successfully obtained authentication token")
                
                return self.token
                
            except requests.exceptions.RequestException as e:
                raise CopernicusAPIError(f"Authentication failed: {e}")


class SentinelDownloader:
    """Downloads specific files from Sentinel products"""
    
    def __init__(self, auth_manager, mission="auto"):
        self.auth = auth_manager
        self.mission = mission
        self.download_dir = Path(CONFIG["download_dir"])
        self.download_dir.mkdir(exist_ok=True)
    
    def _api_request(self, url):
        """Make authenticated API request and return JSON response"""
        token = self.auth.get_token()
        
        try:
            response = requests.get(
                url,
                headers={"Authorization": f"Bearer {token}"},
                timeout=CONFIG["timeout"]
            )
            
            if not response.ok:
                raise CopernicusAPIError(
                    f"API request failed: {response.status_code} - {response.text[:200]}"
                )
            
            return response.json()
            
        except requests.exceptions.RequestException as e:
            raise CopernicusAPIError(f"Request failed: {e}")
    
    def _extract_values(self, json_response):
        """Extract values from API response, handling different formats"""
        if isinstance(json_response, dict):
            if "value" in json_response:
                return json_response["value"]
            if "result" in json_response:
                return json_response["result"]
        
        if isinstance(json_response, list):
            return json_response
        
        raise CopernicusAPIError(f"Unexpected API response structure: {json_response}")
    
    def _get_product_name(self, product_id):
        """Fetch product name from API (handles both UUID and name formats)"""
        # If it looks like a UUID (contains dashes), fetch the product name
        if "-" in product_id:
            try:
                product_url = f"{CATALOGUE_URL}/Products({product_id})"
                response = self._api_request(product_url)
                return response.get("Name", product_id)
            except Exception as e:
                logger.warning(f"Could not fetch product name for {product_id}: {e}")
                return product_id
        return product_id
    
    def _detect_mission(self, product_id):
        """Auto-detect mission type from product ID or name"""
        # First, get the actual product name if we have a UUID
        product_name = self._get_product_name(product_id)
        product_upper = product_name.upper()
        
        if product_upper.startswith("S1"):
            return "sentinel1"
        elif product_upper.startswith("S2"):
            return "sentinel2"
        else:
            raise CopernicusAPIError(
                f"Cannot detect mission type from product: {product_name}. "
                "Expected product name to start with S1 or S2"
            )
    
    def _find_file_recursive(self, node, token, pattern_func):
        """Recursively search for file matching pattern in product node tree"""
        nodes_uri = node.get("Nodes", {}).get("uri")
        
        # Leaf node - check if it matches
        if not nodes_uri:
            node_name = node.get("Name", "")
            if pattern_func(node_name):
                return node
            return None
        
        # Directory node - recurse into children
        response = self._api_request(nodes_uri)
        child_nodes = self._extract_values(response)
        
        for child in child_nodes:
            child_name = child.get("Name", "")
            
            # Check if this is a matching file
            if pattern_func(child_name) and child.get("ChildrenNumber", 0) == 0:
                return child
            
            # Recurse into subdirectories
            if child.get("ChildrenNumber", 0) > 0:
                result = self._find_file_recursive(child, token, pattern_func)
                if result:
                    return result
        
        return None
    
    def download_file(self, product_id):
        """Download target file for given Sentinel product ID (UUID or name)"""
        
        # Get actual product name for logging
        product_name = self._get_product_name(product_id)
        
        # Detect mission type
        if self.mission == "auto":
            detected_mission = self._detect_mission(product_id)
        else:
            detected_mission = self.mission
        
        if detected_mission not in FILE_PATTERNS:
            raise CopernicusAPIError(f"Unsupported mission: {detected_mission}")
        
        pattern_config = FILE_PATTERNS[detected_mission]
        pattern_func = pattern_config["pattern"]
        file_description = pattern_config["description"]
        subdir = pattern_config["subdir"]
        
        logger.info(f"Processing {detected_mission.upper()} product: {product_name}")
        logger.info(f"Target file: {file_description}")
        
        token = self.auth.get_token()
        
        # Get root nodes of the product
        root_url = f"{CATALOGUE_URL}/Products({product_id})/Nodes"
        root_response = self._api_request(root_url)
        root_nodes = self._extract_values(root_response)
        
        if not root_nodes:
            raise CopernicusAPIError(f"No nodes found for product: {product_id}")
        
        # Find target file in product structure
        logger.info(f"Searching for {file_description} in product structure")
        target_node = self._find_file_recursive(root_nodes[0], token, pattern_func)
        
        if not target_node:
            raise CopernicusAPIError(
                f"{file_description} not found in product: {product_id}"
            )
        
        # Extract download URL from node
        nodes_uri = target_node.get("Nodes", {}).get("uri")
        if not nodes_uri:
            raise CopernicusAPIError(f"No download URI found in target node")
        
        download_url = nodes_uri.rstrip("/Nodes") + "/$value"
        filename = target_node["Name"]
        file_size = target_node.get("ContentLength", 0)
        
        # Create mission-specific subdirectory
        output_dir = self.download_dir / subdir
        output_dir.mkdir(exist_ok=True)
        output_path = output_dir / filename
        
        # Check if file already exists
        if output_path.exists():
            existing_size = output_path.stat().st_size
            if existing_size == file_size:
                logger.info(f"File already exists with correct size: {filename}")
                return str(output_path)
            else:
                logger.warning(f"Existing file has incorrect size, re-downloading: {filename}")
        
        # Download file with progress bar
        logger.info(f"Downloading: {filename} ({file_size / 1024 / 1024:.1f} MB)")
        
        try:
            headers = {"Authorization": f"Bearer {token}"}
            
            with requests.get(download_url, headers=headers, stream=True, timeout=CONFIG["timeout"]) as r:
                r.raise_for_status()
                
                chunk_size = CONFIG["chunk_size_mb"] * 1024 * 1024
                
                with open(output_path, "wb") as f, tqdm(
                    desc=filename[:50],  # Truncate long filenames
                    total=file_size,
                    unit="B",
                    unit_scale=True,
                    unit_divisor=1024,
                ) as progress_bar:
                    for chunk in r.iter_content(chunk_size=chunk_size):
                        if chunk:
                            f.write(chunk)
                            progress_bar.update(len(chunk))
            
            logger.info(f"Successfully downloaded: {filename}")
            return str(output_path)
            
        except requests.exceptions.RequestException as e:
            if output_path.exists():
                output_path.unlink()
            raise CopernicusAPIError(f"Download failed: {e}")


def download_worker(queue, downloader):
    """Worker thread for downloading files from queue"""
    while True:
        product_id = queue.get()
        
        try:
            output_file = downloader.download_file(product_id)
            logger.info(f"✓ SUCCESS: {product_id} -> {output_file}")
            
        except Exception as e:
            logger.error(f"✗ FAILED: {product_id} - {e}")
        
        finally:
            queue.task_done()


def read_product_ids(filepath):
    """Read product IDs from text file"""
    try:
        with open(filepath, 'r') as f:
            ids = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]
        
        if not ids:
            raise ValueError("No product IDs found in file")
        
        return ids
        
    except FileNotFoundError:
        logger.error(f"File not found: {filepath}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error reading file: {e}")
        sys.exit(1)


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="Download specific files from Sentinel-1 and Sentinel-2 products",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Auto-detect mission from product IDs
  python sentinel_downloader.py ids.txt
  
  # Force Sentinel-1 mode
  python sentinel_downloader.py s1_ids.txt --mission sentinel1
  
  # Force Sentinel-2 mode
  python sentinel_downloader.py s2_ids.txt --mission sentinel2
  
  # Adjust number of parallel downloads
  python sentinel_downloader.py ids.txt --workers 8

Supported files:
  Sentinel-1: VH polarization TIFF files
  Sentinel-2: TCI 10m JP2 files
        """
    )
    
    parser.add_argument(
        "ids_file",
        help="Text file containing product IDs (one per line)"
    )
    
    parser.add_argument(
        "--mission",
        choices=["auto", "sentinel1", "sentinel2"],
        default="auto",
        help="Mission type (default: auto-detect from product ID)"
    )
    
    parser.add_argument(
        "--workers",
        type=int,
        default=CONFIG["workers"],
        help=f"Number of parallel download workers (default: {CONFIG['workers']})"
    )
    
    parser.add_argument(
        "--output-dir",
        default=CONFIG["download_dir"],
        help=f"Output directory (default: {CONFIG['download_dir']})"
    )
    
    return parser.parse_args()


def main():
    """Main entry point"""
    args = parse_arguments()
    
    # Update config from arguments
    CONFIG["workers"] = args.workers
    CONFIG["download_dir"] = args.output_dir
    
    product_ids = read_product_ids(args.ids_file)
    
    logger.info("=" * 60)
    logger.info("Sentinel Data Downloader")
    logger.info("=" * 60)
    logger.info(f"Products to download: {len(product_ids)}")
    logger.info(f"Mission mode: {args.mission}")
    logger.info(f"Output directory: {CONFIG['download_dir']}")
    logger.info(f"Worker threads: {CONFIG['workers']}")
    logger.info("=" * 60)
    
    # Initialize authentication and downloader
    auth_manager = AuthenticationManager(SENTINEL_USER, SENTINEL_PASS)
    downloader = SentinelDownloader(auth_manager, mission=args.mission)
    
    # Create download queue and worker threads
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
    
    # Wait for all downloads to complete
    download_queue.join()
    
    logger.info("=" * 60)
    logger.info("All downloads completed")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()