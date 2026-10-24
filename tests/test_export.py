"""
Unit tests for search results export to GeoJSON and CSV.
"""

import csv
import json

from smart_sentinel.export import (
    export_search_results,
    export_search_results_to_csv,
    export_search_results_to_geojson,
)
from smart_sentinel.models import Product


def test_export_search_results_to_geojson(tmp_path):
    """Verify GeoJSON FeatureCollection structure and properties."""
    products = [
        Product(
            id="test-uuid-1",
            name="S2A_MSIL2A_TEST_SCENE_1",
            collection="SENTINEL-2",
            content_length=1000000,
            publication_date="2024-05-01T12:00:00Z",
            footprint={"type": "Polygon", "coordinates": [[[10.0, 45.0], [11.0, 45.0], [11.0, 46.0], [10.0, 45.0]]]},
            cloud_cover=12.5,
            checksum="md5hash123",
        ),
        Product(
            id="test-uuid-2",
            name="S2B_MSIL2A_TEST_SCENE_2",
            collection="SENTINEL-2",
            content_length=2000000,
            publication_date="2024-05-02T12:00:00Z",
            footprint=None,
            cloud_cover=0.0,
            checksum="md5hash456",
        ),
    ]

    out_file = tmp_path / "results.geojson"
    saved = export_search_results_to_geojson(products, out_file)

    assert saved.exists()
    data = json.loads(saved.read_text(encoding="utf-8"))

    assert data["type"] == "FeatureCollection"
    assert len(data["features"]) == 2

    f1 = data["features"][0]
    assert f1["id"] == "test-uuid-1"
    assert f1["geometry"]["type"] == "Polygon"
    assert f1["properties"]["name"] == "S2A_MSIL2A_TEST_SCENE_1"
    assert f1["properties"]["cloud_cover"] == 12.5

    f2 = data["features"][1]
    assert f2["geometry"] is None


def test_export_search_results_to_csv(tmp_path):
    """Verify CSV export formatting and columns."""
    products = [
        Product(
            id="test-uuid-1",
            name="S2A_MSIL2A_TEST_SCENE_1",
            collection="SENTINEL-2",
            content_length=1048576,
            publication_date="2024-05-01T12:00:00Z",
            cloud_cover=5.0,
            checksum="hash1",
        )
    ]

    out_file = tmp_path / "results.csv"
    saved = export_search_results_to_csv(products, out_file)

    assert saved.exists()
    with open(saved, "r", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))
        assert len(reader) == 1
        assert reader[0]["id"] == "test-uuid-1"
        assert reader[0]["name"] == "S2A_MSIL2A_TEST_SCENE_1"
        assert reader[0]["cloud_cover"] == "5.0"
        assert float(reader[0]["size_mb"]) == 1.0


def test_export_search_results_auto_detect(tmp_path):
    """Verify format detection based on file extension."""
    products = [Product(id="1", name="scene1")]

    geojson_out = tmp_path / "export.geojson"
    export_search_results(products, geojson_out)
    assert geojson_out.exists()

    csv_out = tmp_path / "export.csv"
    export_search_results(products, csv_out)
    assert csv_out.exists()
