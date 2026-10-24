"""
Export utilities for CDSE catalog search results (GeoJSON, CSV).
"""

import csv
import json
import logging
from pathlib import Path
from typing import List

from smart_sentinel.models import Product

logger = logging.getLogger(__name__)


def export_search_results_to_geojson(products: List[Product], output_path: Path) -> Path:
    """
    Exports a list of Product search results into a standard GeoJSON FeatureCollection.
    Can be directly loaded into QGIS, ArcGIS, or web mapping tools.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    features = []
    for prod in products:
        feature = {
            "type": "Feature",
            "id": prod.id,
            "geometry": prod.footprint or None,
            "properties": {
                "id": prod.id,
                "name": prod.name,
                "collection": prod.collection,
                "mission": prod.mission,
                "publication_date": prod.publication_date,
                "cloud_cover": prod.cloud_cover,
                "size_mb": round(prod.size_mb, 2),
                "checksum": prod.checksum,
                "checksum_algorithm": prod.checksum_algorithm,
            },
        }
        features.append(feature)

    geojson_data = {
        "type": "FeatureCollection",
        "features": features,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(geojson_data, f, indent=2)

    logger.info(f"✓ Exported {len(products)} search results to GeoJSON: {output_path}")
    return output_path


def export_search_results_to_csv(products: List[Product], output_path: Path) -> Path:
    """
    Exports a list of Product search results into a CSV spreadsheet.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    headers = [
        "id",
        "name",
        "collection",
        "mission",
        "publication_date",
        "cloud_cover",
        "size_mb",
        "checksum",
        "checksum_algorithm",
    ]

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for prod in products:
            writer.writerow({
                "id": prod.id,
                "name": prod.name,
                "collection": prod.collection,
                "mission": prod.mission,
                "publication_date": prod.publication_date or "",
                "cloud_cover": prod.cloud_cover if prod.cloud_cover is not None else "",
                "size_mb": round(prod.size_mb, 2),
                "checksum": prod.checksum or "",
                "checksum_algorithm": prod.checksum_algorithm or "",
            })

    logger.info(f"✓ Exported {len(products)} search results to CSV: {output_path}")
    return output_path


def export_search_results(products: List[Product], output_path: Path) -> Path:
    """
    Automatically detects extension (.geojson or .csv) and exports accordingly.
    """
    path = Path(output_path)
    ext = path.suffix.lower()

    if ext in (".geojson", ".json"):
        return export_search_results_to_geojson(products, path)
    elif ext == ".csv":
        return export_search_results_to_csv(products, path)
    else:
        # Default to GeoJSON if unrecognized
        target = path.with_suffix(".geojson")
        return export_search_results_to_geojson(products, target)
