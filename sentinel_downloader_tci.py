"""
Sentinel-2 TCI Downloader
Downloads True Color Image (TCI) JP2 files from Copernicus Data Space Ecosystem
without downloading the entire SAFE product.

Usage:
    python sentinel_downloader_tci.py ids.txt

Requirements:
    - .env file with SENTINEL_USER and SENTINEL_PASS credentials
    - ids.txt file with one Sentinel-2 product ID per line
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
    "download_dir": "tci_downloads",
    "timeout": 120,
    "token_refresh_seconds": 600,
    "chunk_size_mb": 1,
}

# API endpoints
IDENTITY_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
CATALOGUE_URL = "https://catalogue.dataspace.copernicus.eu/odata/v1"
DOWNLOAD_URL = "https://download.dataspace.copernicus.eu/odata/v1"


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
    """Downloads Sentinel-2 TCI files from Copernicus Data Space"""
    
    def __init__(self, auth_manager):
        self.auth = auth_manager
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
    
    def _find_tci_file(self, node, token, target_pattern="TCI_10m.jp2"):
        """Recursively search for TCI file in product node tree"""
        nodes_uri = node.get("Nodes", {}).get("uri")
        
        # Leaf node - check if it matches
        if not nodes_uri:
            if target_pattern in node.get("Name", ""):
                return node
            return None
        
        # Directory node - recurse into children
        response = self._api_request(nodes_uri)
        child_nodes = self._extract_values(response)
        
        for child in child_nodes:
            # Check if this is the target file
            if target_pattern in child.get("Name", "") and child.get("ChildrenNumber", 0) == 0:
                return child
            
            # Recurse into subdirectories
            if child.get("ChildrenNumber", 0) > 0:
                result = self._find_tci_file(child, token, target_pattern)
                if result:
                    return result
        
        return None
    
    def download_tci(self, product_id):
        """Download TCI JP2 file for given Sentinel-2 product ID"""
        logger.info(f"Processing product: {product_id}")
        
        token = self.auth.get_token()
        
        # Get root nodes of the product
        root_url = f"{CATALOGUE_URL}/Products({product_id})/Nodes"
        root_response = self._api_request(root_url)
        root_nodes = self._extract_values(root_response)
        
        if not root_nodes:
            raise CopernicusAPIError(f"No nodes found for product: {product_id}")
        
        # Find TCI file in product structure
        logger.info(f"Searching for TCI file in product structure")
        tci_node = self._find_tci_file(root_nodes[0], token)
        
        if not tci_node:
            raise CopernicusAPIError(f"TCI_10m.jp2 not found in product: {product_id}")
        
        # Extract download URL from node
        nodes_uri = tci_node.get("Nodes", {}).get("uri")
        if not nodes_uri:
            raise CopernicusAPIError(f"No download URI found in TCI node")
        
        download_url = nodes_uri.rstrip("/Nodes") + "/$value"
        filename = tci_node["Name"]
        file_size = tci_node.get("ContentLength", 0)
        output_path = self.download_dir / filename
        
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
                    desc=filename,
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
            output_file = downloader.download_tci(product_id)
            logger.info(f"✓ SUCCESS: {product_id} -> {output_file}")
            
        except Exception as e:
            logger.error(f"✗ FAILED: {product_id} - {e}")
        
        finally:
            queue.task_done()


def read_product_ids(filepath):
    """Read product IDs from text file"""
    try:
        with open(filepath, 'r') as f:
            ids = [line.strip() for line in f if line.strip()]
        
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
        print("Usage: python sentinel_downloader_tci.py ids.txt")
        print("\nDownloads TCI JP2 files from Sentinel-2 products")
        print("ids.txt should contain one product ID per line")
        sys.exit(1)
    
    ids_file = sys.argv[1]
    product_ids = read_product_ids(ids_file)
    
    logger.info(f"Found {len(product_ids)} product(s) to download")
    logger.info(f"Output directory: {CONFIG['download_dir']}")
    logger.info(f"Worker threads: {CONFIG['workers']}")
    
    # Initialize authentication and downloader
    auth_manager = AuthenticationManager(SENTINEL_USER, SENTINEL_PASS)
    downloader = SentinelDownloader(auth_manager)
    
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
    
    logger.info("All downloads completed")


if __name__ == "__main__":
    main()