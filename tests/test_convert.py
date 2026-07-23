"""Tests for core conversion logic."""

import json
import math
import os
import struct
from pathlib import Path

import pytest

import vector_convert as vc


class TestReadGeoJSON:
    def test_read_feature_collection(self, sample_geojson_path):
        data = vc.read_geojson(sample_geojson_path)
        assert data["type"] == "FeatureCollection"
        assert len(data["features"]) == 3

    def test_read_single_feature(self, tmp_dir):
        feat = {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [1, 2]},
            "properties": {"id": 1},
        }
        path = tmp_dir / "single.geojson"
        with open(path, "w") as f:
            json.dump(feat, f)
        data = vc.read_geojson(path)
        assert len(data["features"]) == 1

    def test_read_geometry_object(self, tmp_dir):
        geom = {"type": "Point", "coordinates": [10, 20]}
        path = tmp_dir / "geom.geojson"
        with open(path, "w") as f:
            json.dump(geom, f)
        data = vc.read_geojson(path)
        assert len(data["features"]) == 1
        assert data["features"][0]["geometry"]["coordinates"] == [10, 20]

    def test_read_invalid_type(self, tmp_dir):
        path = tmp_dir / "bad.geojson"
        with open(path, "w") as f:
            json.dump({"type": "Unknown"}, f)
        with pytest.raises(ValueError, match="Unsupported"):
            vc.read_geojson(path)

    def test_read_missing_type(self, tmp_dir):
        path = tmp_dir / "bad.geojson"
        with open(path, "w") as f:
            json.dump({"features": []}, f)
        with pytest.raises(ValueError, match="missing"):
            vc.read_geojson(path)


class TestReadCSV:
    def test_read_csv(self, sample_csv_path):
        data = vc.read_csv(sample_csv_path)
        assert len(data["features"]) == 3
        assert data["features"][0]["geometry"]["type"] == "Point"

    def test_csv_column_detection(self, tmp_dir):
        import csv
        path = tmp_dir / "custom.csv"
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["id", "LATITUDE", "LONGITUDE"])
            writer.writerow([1, 10.0, 20.0])
        data = vc.read_csv(path)
        assert len(data["features"]) == 1
        assert data["features"][0]["geometry"]["coordinates"] == [20.0, 10.0]

    def test_csv_missing_columns(self, tmp_dir):
        import csv
        path = tmp_dir / "nocoord.csv"
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["id", "value"])
            writer.writerow([1, 100])
        with pytest.raises(ValueError, match="lat/lon"):
            vc.read_csv(path)


class TestReadKML:
    def test_read_kml(self, sample_kml_path):
        data = vc.read_kml(sample_kml_path)
        assert len(data["features"]) == 2
        assert data["features"][0]["properties"]["name"] == "Tokyo"

    def test_kml_coordinates(self, sample_kml_path):
        data = vc.read_kml(sample_kml_path)
        coords = data["features"][0]["geometry"]["coordinates"]
        assert abs(coords[0] - 139.6917) < 0.001
        assert abs(coords[1] - 35.6895) < 0.001


class TestReadGPX:
    def test_read_gpx_waypoints(self, sample_gpx_path):
        data = vc.read_gpx(sample_gpx_path)
        wpt_features = [f for f in data["features"] if f["geometry"]["type"] == "Point"]
        assert len(wpt_features) >= 2

    def test_gpx_route(self, sample_gpx_path):
        data = vc.read_gpx(sample_gpx_path)
        line_features = [f for f in data["features"] if f["geometry"]["type"] == "LineString"]
        assert len(line_features) >= 1

    def test_gpx_properties(self, sample_gpx_path):
        data = vc.read_gpx(sample_gpx_path)
        names = [f["properties"].get("name") for f in data["features"]]
        assert "Paris" in names


class TestReadShapefile:
    def test_read_shp(self, sample_shp_dir):
        data = vc.read_shapefile(str(sample_shp_dir) + ".shp")
        assert data["type"] == "FeatureCollection"
        assert len(data["features"]) == 3

    def test_shp_geometry(self, sample_shp_dir):
        data = vc.read_shapefile(str(sample_shp_dir) + ".shp")
        for feat in data["features"]:
            assert feat["geometry"]["type"] == "Point"
            assert len(feat["geometry"]["coordinates"]) == 2

    def test_shp_properties(self, sample_shp_dir):
        data = vc.read_shapefile(str(sample_shp_dir) + ".shp")
        names = [f["properties"].get("NAME") for f in data["features"]]
        assert "Beijing" in names
        assert "Shanghai" in names

    def test_shp_bounds(self, sample_shp_dir):
        data = vc.read_shapefile(str(sample_shp_dir) + ".shp")
        bounds = data["bounds"]
        assert bounds[0] <= bounds[2]
        assert bounds[1] <= bounds[3]

    def test_shp_crs(self, sample_shp_dir):
        data = vc.read_shapefile(str(sample_shp_dir) + ".shp")
        assert data["crs_wkt"] is not None
        assert "WGS 84" in data["crs_wkt"]


class TestReadGeoPackage:
    def test_read_gpkg(self, sample_gpkg_path):
        data = vc.read_geopackage(str(sample_gpkg_path))
        assert len(data["features"]) == 3

    def test_gpkg_properties(self, sample_gpkg_path):
        data = vc.read_geopackage(str(sample_gpkg_path))
        names = [f["properties"].get("name") for f in data["features"]]
        assert "Beijing" in names


class TestWriteGeoJSON:
    def test_write_geojson(self, sample_geojson_path, tmp_dir):
        data = vc.read_geojson(sample_geojson_path)
        output = tmp_dir / "out.geojson"
        vc.write_geojson(data, str(output))
        assert output.exists()
        result = json.loads(output.read_text())
        assert result["type"] == "FeatureCollection"
        assert len(result["features"]) == 3


class TestWriteCSV:
    def test_write_csv(self, sample_geojson_path, tmp_dir):
        data = vc.read_geojson(sample_geojson_path)
        output = tmp_dir / "out.csv"
        vc.write_csv(data, str(output))
        assert output.exists()
        content = output.read_text()
        assert "longitude" in content
        assert "latitude" in content


class TestWriteKML:
    def test_write_kml(self, sample_geojson_path, tmp_dir):
        data = vc.read_geojson(sample_geojson_path)
        output = tmp_dir / "out.kml"
        vc.write_kml(data, str(output))
        assert output.exists()
        content = output.read_text()
        assert "<kml" in content


class TestWriteGPX:
    def test_write_gpx(self, sample_geojson_path, tmp_dir):
        data = vc.read_geojson(sample_geojson_path)
        output = tmp_dir / "out.gpx"
        vc.write_gpx(data, str(output))
        assert output.exists()
        content = output.read_text()
        assert "<gpx" in content


class TestWriteShapefile:
    def test_write_shp(self, sample_geojson_path, tmp_dir):
        data = vc.read_geojson(sample_geojson_path)
        output = tmp_dir / "out.shp"
        vc.write_shapefile(data, str(output))
        assert (tmp_dir / "out.shp").exists()
        assert (tmp_dir / "out.shx").exists()
        assert (tmp_dir / "out.dbf").exists()

    def test_write_shp_roundtrip(self, sample_geojson_path, tmp_dir):
        data = vc.read_geojson(sample_geojson_path)
        shp_out = tmp_dir / "out.shp"
        vc.write_shapefile(data, str(shp_out))
        result = vc.read_shapefile(str(shp_out))
        assert len(result["features"]) == 3


class TestWriteGeoPackage:
    def test_write_gpkg(self, sample_geojson_path, tmp_dir):
        data = vc.read_geojson(sample_geojson_path)
        output = tmp_dir / "out.gpkg"
        vc.write_geopackage(data, str(output))
        assert output.exists()

    def test_gpkg_roundtrip(self, sample_geojson_path, tmp_dir):
        data = vc.read_geojson(sample_geojson_path)
        gpkg_out = tmp_dir / "out.gpkg"
        vc.write_geopackage(data, str(gpkg_out))
        result = vc.read_geopackage(str(gpkg_out))
        assert len(result["features"]) == 3


class TestCRSTransform:
    def test_4326_to_3857(self):
        lon, lat = 0, 0
        x, y = vc.transform_point(lon, lat, 4326, 3857)
        assert abs(x) < 0.001
        assert abs(y) < 0.001

    def test_3857_to_4326(self):
        x, y = 0, 0
        lon, lat = vc.transform_point(x, y, 3857, 4326)
        assert abs(lon) < 0.001
        assert abs(lat) < 0.001

    def test_roundtrip_4326_3857(self):
        lon, lat = 116.4, 39.9
        x, y = vc.transform_point(lon, lat, 4326, 3857)
        lon2, lat2 = vc.transform_point(x, y, 3857, 4326)
        assert abs(lon - lon2) < 0.001
        assert abs(lat - lat2) < 0.001

    def test_same_crs(self):
        lon, lat = 100.0, 50.0
        x, y = vc.transform_point(lon, lat, 4326, 4326)
        assert x == lon
        assert y == lat


class TestGeometryTransform:
    def test_transform_point(self):
        geom = {"type": "Point", "coordinates": [116.4, 39.9]}
        result = vc.transform_geometry(geom, 4326, 3857)
        assert result["type"] == "Point"
        assert result["coordinates"][0] != 116.4

    def test_transform_linestring(self):
        geom = {"type": "LineString", "coordinates": [[0, 0], [1, 1]]}
        result = vc.transform_geometry(geom, 4326, 3857)
        assert result["type"] == "LineString"
        assert len(result["coordinates"]) == 2


class TestRoundGeometry:
    def test_round_point(self):
        geom = {"type": "Point", "coordinates": [1.123456789, 2.987654321]}
        result = vc.round_geometry(geom, 4)
        assert result["coordinates"][0] == 1.1235
        assert result["coordinates"][1] == 2.9877

    def test_round_linestring(self):
        geom = {"type": "LineString", "coordinates": [[1.111111, 2.222222], [3.333333, 4.444444]]}
        result = vc.round_geometry(geom, 2)
        assert result["coordinates"][0] == [1.11, 2.22]


class TestBboxFilter:
    def test_point_in_bbox(self):
        coords = [116.4, 39.9]
        assert vc.coords_in_bbox(coords, [115, 38, 117, 40]) is True

    def test_point_outside_bbox(self):
        coords = [116.4, 39.9]
        assert vc.coords_in_bbox(coords, [0, 0, 10, 10]) is False

    def test_geometry_intersects(self):
        geom = {"type": "Point", "coordinates": [116.4, 39.9]}
        assert vc.geometry_intersects_bbox(geom, [115, 38, 117, 40]) is True

    def test_geometry_no_intersect(self):
        geom = {"type": "Point", "coordinates": [0, 0]}
        assert vc.geometry_intersects_bbox(geom, [115, 38, 117, 40]) is False


class TestGetInfo:
    def test_info(self, sample_geojson_path):
        data = vc.read_geojson(sample_geojson_path)
        info = vc.get_info(data)
        assert info["feature_count"] == 3
        assert "Point" in info["geometry_types"]
        assert "name" in info["fields"]
        assert info["bounds"] is not None


class TestDBFParser:
    def test_parse_dbase_header(self, sample_shp_dir):
        dbf_path = str(sample_shp_dir) + ".dbf"
        with open(dbf_path, "rb") as f:
            data = f.read()
        info = vc.parse_dbase_header(data)
        assert info["num_records"] == 3
        assert len(info["fields"]) == 1
        assert info["fields"][0]["name"] == "NAME"


class TestFormatDetection:
    def test_extensions(self):
        assert vc.FORMAT_EXTENSIONS[".shp"] == "shp"
        assert vc.FORMAT_EXTENSIONS[".geojson"] == "geojson"
        assert vc.FORMAT_EXTENSIONS[".json"] == "geojson"
        assert vc.FORMAT_EXTENSIONS[".kml"] == "kml"
        assert vc.FORMAT_EXTENSIONS[".gpx"] == "gpx"
        assert vc.FORMAT_EXTENSIONS[".gpkg"] == "gpkg"
        assert vc.FORMAT_EXTENSIONS[".csv"] == "csv"


class TestConvertFunction:
    def test_convert_geojson_to_csv(self, sample_geojson_path, tmp_dir):
        output = tmp_dir / "out.csv"
        result = vc.convert(str(sample_geojson_path), str(output), "csv")
        assert result["features"] == 3
        assert output.exists()

    def test_convert_info_only(self, sample_geojson_path):
        info = vc.convert(str(sample_geojson_path), None, None, info_only=True)
        assert info["feature_count"] == 3

    def test_convert_geojson_to_geojson(self, sample_geojson_path, tmp_dir):
        output = tmp_dir / "out.geojson"
        result = vc.convert(str(sample_geojson_path), str(output), "geojson")
        assert result["features"] == 3
