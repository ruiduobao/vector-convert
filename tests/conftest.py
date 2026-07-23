import importlib.util
import os
import sys
import tempfile
from pathlib import Path

import pytest

# Load vector-convert.py as vector_convert module
def _load_module():
    module_path = Path(__file__).parent.parent / "vector-convert.py"
    spec = importlib.util.spec_from_file_location("vector_convert", str(module_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["vector_convert"] = mod
    spec.loader.exec_module(mod)
    return mod

vector_convert = _load_module()

@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)

@pytest.fixture
def sample_geojson_path(tmp_dir):
    data = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [116.4, 39.9]},
                "properties": {"name": "Beijing", "population": 21540000, "country": "China"},
            },
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [121.47, 31.23]},
                "properties": {"name": "Shanghai", "population": 24870000, "country": "China"},
            },
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [114.05, 22.55]},
                "properties": {"name": "Shenzhen", "population": 17560000, "country": "China"},
            },
        ],
    }
    path = tmp_dir / "test.geojson"
    import json
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return path

@pytest.fixture
def sample_line_geojson_path(tmp_dir):
    data = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[0, 0], [1, 1], [2, 0], [3, 1]],
                },
                "properties": {"name": "route1"},
            },
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]],
                },
                "properties": {"name": "zone1", "area": 100},
            },
        ],
    }
    path = tmp_dir / "lines.geojson"
    import json
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return path

@pytest.fixture
def sample_csv_path(tmp_dir):
    import csv
    path = tmp_dir / "test.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "latitude", "longitude", "type"])
        writer.writerow(["Point A", 39.9, 116.4, "capital"])
        writer.writerow(["Point B", 31.23, 121.47, "city"])
        writer.writerow(["Point C", 22.55, 114.05, "city"])
    return path

@pytest.fixture
def sample_kml_path(tmp_dir):
    kml_content = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark>
      <name>Tokyo</name>
      <Point>
        <coordinates>139.6917,35.6895</coordinates>
      </Point>
    </Placemark>
    <Placemark>
      <name>Osaka</name>
      <Point>
        <coordinates>135.5023,34.6937</coordinates>
      </Point>
    </Placemark>
  </Document>
</kml>"""
    path = tmp_dir / "test.kml"
    with open(path, "w", encoding="utf-8") as f:
        f.write(kml_content)
    return path

@pytest.fixture
def sample_gpx_path(tmp_dir):
    gpx_content = """<?xml version="1.0" encoding="UTF-8"?>
<gpx xmlns="http://www.topografix.com/GPX/1/1" version="1.1" creator="test">
  <wpt lat="48.8566" lon="2.3522">
    <name>Paris</name>
  </wpt>
  <wpt lat="51.5074" lon="-0.1278">
    <name>London</name>
  </wpt>
  <rte>
    <name>Route 1</name>
    <rtept lat="48.8566" lon="2.3522"/>
    <rtept lat="51.5074" lon="-0.1278"/>
  </rte>
</gpx>"""
    path = tmp_dir / "test.gpx"
    with open(path, "w", encoding="utf-8") as f:
        f.write(gpx_content)
    return path

@pytest.fixture
def sample_shp_dir(tmp_dir):
    """Create a minimal valid Shapefile with binary data."""
    import struct

    name = "test"
    shp_path = tmp_dir / f"{name}.shp"
    shx_path = tmp_dir / f"{name}.shx"
    dbf_path = tmp_dir / f"{name}.dbf"
    prj_path = tmp_dir / f"{name}.prj"

    points = [(116.4, 39.9), (121.47, 31.23), (114.05, 22.55)]
    names = ["Beijing", "Shanghai", "Shenzhen"]

    # Build SHP file
    num_records = len(points)
    record_content_size = 20  # shape_type(4) + x(8) + y(8)
    shp_file_size_words = 50 + num_records * (2 + record_content_size // 2)

    shp_header = struct.pack(">I", 9994)
    shp_header += b"\x00" * 20
    shp_header += struct.pack(">I", shp_file_size_words)
    shp_header += struct.pack("<I", 1000)
    shp_header += struct.pack("<I", 1)  # Point type
    shp_header += struct.pack("<dddd", 114.05, 22.55, 121.47, 39.9)
    shp_header += struct.pack("<dddd", 0, 0, 0, 0)

    with open(shp_path, "wb") as f:
        f.write(shp_header)
        offset = 50
        for i, (x, y) in enumerate(points):
            rec_data = struct.pack("<I", 1) + struct.pack("<dd", x, y)
            rec_size_words = len(rec_data) // 2
            f.write(struct.pack(">II", i + 1, rec_size_words))
            f.write(rec_data)

    # Build SHX file
    shx_header = struct.pack(">I", 9994)
    shx_header += b"\x00" * 20
    shx_header += struct.pack(">I", 50 + num_records * 4)
    shx_header += struct.pack("<I", 1000)
    shx_header += struct.pack("<I", 1)
    shx_header += struct.pack("<dddd", 114.05, 22.55, 121.47, 39.9)
    shx_header += struct.pack("<dddd", 0, 0, 0, 0)

    with open(shx_path, "wb") as f:
        f.write(shx_header)
        offset = 50
        for i, (x, y) in enumerate(points):
            f.write(struct.pack(">II", offset, 10))
            offset += 2 + 10

    # Build DBF file (dBASE III)
    num_fields = 1
    field_name = "NAME"
    field_len = 20
    header_size = 32 + num_fields * 32 + 1
    record_size = 1 + field_len

    dbf_header = struct.pack("<BBBBIHH", 3, 0, 0, 0, num_records, header_size, record_size)
    dbf_header += b"\x00" * 20
    dbf_header += field_name.encode("ascii").ljust(11, b"\x00")
    dbf_header += b"C"
    dbf_header += b"\x00" * 4
    dbf_header += struct.pack("<BB", field_len, 0)
    dbf_header += b"\x00" * 14
    dbf_header += b"\x0D"

    with open(dbf_path, "wb") as f:
        f.write(dbf_header)
        for name_val in names:
            rec = b" " + name_val.encode("ascii").ljust(field_len, b" ")
            f.write(rec)

    # Build PRJ file
    with open(prj_path, "w") as f:
        f.write('GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433],AUTHORITY["EPSG","4326"]]')

    return tmp_dir / name

@pytest.fixture
def sample_gpkg_path(tmp_dir, sample_geojson_path):
    """Create a GeoPackage from sample GeoJSON data."""
    import sqlite3
    from datetime import datetime

    path = tmp_dir / "test.gpkg"
    conn = sqlite3.connect(str(path))
    cursor = conn.cursor()

    cursor.execute("""CREATE TABLE gpkg_spatial_ref_sys (
        srs_name TEXT, srs_id INTEGER PRIMARY KEY, organization TEXT,
        organization_coordsys_id INTEGER, definition TEXT, description TEXT
    )""")
    cursor.execute("INSERT INTO gpkg_spatial_ref_sys VALUES (?, ?, ?, ?, ?, ?)",
                   ("WGS 84", 4326, "EPSG", 4326, vector_convert.EPSG_DEFS[4326]["wkt"], ""))

    cursor.execute("""CREATE TABLE gpkg_contents (
        table_name TEXT PRIMARY KEY, data_type TEXT, identifier TEXT,
        description TEXT, last_change DATETIME, min_x REAL, min_y REAL,
        max_x REAL, max_y REAL, srs_id INTEGER
    )""")

    cursor.execute("""CREATE TABLE gpkg_geometry_columns (
        table_name TEXT, column_name TEXT, geometry_type_name TEXT,
        srs_id INTEGER, z INTEGER, m INTEGER
    )""")

    cursor.execute("""CREATE TABLE features (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        geom BLOB,
        name TEXT,
        population TEXT,
        country TEXT
    )""")

    points = [
        ("Beijing", "21540000", "China", 116.4, 39.9),
        ("Shanghai", "24870000", "China", 121.47, 31.23),
        ("Shenzhen", "17560000", "China", 114.05, 22.55),
    ]

    for name, pop, country, lon, lat in points:
        import io
        import struct as _struct
        buf = io.BytesIO()
        # GeoPackage envelope header: magic "GP", version 1, flags (little-endian, envelope=xy), srs_id=4326
        buf.write(b"GP")
        buf.write(_struct.pack("<B", 0))  # version
        buf.write(_struct.pack("<B", 0x01))  # flags: little-endian, no envelope
        buf.write(_struct.pack("<i", 4326))  # srs_id
        # WKB geometry
        buf.write(_struct.pack("<B", 1))  # WKB byte order
        buf.write(_struct.pack("<I", 1))  # WKB type = Point
        buf.write(_struct.pack("<dd", lon, lat))
        geom_blob = buf.getvalue()
        cursor.execute("INSERT INTO features (geom, name, population, country) VALUES (?, ?, ?, ?)",
                       (geom_blob, name, pop, country))

    cursor.execute("INSERT INTO gpkg_contents VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                   ("features", "features", "features", "", "2024-01-01T00:00:00.000Z",
                    -180, -90, 180, 90, 4326))
    cursor.execute("INSERT INTO gpkg_geometry_columns VALUES (?, ?, ?, ?, ?, ?)",
                   ("features", "geom", "GEOMETRY", 4326, 0, 0))

    conn.commit()
    conn.close()
    return path
