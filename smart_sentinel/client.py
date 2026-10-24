"""
CDSE API Client for querying metadata, searching products, and navigating product file trees.
"""

import logging
import re
from typing import Any, Dict, List, Optional

import requests

from smart_sentinel.auth import AuthenticationManager
from smart_sentinel.config import (
    CATALOGUE_URL,
    DEFAULT_TIMEOUT,
    S1_POLARIZATION_PRESETS,
    S2_BAND_PRESETS,
    STAC_URL,
)
from smart_sentinel.models import Product, ProductFile

logger = logging.getLogger(__name__)

UUID_REGEX = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


class CDSEClientError(Exception):
    """Raised when an API request to the CDSE Catalogue or STAC fails."""


class CDSEClient:
    """Client for discovering and querying CDSE Sentinel products and internal files."""

    def __init__(self, auth_manager: Optional[AuthenticationManager] = None):
        self.auth = auth_manager or AuthenticationManager()

    def _api_get(self, url: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Makes an authenticated GET request with the bearer token."""
        token = self.auth.get_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }

        try:
            response = requests.get(url, headers=headers, params=params, timeout=DEFAULT_TIMEOUT)

            # Auto-retry once if unauthorized
            if response.status_code in (401, 403):
                token = self.auth.get_token(force_refresh=True)
                headers["Authorization"] = f"Bearer {token}"
                response = requests.get(url, headers=headers, params=params, timeout=DEFAULT_TIMEOUT)

            if not response.ok:
                raise CDSEClientError(
                    f"API request failed with status {response.status_code}: {response.text[:300]}"
                )

            return response.json()
        except requests.exceptions.RequestException as exc:
            raise CDSEClientError(f"Network error querying CDSE API: {exc}") from exc

    def _extract_values(self, json_data: Any) -> List[Dict[str, Any]]:
        """Normalizes OData responses into a list of items."""
        if isinstance(json_data, dict):
            if "value" in json_data:
                return json_data["value"]
            if "result" in json_data:
                return json_data["result"]
            return [json_data]
        if isinstance(json_data, list):
            return json_data
        return []

    def get_product(self, product_id_or_name: str) -> Product:
        """
        Retrieves product metadata by either its UUID or full SAFE product name.
        """
        product_id_or_name = product_id_or_name.strip()

        if UUID_REGEX.match(product_id_or_name):
            url = f"{CATALOGUE_URL}/Products({product_id_or_name})"
            data = self._api_get(url)
            return self._build_product_from_odata(data)

        # It is a product name; query by name filter
        url = f"{CATALOGUE_URL}/Products"
        params = {"$filter": f"Name eq '{product_id_or_name}'"}
        data = self._api_get(url, params=params)
        items = self._extract_values(data)

        if not items:
            raise CDSEClientError(f"Product not found by name: '{product_id_or_name}'")

        return self._build_product_from_odata(items[0])

    def _build_product_from_odata(self, data: Dict[str, Any]) -> Product:
        """Constructs a Product model from an OData JSON object."""
        checksum_val = None
        checksum_algo = "MD5"
        checksum_list = data.get("Checksum", [])
        if checksum_list and isinstance(checksum_list, list) and len(checksum_list) > 0:
            checksum_val = checksum_list[0].get("Value")
            checksum_algo = checksum_list[0].get("Algorithm", "MD5")

        collection = "Unknown"
        if "Collection" in data and isinstance(data["Collection"], dict):
            collection = data["Collection"].get("Name", "Unknown")

        cloud_cover = None
        for attr in data.get("Attributes", []):
            if attr.get("Name") == "cloudCover":
                cloud_cover = float(attr.get("Value", 0.0))
                break

        return Product(
            id=data.get("Id", ""),
            name=data.get("Name", ""),
            collection=collection,
            content_length=data.get("ContentLength", 0),
            publication_date=data.get("PublicationDate"),
            footprint=data.get("GeoFootprint"),
            cloud_cover=cloud_cover,
            checksum=checksum_val,
            checksum_algorithm=checksum_algo,
            raw_metadata=data,
        )

    def search(
        self,
        collection: str = "SENTINEL-2",
        bbox: Optional[List[float]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        max_cloud_cover: Optional[float] = None,
        limit: int = 10,
    ) -> List[Product]:
        """
        Searches CDSE catalog using the STAC API, falling back to OData if needed.
        bbox format: [min_lon, min_lat, max_lon, max_lat]
        """
        # Map collection shorthand
        col_upper = collection.upper()
        if col_upper in ("S2", "SENTINEL2", "SENTINEL-2"):
            stac_collection = "SENTINEL-2"
        elif col_upper in ("S1", "SENTINEL1", "SENTINEL-1"):
            stac_collection = "SENTINEL-1"
        else:
            stac_collection = collection

        # Try STAC Search first
        try:
            return self._search_stac(
                collection=stac_collection,
                bbox=bbox,
                start_date=start_date,
                end_date=end_date,
                max_cloud_cover=max_cloud_cover,
                limit=limit,
            )
        except Exception as exc:
            logger.warning(f"STAC search encountered an issue: {exc}. Trying OData search...")
            return self._search_odata(
                collection=stac_collection,
                bbox=bbox,
                start_date=start_date,
                end_date=end_date,
                max_cloud_cover=max_cloud_cover,
                limit=limit,
            )

    def _search_stac(
        self,
        collection: str,
        bbox: Optional[List[float]],
        start_date: Optional[str],
        end_date: Optional[str],
        max_cloud_cover: Optional[float],
        limit: int,
    ) -> List[Product]:
        """Executes a STAC /search POST query."""
        search_url = f"{STAC_URL}/search"
        payload: Dict[str, Any] = {
            "collections": [collection],
            "limit": limit,
        }

        if bbox:
            payload["bbox"] = bbox

        if start_date and end_date:
            s = start_date if "T" in start_date else f"{start_date}T00:00:00Z"
            e = end_date if "T" in end_date else f"{end_date}T23:59:59Z"
            payload["datetime"] = f"{s}/{e}"
        elif start_date:
            s = start_date if "T" in start_date else f"{start_date}T00:00:00Z"
            payload["datetime"] = f"{s}/.."

        if max_cloud_cover is not None:
            payload["query"] = {"eo:cloud_cover": {"lte": max_cloud_cover}}

        token = self.auth.get_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        res = requests.post(search_url, json=payload, headers=headers, timeout=DEFAULT_TIMEOUT)
        res.raise_for_status()

        features = res.json().get("features", [])
        products: List[Product] = []

        for feat in features:
            props = feat.get("properties", {})
            feat_id = feat.get("id", "")

            # Look for CDSE internal UUID if present in properties
            cdse_id = props.get("id") or feat_id
            product_name = props.get("title") or feat_id
            cloud = props.get("eo:cloud_cover")

            products.append(
                Product(
                    id=cdse_id,
                    name=product_name,
                    collection=collection,
                    publication_date=props.get("datetime"),
                    footprint=feat.get("geometry"),
                    cloud_cover=cloud,
                    raw_metadata=feat,
                )
            )

        return products

    def _search_odata(
        self,
        collection: str,
        bbox: Optional[List[float]],
        start_date: Optional[str],
        end_date: Optional[str],
        max_cloud_cover: Optional[float],
        limit: int,
    ) -> List[Product]:
        """Executes an OData catalog query with filters."""
        filters = [f"Collection/Name eq '{collection}'"]

        if start_date:
            s = start_date if "T" in start_date else f"{start_date}T00:00:00.000Z"
            filters.append(f"ContentDate/Start ge {s}")
        if end_date:
            e = end_date if "T" in end_date else f"{end_date}T23:59:59.999Z"
            filters.append(f"ContentDate/Start le {e}")

        if max_cloud_cover is not None:
            filters.append(f"Attributes/OData.CSC.DoubleAttribute/any(att:att/Name eq 'cloudCover' and att/OData.CSC.DoubleAttribute/Value le {max_cloud_cover})")

        if bbox:
            # bbox is [min_lon, min_lat, max_lon, max_lat]
            min_lon, min_lat, max_lon, max_lat = bbox
            polygon_wkt = (
                f"POLYGON(({min_lon} {min_lat}, {max_lon} {min_lat}, "
                f"{max_lon} {max_lat}, {min_lon} {max_lat}, {min_lon} {min_lat}))"
            )
            filters.append(f"OData.CSC.Intersects(area=geography'SRID=4326;{polygon_wkt}')")

        params = {
            "$filter": " and ".join(filters),
            "$top": limit,
            "$orderby": "ContentDate/Start desc",
        }

        url = f"{CATALOGUE_URL}/Products"
        data = self._api_get(url, params=params)
        items = self._extract_values(data)
        return [self._build_product_from_odata(item) for item in items]

    def _find_files_recursive(self, node: Dict[str, Any]) -> List[ProductFile]:
        """Recursively traverses OData product node hierarchy to discover downloadable files."""
        files: List[ProductFile] = []
        nodes_uri = node.get("Nodes", {}).get("uri")

        # If it has no Nodes URI, it's a leaf node (a file)
        if not nodes_uri:
            download_url = node.get("Nodes", {}).get("uri")
            if not download_url:
                # Value endpoint
                node_id = node.get("Id")
                download_url = f"{CATALOGUE_URL}/Nodes({node_id})/$value"

            checksum_val = None
            checksum_algo = "MD5"
            checksum_list = node.get("Checksum", [])
            if checksum_list and isinstance(checksum_list, list) and len(checksum_list) > 0:
                checksum_val = checksum_list[0].get("Value")
                checksum_algo = checksum_list[0].get("Algorithm", "MD5")

            files.append(
                ProductFile(
                    id=node.get("Id", ""),
                    name=node.get("Name", ""),
                    download_url=download_url,
                    content_length=node.get("ContentLength", 0),
                    checksum=checksum_val,
                    checksum_algorithm=checksum_algo,
                    raw_node=node,
                )
            )
            return files

        # It's a directory; recurse into children
        child_response = self._api_get(nodes_uri)
        children = self._extract_values(child_response)

        for child in children:
            if child.get("ChildrenNumber", 0) == 0:
                child_uri = child.get("Nodes", {}).get("uri", "")
                download_url = child_uri.rstrip("/Nodes") + "/$value" if child_uri else ""

                checksum_val = None
                checksum_algo = "MD5"
                checksum_list = child.get("Checksum", [])
                if checksum_list and isinstance(checksum_list, list) and len(checksum_list) > 0:
                    checksum_val = checksum_list[0].get("Value")
                    checksum_algo = checksum_list[0].get("Algorithm", "MD5")

                files.append(
                    ProductFile(
                        id=child.get("Id", ""),
                        name=child.get("Name", ""),
                        download_url=download_url,
                        content_length=child.get("ContentLength", 0),
                        checksum=checksum_val,
                        checksum_algorithm=checksum_algo,
                        raw_node=child,
                    )
                )
            else:
                files.extend(self._find_files_recursive(child))

        return files

    def list_product_files(self, product_id_or_name: str) -> List[ProductFile]:
        """Lists all individual asset files within a product."""
        product = self.get_product(product_id_or_name)
        root_url = f"{CATALOGUE_URL}/Products({product.id})/Nodes"
        root_nodes = self._extract_values(self._api_get(root_url))

        files: List[ProductFile] = []
        for root_node in root_nodes:
            files.extend(self._find_files_recursive(root_node))

        return files

    def resolve_requested_bands(self, mission: str, requested: Optional[str]) -> List[str]:
        """Resolves band preset string or comma-separated list into normalized identifiers."""
        if not requested:
            return ["TCI"] if mission == "sentinel2" else ["vh"]

        requested_clean = requested.strip().lower()

        if mission == "sentinel2":
            if requested_clean in S2_BAND_PRESETS:
                return S2_BAND_PRESETS[requested_clean]
        elif mission == "sentinel1":
            if requested_clean in S1_POLARIZATION_PRESETS:
                return S1_POLARIZATION_PRESETS[requested_clean]

        # Comma-separated list
        return [b.strip() for b in requested.split(",") if b.strip()]

    def find_files_for_bands(
        self, product: Product, requested_bands: Optional[str] = None
    ) -> List[ProductFile]:
        """
        Finds files matching the requested band identifiers or presets within the product.
        """
        all_files = self.list_product_files(product.id)
        target_bands = self.resolve_requested_bands(product.mission, requested_bands)
        target_bands_lower = [b.lower() for b in target_bands]

        matched_files: List[ProductFile] = []

        for pfile in all_files:
            fname = pfile.name.lower()
            if product.is_sentinel2:
                # Match JP2 files corresponding to the band
                if fname.endswith(".jp2"):
                    for band in target_bands_lower:
                        # Handles patterns like _b04_10m.jp2, _b04.jp2, _tci_10m.jp2, etc.
                        if f"_{band}_" in fname or f"_{band}." in fname or fname.startswith(f"{band}_"):
                            if pfile not in matched_files:
                                matched_files.append(pfile)
            elif product.is_sentinel1:
                # Match TIFF files corresponding to polarization
                if fname.endswith(".tiff") or fname.endswith(".tif"):
                    for pol in target_bands_lower:
                        if f"-{pol}-" in fname or f"_{pol}_" in fname or f"{pol}" in fname:
                            if pfile not in matched_files:
                                matched_files.append(pfile)
            else:
                # Generic fallback: substring match
                for b in target_bands_lower:
                    if b in fname:
                        matched_files.append(pfile)

        return matched_files
