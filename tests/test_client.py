"""
Unit tests for CDSEClient: UUID resolution, OData queries, STAC search, and band resolution.
"""

import responses

from smart_sentinel.config import CATALOGUE_URL, STAC_URL


@responses.activate
def test_get_product_by_uuid(mock_client):
    """Verify querying product by UUID fetches direct OData record."""
    uuid = "b44fc1ca-4852-488f-a492-929a2e483c4a"
    product_url = f"{CATALOGUE_URL}/Products({uuid})"

    responses.add(
        responses.GET,
        product_url,
        json={
            "Id": uuid,
            "Name": "S2B_MSIL2A_20240113T062129_N0510_R034_T41RMH_20240113T083904",
            "ContentLength": 1048576000,
            "PublicationDate": "2024-01-13T10:00:00Z",
            "Checksum": [{"Value": "a1b2c3d4e5f6", "Algorithm": "MD5"}],
            "Collection": {"Name": "SENTINEL-2"},
        },
        status=200,
    )

    prod = mock_client.get_product(uuid)
    assert prod.id == uuid
    assert prod.is_sentinel2 is True
    assert prod.mission == "sentinel2"
    assert prod.content_length == 1048576000
    assert prod.checksum == "a1b2c3d4e5f6"
    assert prod.checksum_algorithm == "MD5"


@responses.activate
def test_get_product_by_name(mock_client):
    """Verify querying product by name queries OData with $filter."""
    name = "S1A_IW_GRDH_1SDV_20240115T123456_20240115T123521_052345_064F8A_1234"
    url = f"{CATALOGUE_URL}/Products"

    responses.add(
        responses.GET,
        url,
        json={
            "value": [
                {
                    "Id": "987e6543-e21b-12d3-a456-426614174000",
                    "Name": name,
                    "ContentLength": 524288000,
                    "Collection": {"Name": "SENTINEL-1"},
                }
            ]
        },
        status=200,
    )

    prod = mock_client.get_product(name)
    assert prod.id == "987e6543-e21b-12d3-a456-426614174000"
    assert prod.is_sentinel1 is True
    assert prod.mission == "sentinel1"


@responses.activate
def test_search_stac(mock_client):
    """Verify STAC search API request formatting and model creation."""
    search_url = f"{STAC_URL}/search"

    responses.add(
        responses.POST,
        search_url,
        json={
            "features": [
                {
                    "id": "item-uuid-1234",
                    "properties": {
                        "id": "item-uuid-1234",
                        "title": "S2A_MSIL2A_20240101T000000_TEST",
                        "datetime": "2024-01-01T00:00:00Z",
                        "eo:cloud_cover": 5.2,
                    },
                    "geometry": {"type": "Point", "coordinates": [10.0, 45.0]},
                }
            ]
        },
        status=200,
    )

    results = mock_client.search(
        collection="SENTINEL-2",
        bbox=[9.0, 44.0, 11.0, 46.0],
        start_date="2024-01-01",
        end_date="2024-01-15",
        max_cloud_cover=10.0,
        limit=5,
    )

    assert len(results) == 1
    item = results[0]
    assert item.id == "item-uuid-1234"
    assert item.name == "S2A_MSIL2A_20240101T000000_TEST"
    assert item.cloud_cover == 5.2


def test_resolve_requested_bands(mock_client):
    """Verify band preset resolution."""
    # Sentinel-2 Presets
    rgb_bands = mock_client.resolve_requested_bands("sentinel2", "rgb")
    assert "TCI" in rgb_bands
    assert "B04" in rgb_bands

    ndvi_bands = mock_client.resolve_requested_bands("sentinel2", "ndvi")
    assert ndvi_bands == ["B04", "B08"]

    custom_bands = mock_client.resolve_requested_bands("sentinel2", "B02,B03,B04")
    assert custom_bands == ["B02", "B03", "B04"]

    # Sentinel-1 Presets
    s1_vh = mock_client.resolve_requested_bands("sentinel1", "vh")
    assert s1_vh == ["vh"]
