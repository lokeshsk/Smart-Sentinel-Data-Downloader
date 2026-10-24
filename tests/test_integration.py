"""
Comprehensive end-to-end integration tests for CLI binaries, module execution, and Python SDK.
Simulates real user workflows across platforms.
"""

import json
from pathlib import Path

import responses
from click.testing import CliRunner

from smart_sentinel.cli import main
from smart_sentinel.config import CATALOGUE_URL, IDENTITY_URL, STAC_URL
from smart_sentinel.downloader import Downloader
from smart_sentinel.export import export_search_results


def test_cli_runner_search_and_export_geojson(tmp_path, mock_auth):
    """Test full CLI search command exporting to GeoJSON."""
    search_url = f"{STAC_URL}/search"

    with responses.RequestsMock() as rsps:
        # Mock auth token
        rsps.add(
            responses.POST,
            IDENTITY_URL,
            json={"access_token": "mock_test_token"},
            status=200,
        )
        rsps.add(
            responses.POST,
            search_url,
            json={
                "features": [
                    {
                        "id": "item-123",
                        "properties": {
                            "id": "item-123",
                            "title": "S2A_MSIL2A_TEST",
                            "datetime": "2024-05-10T10:00:00Z",
                            "eo:cloud_cover": 4.5,
                        },
                        "geometry": {"type": "Polygon", "coordinates": [[[12.0, 41.0], [13.0, 41.0], [13.0, 42.0], [12.0, 41.0]]]},
                    }
                ]
            },
            status=200,
        )

        export_file = tmp_path / "search_output.geojson"
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "search",
                "--bbox", "12.0", "41.0", "13.0", "42.0",
                "--start", "2024-05-01",
                "--end", "2024-05-31",
                "--max-cloud", "10",
                "--export", str(export_file),
            ],
            env={"SENTINEL_USER": "test@example.com", "SENTINEL_PASS": "testpass"},
        )

        assert result.exit_code == 0
        assert "Search Results" in result.output
        assert "S2A_MSIL2A_TEST" in result.output
        assert export_file.exists()

        data = json.loads(export_file.read_text(encoding="utf-8"))
        assert data["type"] == "FeatureCollection"
        assert len(data["features"]) == 1
        assert data["features"][0]["id"] == "item-123"


def test_cli_runner_download_selective_mock(tmp_path, mock_auth):
    """Test full CLI download command downloading mock band files."""
    uuid = "b44fc1ca-4852-488f-a492-929a2e483c4a"
    product_url = f"{CATALOGUE_URL}/Products({uuid})"
    nodes_url = f"{CATALOGUE_URL}/Products({uuid})/Nodes"
    download_url = f"{CATALOGUE_URL}/Nodes(node123)/$value"
    band_content = b"TEST_BAND_PIXEL_DATA_JP2"

    with responses.RequestsMock() as rsps:
        # 0. Auth token
        rsps.add(
            responses.POST,
            IDENTITY_URL,
            json={"access_token": "mock_test_token"},
            status=200,
        )
        # 1. Product metadata
        rsps.add(
            responses.GET,
            product_url,
            json={
                "Id": uuid,
                "Name": "S2B_MSIL2A_TEST_PRODUCT",
                "ContentLength": 100000,
                "Collection": {"Name": "SENTINEL-2"},
            },
            status=200,
        )

        # 2. Root nodes
        rsps.add(
            responses.GET,
            nodes_url,
            json={
                "value": [
                    {
                        "Id": "root_node",
                        "Name": "S2B_MSIL2A_TEST_PRODUCT.SAFE",
                        "ChildrenNumber": 1,
                        "Nodes": {"uri": f"{CATALOGUE_URL}/Nodes(root_node)/Nodes"},
                    }
                ]
            },
            status=200,
        )

        # 3. Children nodes (containing TCI band file)
        rsps.add(
            responses.GET,
            f"{CATALOGUE_URL}/Nodes(root_node)/Nodes",
            json={
                "value": [
                    {
                        "Id": "node123",
                        "Name": "T41RMH_20240113T062129_TCI_10m.jp2",
                        "ChildrenNumber": 0,
                        "ContentLength": len(band_content),
                        "Nodes": {"uri": f"{CATALOGUE_URL}/Nodes(node123)/Nodes"},
                    }
                ]
            },
            status=200,
        )

        # 4. Binary download
        rsps.add(
            responses.GET,
            download_url,
            body=band_content,
            status=200,
            headers={"Content-Length": str(len(band_content))},
        )

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "download",
                uuid,
                "--bands", "tci",
                "--output-dir", str(tmp_path),
                "--no-checksum",
            ],
            env={"SENTINEL_USER": "test@example.com", "SENTINEL_PASS": "testpass"},
        )

        assert result.exit_code == 0
        assert "Successful: 1" in result.output
        downloaded_file = tmp_path / "sentinel2" / "S2B_MSIL2A_TEST_PRODUCT" / "T41RMH_20240113T062129_TCI_10m.jp2"
        assert downloaded_file.exists()
        assert downloaded_file.read_bytes() == band_content


def test_python_sdk_programmatic_workflow(tmp_path, mock_client):
    """Test using smart_sentinel programmatically in Python code."""
    # 1. Search
    search_url = f"{STAC_URL}/search"
    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.POST,
            search_url,
            json={
                "features": [
                    {
                        "id": "uuid-sdk-1",
                        "properties": {
                            "id": "uuid-sdk-1",
                            "title": "S2A_SDK_PRODUCT",
                            "datetime": "2024-05-01T00:00:00Z",
                            "eo:cloud_cover": 0.0,
                        },
                        "geometry": {"type": "Point", "coordinates": [0, 0]},
                    }
                ]
            },
            status=200,
        )

        results = mock_client.search(collection="SENTINEL-2", limit=1)
        assert len(results) == 1
        assert results[0].name == "S2A_SDK_PRODUCT"

        # 2. Export
        export_path = tmp_path / "sdk_export.csv"
        export_search_results(results, export_path)
        assert export_path.exists()
        with open(export_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            assert len(lines) == 2  # header + 1 row
            assert "S2A_SDK_PRODUCT" in lines[1]


def test_cross_platform_path_handling(tmp_path):
    """Verify that path resolution works seamlessly regardless of OS path separators."""
    dl = Downloader(download_dir=tmp_path)
    # Testing nested path resolution
    nested = dl.download_dir / "sentinel2" / "scene_name" / "file.jp2"
    assert isinstance(nested, Path)
    # Parent creation should succeed cleanly
    nested.parent.mkdir(parents=True, exist_ok=True)
    assert nested.parent.exists()
    nested.write_bytes(b"DATA")
    assert nested.exists()
