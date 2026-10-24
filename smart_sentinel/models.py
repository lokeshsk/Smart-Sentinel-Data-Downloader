"""
Data models and classes representing CDSE products, files, and queries.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Product:
    """Represents a Sentinel product in CDSE."""
    id: str
    name: str
    collection: str = "Unknown"
    content_length: int = 0
    publication_date: Optional[str] = None
    footprint: Optional[Dict[str, Any]] = None
    cloud_cover: Optional[float] = None
    checksum: Optional[str] = None
    checksum_algorithm: Optional[str] = "MD5"
    raw_metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_sentinel1(self) -> bool:
        return self.name.upper().startswith("S1")

    @property
    def is_sentinel2(self) -> bool:
        return self.name.upper().startswith("S2")

    @property
    def mission(self) -> str:
        if self.is_sentinel1:
            return "sentinel1"
        elif self.is_sentinel2:
            return "sentinel2"
        return "unknown"

    @property
    def size_mb(self) -> float:
        return self.content_length / (1024 * 1024)

    @property
    def size_gb(self) -> float:
        return self.content_length / (1024 * 1024 * 1024)


@dataclass
class ProductFile:
    """Represents an individual file/asset inside a Sentinel product."""
    id: str
    name: str
    download_url: str
    content_length: int = 0
    checksum: Optional[str] = None
    checksum_algorithm: Optional[str] = "MD5"
    path: str = ""
    raw_node: Dict[str, Any] = field(default_factory=dict)

    @property
    def size_mb(self) -> float:
        return self.content_length / (1024 * 1024)


@dataclass
class SearchFilter:
    """Search parameters for querying CDSE catalog."""
    collection: str = "SENTINEL-2"
    bbox: Optional[List[float]] = None  # [min_lon, min_lat, max_lon, max_lat]
    start_date: Optional[str] = None    # YYYY-MM-DD or ISO8601
    end_date: Optional[str] = None      # YYYY-MM-DD or ISO8601
    max_cloud_cover: Optional[float] = None  # 0 to 100
    limit: int = 10


@dataclass
class DownloadResult:
    """Summary of a completed or failed download."""
    product_id: str
    filename: str
    output_path: Optional[str] = None
    bytes_downloaded: int = 0
    status: str = "SUCCESS"
    error_message: Optional[str] = None
