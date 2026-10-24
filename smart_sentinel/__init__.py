"""
Smart Sentinel Data Downloader
A fast, selective, and robust Sentinel-1 and Sentinel-2 downloader for CDSE.
"""

__version__ = "1.0.0"
__author__ = "Lokesh S K"

from smart_sentinel.auth import AuthenticationManager
from smart_sentinel.client import CDSEClient
from smart_sentinel.downloader import Downloader
from smart_sentinel.export import export_search_results
from smart_sentinel.models import Product, ProductFile, SearchFilter

__all__ = [
    "AuthenticationManager",
    "CDSEClient",
    "Downloader",
    "Product",
    "ProductFile",
    "SearchFilter",
    "export_search_results",
    "__version__",
]

