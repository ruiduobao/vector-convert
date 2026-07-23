"""Integration tests with real file conversions."""

import json
import os
import struct
from pathlib import Path

import pytest

import vector_convert as vc


class TestGeoJSONRoundTrip:
    def test_geojson_to_csv_to_geojson(self, sample_geojson_path, tmp_dir):
        csv_out = tmp_dir / "mid.csv"
        data = vc.read_geojson(str(sample_geojson_path))
        vc.write_csv(data, str(csv_out))
        result = vc.read_csv(str(csv_out))
        assert len(result["features"]) == 3
        for feat in result["features"]:
            assert feat["geometry"]["type"] == "Point"

    def test_geojson_to_kml(self, sample_geojson_path, tmp_dir):
        kml_out = tmp_dir / "out.kml"
        result = vc.convert(str(sample_geojson_path), str(kml_out), "kml")
        assert result["features"] == 3
        parsed = vc.read_kml(str(kml_out))
        assert len(parsed["features"]) == 3

    def test_geojson_to_gpx(self, sample_geojson_path, tmp_dir):
        gpx_out = tmp_dir / "out.gpx"
        result = vc.convert(str(sample_geojson_path), str(gpx_out), "gpx")
        assert result["features"] == 3
        parsed = vc.read_gpx(str(gpx_out))
        assert len(parsed["features"]) == 3

    def test_geojson_to_shp(self, sample_geojson_path, tmp_dir):
        shp_out = tmp_dir / "out.shp"
        result = vc.convert(str(sample_geojson_path), str(shp_out), "shp")
        assert result["features"] == 3
        parsed = vc.read_shapefile(str(shp_out))
        assert len(parsed["features"]) == 3

    def test_geojson_to_gpkg(self, sample_geojson_path, tmp_dir):
        gpkg_out = tmp_dir / "out.gpkg"
        result = vc.convert(str(sample_geojson_path), str(gpkg_out), "gpkg")
        assert result["features"] == 3
        parsed = vc.read_geopackage(str(gpkg_out))
        assert len(parsed["features"]) == 3


class TestShapefileConversion:
    def test_shp_to_geojson(self, sample_shp_dir, tmp_dir):
        geojson_out = tmp_dir / "out.geojson"
        result = vc.convert(str(sample_shp_dir) + ".shp", str(geojson_out), "geojson")
        assert result["features"] == 3
        data = json.loads(geojson_out.read_text())
        assert data["type"] == "FeatureCollection"

    def test_shp_to_csv(self, sample_shp_dir, tmp_dir):
        csv_out = tmp_dir / "out.csv"
        result = vc.convert(str(sample_shp_dir) + ".shp", str(csv_out), "csv")
        assert result["features"] == 3
        content = csv_out.read_text()
        assert "longitude" in content

    def test_shp_to_kml(self, sample_shp_dir, tmp_dir):
        kml_out = tmp_dir / "out.kml"
        result = vc.convert(str(sample_shp_dir) + ".shp", str(kml_out), "kml")
        assert result["features"] == 3


class TestCSVConversion:
    def test_csv_to_geojson(self, sample_csv_path, tmp_dir):
        geojson_out = tmp_dir / "out.geojson"
        result = vc.convert(str(sample_csv_path), str(geojson_out), "geojson")
        assert result["features"] == 3
        data = json.loads(geojson_out.read_text())
        assert data["features"][0]["geometry"]["type"] == "Point"

    def test_csv_to_kml(self, sample_csv_path, tmp_dir):
        kml_out = tmp_dir / "out.kml"
        result = vc.convert(str(sample_csv_path), str(kml_out), "kml")
        assert result["features"] == 3

    def test_csv_to_gpx(self, sample_csv_path, tmp_dir):
        gpx_out = tmp_dir / "out.gpx"
        result = vc.convert(str(sample_csv_path), str(gpx_out), "gpx")
        assert result["features"] == 3


class TestKMLConversion:
    def test_kml_to_geojson(self, sample_kml_path, tmp_dir):
        geojson_out = tmp_dir / "out.geojson"
        result = vc.convert(str(sample_kml_path), str(geojson_out), "geojson")
        assert result["features"] == 2
        data = json.loads(geojson_out.read_text())
        names = [f["properties"].get("name") for f in data["features"]]
        assert "Tokyo" in names

    def test_kml_to_csv(self, sample_kml_path, tmp_dir):
        csv_out = tmp_dir / "out.csv"
        result = vc.convert(str(sample_kml_path), str(csv_out), "csv")
        assert result["features"] == 2


class TestGPXConversion:
    def test_gpx_to_geojson(self, sample_gpx_path, tmp_dir):
        geojson_out = tmp_dir / "out.geojson"
        result = vc.convert(str(sample_gpx_path), str(geojson_out), "geojson")
        assert result["features"] >= 2

    def test_gpx_to_kml(self, sample_gpx_path, tmp_dir):
        kml_out = tmp_dir / "out.kml"
        result = vc.convert(str(sample_gpx_path), str(kml_out), "kml")
        assert result["features"] >= 2


class TestGeoPackageConversion:
    def test_gpkg_to_geojson(self, sample_gpkg_path, tmp_dir):
        geojson_out = tmp_dir / "out.geojson"
        result = vc.convert(str(sample_gpkg_path), str(geojson_out), "geojson")
        assert result["features"] == 3

    def test_gpkg_to_csv(self, sample_gpkg_path, tmp_dir):
        csv_out = tmp_dir / "out.csv"
        result = vc.convert(str(sample_gpkg_path), str(csv_out), "csv")
        assert result["features"] == 3


class TestFilterIntegration:
    def test_filter_with_conversion(self, sample_geojson_path, tmp_dir):
        csv_out = tmp_dir / "filtered.csv"
        result = vc.convert(
            str(sample_geojson_path), str(csv_out), "csv",
            fields="name", precision=2,
        )
        assert result["features"] == 3
        content = csv_out.read_text()
        assert "population" not in content

    def test_bbox_filter_geojson(self, sample_geojson_path, tmp_dir):
        geojson_out = tmp_dir / "clipped.geojson"
        result = vc.convert(
            str(sample_geojson_path), str(geojson_out), "geojson",
            bbox=[115, 20, 122, 35],
        )
        assert result["features"] >= 1

    def test_precision_in_output(self, sample_geojson_path, tmp_dir):
        geojson_out = tmp_dir / "precise.geojson"
        result = vc.convert(
            str(sample_geojson_path), str(geojson_out), "geojson",
            precision=2,
        )
        data = json.loads(geojson_out.read_text())
        for feat in data["features"]:
            coords = feat["geometry"]["coordinates"]
            for c in coords:
                parts = str(c).split(".")
                if len(parts) == 2:
                    assert len(parts[1]) <= 2


class TestMultiStepConversion:
    def test_shp_to_gpkg_to_geojson(self, sample_shp_dir, tmp_dir):
        gpkg_out = tmp_dir / "mid.gpkg"
        geojson_out = tmp_dir / "final.geojson"
        vc.convert(str(sample_shp_dir) + ".shp", str(gpkg_out), "gpkg")
        result = vc.convert(str(gpkg_out), str(geojson_out), "geojson")
        assert result["features"] == 3

    def test_kml_to_shp_to_csv(self, sample_kml_path, tmp_dir):
        shp_out = tmp_dir / "mid.shp"
        csv_out = tmp_dir / "final.csv"
        vc.convert(str(sample_kml_path), str(shp_out), "shp")
        result = vc.convert(str(shp_out), str(csv_out), "csv")
        assert result["features"] == 2
