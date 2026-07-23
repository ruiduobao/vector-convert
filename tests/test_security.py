"""Security and edge-case tests."""

import json
import os
from pathlib import Path

import pytest

import vector_convert as vc


class TestInputValidation:
    def test_read_nonexistent_file(self):
        with pytest.raises((FileNotFoundError, Exception)):
            vc.read_input("nonexistent_file.geojson")

    def test_unsupported_extension(self, tmp_dir):
        path = tmp_dir / "data.xyz"
        path.write_text("test")
        with pytest.raises(ValueError, match="Unsupported"):
            vc.read_input(str(path))

    def test_empty_geojson_features(self, tmp_dir):
        data = {"type": "FeatureCollection", "features": []}
        path = tmp_dir / "empty.geojson"
        with open(path, "w") as f:
            json.dump(data, f)
        result = vc.read_geojson(str(path))
        assert len(result["features"]) == 0

    def test_empty_csv(self, tmp_dir):
        path = tmp_dir / "empty.csv"
        path.write_text("latitude,longitude\n")
        result = vc.read_csv(str(path))
        assert len(result["features"]) == 0

    def test_invalid_shp_header(self, tmp_dir):
        path = tmp_dir / "bad.shp"
        path.write_bytes(b"\x00" * 100)
        with pytest.raises(ValueError, match="Invalid SHP"):
            vc.read_shapefile(str(path))

    def test_malformed_geojson(self, tmp_dir):
        path = tmp_dir / "bad.geojson"
        path.write_text("{not valid json")
        with pytest.raises(json.JSONDecodeError):
            vc.read_geojson(str(path))


class TestEdgeCases:
    def test_feature_with_null_geometry(self, tmp_dir):
        data = {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "geometry": None, "properties": {"id": 1}},
                {"type": "Feature", "geometry": {"type": "Point", "coordinates": [1, 2]}, "properties": {"id": 2}},
            ],
        }
        path = tmp_dir / "nullgeom.geojson"
        with open(path, "w") as f:
            json.dump(data, f)
        result = vc.read_geojson(str(path))
        assert len(result["features"]) == 2

    def test_feature_with_empty_properties(self, tmp_dir):
        data = {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "geometry": {"type": "Point", "coordinates": [1, 2]}, "properties": {}},
            ],
        }
        path = tmp_dir / "emptyprops.geojson"
        with open(path, "w") as f:
            json.dump(data, f)
        result = vc.read_geojson(str(path))
        assert result["features"][0]["properties"] == {}

    def test_large_precision(self, tmp_dir):
        data = {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "geometry": {"type": "Point", "coordinates": [1.123456789012345, 2.987654321098765]}, "properties": {}},
            ],
        }
        path = tmp_dir / "prec.geojson"
        with open(path, "w") as f:
            json.dump(data, f)
        result_data = vc.read_geojson(str(path))
        filtered = vc.apply_filters(result_data, precision=15)
        coords = filtered["features"][0]["geometry"]["coordinates"]
        assert len(str(coords[0]).split(".")[-1]) <= 15

    def test_special_characters_in_properties(self, tmp_dir):
        data = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [1, 2]},
                    "properties": {"name": "日本語テスト", "city": "北京"},
                },
            ],
        }
        path = tmp_dir / "unicode.geojson"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        result = vc.read_geojson(str(path))
        assert result["features"][0]["properties"]["name"] == "日本語テスト"

    def test_write_csv_empty(self, tmp_dir):
        data = {"type": "FeatureCollection", "features": []}
        output = tmp_dir / "empty_out.csv"
        vc.write_csv(data, str(output))
        assert output.exists()

    def test_write_geojson_preserves_properties(self, sample_geojson_path, tmp_dir):
        data = vc.read_geojson(sample_geojson_path)
        output = tmp_dir / "out.geojson"
        vc.write_geojson(data, str(output))
        result = json.loads(output.read_text())
        assert result["features"][0]["properties"]["name"] == "Beijing"

    def test_multipolygon_geometry(self, tmp_dir):
        data = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "MultiPolygon",
                        "coordinates": [
                            [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
                            [[[2, 2], [3, 2], [3, 3], [2, 3], [2, 2]]],
                        ],
                    },
                    "properties": {"id": 1},
                },
            ],
        }
        path = tmp_dir / "mp.geojson"
        with open(path, "w") as f:
            json.dump(data, f)
        result = vc.read_geojson(str(path))
        assert result["features"][0]["geometry"]["type"] == "MultiPolygon"

    def test_multilinestring_geometry(self, tmp_dir):
        data = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "MultiLineString",
                        "coordinates": [
                            [[0, 0], [1, 1]],
                            [[2, 2], [3, 3]],
                        ],
                    },
                    "properties": {},
                },
            ],
        }
        path = tmp_dir / "mls.geojson"
        with open(path, "w") as f:
            json.dump(data, f)
        result = vc.read_geojson(str(path))
        assert len(result["features"]) == 1

    def test_kml_with_namespace(self, tmp_dir):
        kml = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark>
      <name>Test</name>
      <Point><coordinates>10,20</coordinates></Point>
    </Placemark>
  </Document>
</kml>"""
        path = tmp_dir / "ns.kml"
        path.write_text(kml, encoding="utf-8")
        result = vc.read_kml(str(path))
        assert len(result["features"]) == 1

    def test_gpx_with_track(self, tmp_dir):
        gpx = """<?xml version="1.0" encoding="UTF-8"?>
<gpx xmlns="http://www.topografix.com/GPX/1/1" version="1.1" creator="test">
  <trk>
    <name>Track 1</name>
    <trkseg>
      <trkpt lat="10" lon="20"/>
      <trkpt lat="11" lon="21"/>
    </trkseg>
  </trk>
</gpx>"""
        path = tmp_dir / "trk.gpx"
        path.write_text(gpx, encoding="utf-8")
        result = vc.read_gpx(str(path))
        assert len(result["features"]) == 1
        assert result["features"][0]["geometry"]["type"] == "LineString"
