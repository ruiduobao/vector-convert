#!/usr/bin/env python3
"""Vector data format converter - converts between SHP, GeoJSON, KML, GPX, GeoPackage, CSV.

Privacy disclosure
------------------
This tool reads and writes only local files. No data is sent over the network.

Public domain notice
--------------------
This tool does not transmit any data and does not access any
external services. All processing is local.

License
-------
MIT-0 — No Attribution.
"""

import argparse
import csv
import io
import json
import math
import os
import sqlite3
import struct
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

SUPPORTED_FORMATS = ["shp", "geojson", "kml", "gpx", "gpkg", "csv"]
FORMAT_EXTENSIONS = {
    ".shp": "shp", ".geojson": "geojson", ".json": "geojson",
    ".kml": "kml", ".gpx": "gpx", ".gpkg": "gpkg", ".csv": "csv",
}

EPSG_DEFS = {
    4326: {
        "name": "WGS 84",
        "wkt": 'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433],AUTHORITY["EPSG","4326"]]',
    },
    3857: {
        "name": "WGS 84 / Pseudo-Mercator",
        "wkt": 'PROJCS["WGS 84 / Pseudo-Mercator",GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]],PROJECTION["Mercator_1SP"],PARAMETER["central_meridian",0],PARAMETER["scale_factor",1],PARAMETER["false_easting",0],PARAMETER["false_northing",0],UNIT["metre",1],AUTHORITY["EPSG","3857"]]',
    },
    32633: {
        "name": "WGS 84 / UTM zone 33N",
        "wkt": 'PROJCS["WGS 84 / UTM zone 33N",GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]],PROJECTION["Transverse_Mercator"],PARAMETER["latitude_of_origin",0],PARAMETER["central_meridian",15],PARAMETER["scale_factor",0.9996],PARAMETER["false_easting",500000],PARAMETER["false_northing",0],UNIT["metre",1],AUTHORITY["EPSG","32633"]]',
    },
}

def read_prj_file(path):
    prj_path = Path(path).with_suffix(".prj")
    if prj_path.exists():
        return prj_path.read_text(encoding="utf-8").strip()
    return None

def detect_crs_from_prj(path):
    wkt = read_prj_file(path)
    if wkt:
        return wkt
    return EPSG_DEFS[4326]["wkt"]

def transform_coords(coords, from_crs, to_crs, precision=6):
    if from_crs == to_crs:
        return coords
    return coords

def transform_point(lon, lat, from_epsg, to_epsg):
    if from_epsg == to_epsg:
        return lon, lat
    if from_epsg == 4326 and to_epsg == 3857:
        x = lon * 20037508.34 / 180.0
        y = math.log(math.tan((90 + lat) * math.pi / 360)) / (math.pi / 180)
        y = y * 20037508.34 / 180.0
        return x, y
    if from_epsg == 3857 and to_epsg == 4326:
        lon = (lon / 20037508.34) * 180.0
        lat = (lat / 20037508.34) * 180.0
        lat = 180 / math.pi * (2 * math.atan(math.exp(lat * math.pi / 180)) - math.pi / 2)
        return lon, lat
    return lon, lat

def round_coords(coords, precision):
    if isinstance(coords, (int, float)):
        return round(coords, precision)
    return [round_coords(c, precision) for c in coords]

def coords_in_bbox(coords, bbox):
    if isinstance(coords, (int, float)):
        return True
    if len(coords) == 2 and isinstance(coords[0], (int, float)):
        lon, lat = coords
        return bbox[0] <= lon <= bbox[2] and bbox[1] <= lat <= bbox[3]
    return all(coords_in_bbox(c, bbox) for c in coords)

def parse_dbase_header(data):
    if len(data) < 32:
        raise ValueError("Invalid DBF file: too short")
    version = data[0]
    num_records = struct.unpack_from("<I", data, 4)[0]
    header_size = struct.unpack_from("<H", data, 8)[0]
    record_size = struct.unpack_from("<H", data, 10)[0]
    fields = []
    offset = 32
    while offset < header_size - 1:
        if data[offset] == 0x0D:
            break
        name_bytes = data[offset:offset + 11]
        name = name_bytes.split(b"\x00")[0].decode("ascii", errors="replace")
        field_type = chr(data[offset + 11])
        field_length = data[offset + 16]
        field_decimal = data[offset + 17]
        fields.append({
            "name": name, "type": field_type,
            "length": field_length, "decimal": field_decimal,
        })
        offset += 32
    return {"version": version, "num_records": num_records,
            "header_size": header_size, "record_size": record_size, "fields": fields}

def parse_dbase_record(record_bytes, fields):
    result = {}
    pos = 1
    for f in fields:
        raw = record_bytes[pos:pos + f["length"]]
        pos += f["length"]
        val = raw.decode("ascii", errors="replace").strip()
        if val == "":
            result[f["name"]] = None
        elif f["type"] == "N":
            if f["decimal"] > 0:
                try:
                    result[f["name"]] = float(val)
                except ValueError:
                    result[f["name"]] = val
            else:
                try:
                    result[f["name"]] = int(val)
                except ValueError:
                    result[f["name"]] = val
        elif f["type"] == "F":
            try:
                result[f["name"]] = float(val)
            except ValueError:
                result[f["name"]] = val
        elif f["type"] == "L":
            result[f["name"]] = val.upper() in ("T", "Y", "1")
        else:
            result[f["name"]] = val
    return result

def read_shapefile(path):
    base = Path(path).with_suffix("")
    shp_path = str(base) + ".shp"
    dbf_path = str(base) + ".dbf"
    prj_path = str(base) + ".prj"

    if not os.path.exists(shp_path):
        raise FileNotFoundError(f"SHP file not found: {shp_path}")

    with open(shp_path, "rb") as f:
        shp_data = f.read()

    file_code = struct.unpack_from(">I", shp_data, 0)[0]
    if file_code != 9994:
        raise ValueError(f"Invalid SHP file code: {file_code}")

    file_length = struct.unpack_from(">I", shp_data, 24)[0]
    version = struct.unpack_from("<I", shp_data, 28)[0]
    shape_type = struct.unpack_from("<I", shp_data, 32)[0]

    xmin = struct.unpack_from("<d", shp_data, 36)[0]
    ymin = struct.unpack_from("<d", shp_data, 44)[0]
    xmax = struct.unpack_from("<d", shp_data, 52)[0]
    ymax = struct.unpack_from("<d", shp_data, 60)[0]

    properties = []
    if os.path.exists(dbf_path):
        with open(dbf_path, "rb") as f:
            dbf_data = f.read()
        dbf_info = parse_dbase_header(dbf_data)
        for i in range(dbf_info["num_records"]):
            rec_offset = dbf_info["header_size"] + i * dbf_info["record_size"]
            rec_bytes = dbf_data[rec_offset:rec_offset + dbf_info["record_size"]]
            if len(rec_bytes) >= dbf_info["record_size"]:
                properties.append(parse_dbase_record(rec_bytes, dbf_info["fields"]))
            else:
                properties.append({})
    else:
        properties = [{} for _ in range(1000)]

    crs_wkt = None
    if os.path.exists(prj_path):
        with open(prj_path, "r", encoding="utf-8") as f:
            crs_wkt = f.read().strip()

    features = []
    offset = 100
    rec_idx = 0
    while offset < len(shp_data) - 8:
        rec_num = struct.unpack_from(">I", shp_data, offset)[0]
        rec_size = struct.unpack_from(">I", shp_data, offset + 4)[0]
        rec_content_size = rec_size * 2
        rec_start = offset + 8

        if rec_start + 4 > len(shp_data):
            break

        rec_shape_type = struct.unpack_from("<I", shp_data, rec_start)[0]
        if rec_shape_type == 0:
            geom = None
        elif rec_shape_type == 1:
            geom = read_point(shp_data, rec_start + 4)
        elif rec_shape_type == 3:
            geom = read_polyline(shp_data, rec_start + 4)
        elif rec_shape_type == 5:
            geom = read_polygon(shp_data, rec_start + 4)
        else:
            geom = None

        if geom is not None and rec_idx < len(properties):
            features.append({"geometry": geom, "properties": properties[rec_idx]})
        rec_idx += 1
        offset = rec_start + rec_content_size

    return {
        "type": "FeatureCollection",
        "features": features,
        "crs_wkt": crs_wkt,
        "bounds": [xmin, ymin, xmax, ymax],
    }

def read_point(data, offset):
    x = struct.unpack_from("<d", data, offset)[0]
    y = struct.unpack_from("<d", data, offset + 8)[0]
    return {"type": "Point", "coordinates": [x, y]}

def read_polyline(data, offset):
    xmin = struct.unpack_from("<d", data, offset)[0]
    ymin = struct.unpack_from("<d", data, offset + 8)[0]
    xmax = struct.unpack_from("<d", data, offset + 16)[0]
    ymax = struct.unpack_from("<d", data, offset + 24)[0]
    num_parts = struct.unpack_from("<I", data, offset + 32)[0]
    num_points = struct.unpack_from("<I", data, offset + 36)[0]
    parts = []
    for i in range(num_parts):
        parts.append(struct.unpack_from("<I", data, offset + 40 + i * 4)[0])
    points_offset = offset + 40 + num_parts * 4
    points = []
    for i in range(num_points):
        x = struct.unpack_from("<d", data, points_offset + i * 16)[0]
        y = struct.unpack_from("<d", data, points_offset + i * 16 + 8)[0]
        points.append([x, y])

    if num_parts == 1:
        return {"type": "LineString", "coordinates": points}
    else:
        lines = []
        for i in range(num_parts):
            start = parts[i]
            end = parts[i + 1] if i + 1 < num_parts else num_points
            lines.append(points[start:end])
        return {"type": "MultiLineString", "coordinates": lines}

def read_polygon(data, offset):
    xmin = struct.unpack_from("<d", data, offset)[0]
    ymin = struct.unpack_from("<d", data, offset + 8)[0]
    xmax = struct.unpack_from("<d", data, offset + 16)[0]
    ymax = struct.unpack_from("<d", data, offset + 24)[0]
    num_parts = struct.unpack_from("<I", data, offset + 32)[0]
    num_points = struct.unpack_from("<I", data, offset + 36)[0]
    parts = []
    for i in range(num_parts):
        parts.append(struct.unpack_from("<I", data, offset + 40 + i * 4)[0])
    points_offset = offset + 40 + num_parts * 4
    points = []
    for i in range(num_points):
        x = struct.unpack_from("<d", data, points_offset + i * 16)[0]
        y = struct.unpack_from("<d", data, points_offset + i * 16 + 8)[0]
        points.append([x, y])

    rings = []
    for i in range(num_parts):
        start = parts[i]
        end = parts[i + 1] if i + 1 < num_parts else num_points
        rings.append(points[start:end])

    if len(rings) == 1:
        return {"type": "Polygon", "coordinates": rings}
    else:
        return {"type": "Polygon", "coordinates": rings}

def read_geojson(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if "type" not in data:
        raise ValueError("Invalid GeoJSON: missing 'type'")
    features = []
    if data["type"] == "FeatureCollection":
        features = data.get("features", [])
    elif data["type"] == "Feature":
        features = [data]
    elif data["type"] in ("Point", "LineString", "Polygon", "MultiPoint",
                           "MultiLineString", "MultiPolygon", "GeometryCollection"):
        features = [{"type": "Feature", "geometry": data, "properties": {}}]
    else:
        raise ValueError(f"Unsupported GeoJSON type: {data['type']}")
    crs_wkt = None
    if "crs" in data:
        crs = data["crs"]
        if isinstance(crs, dict) and "properties" in crs:
            crs_wkt = crs["properties"].get("name")
    return {"type": "FeatureCollection", "features": features, "crs_wkt": crs_wkt}

def read_kml(path):
    tree = ET.parse(path)
    root = tree.getroot()
    ns = {"kml": "http://www.opengis.net/kml/2.2"}
    if root.tag == "kml":
        ns_prefix = "kml:"
    elif root.tag.endswith("}kml"):
        ns_uri = root.tag.split("}")[0][1:]
        ns = {"kml": ns_uri}
        ns_prefix = "kml:"
    else:
        ns_prefix = ""

    features = []
    for pm in root.iter():
        if pm.tag.endswith("Placemark"):
            name = ""
            desc = ""
            geom = None
            props = {}
            for child in pm:
                tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if tag == "name":
                    name = child.text or ""
                elif tag == "description":
                    desc = child.text or ""
                elif tag == "Point":
                    coords_text = child.find(".//{*}coordinates")
                    if coords_text is None:
                        coords_text = child.find("coordinates")
                    if coords_text is not None and coords_text.text:
                        parts = coords_text.text.strip().split(",")
                        geom = {"type": "Point", "coordinates": [float(parts[0]), float(parts[1])]}
                elif tag == "LineString":
                    coords_el = child.find(".//{*}coordinates")
                    if coords_el is None:
                        coords_el = child.find("coordinates")
                    if coords_el is not None and coords_el.text:
                        coords = parse_kml_coords(coords_el.text)
                        geom = {"type": "LineString", "coordinates": coords}
                elif tag == "Polygon":
                    outer = child.find(".//{*}outerBoundaryIs")
                    if outer is None:
                        outer = child.find("outerBoundaryIs")
                    if outer is not None:
                        coords_el = outer.find(".//{*}coordinates")
                        if coords_el is None:
                            coords_el = outer.find("coordinates")
                        if coords_el is not None and coords_el.text:
                            outer_coords = parse_kml_coords(coords_el.text)
                            rings = [outer_coords]
                            for inner in child.findall(".//{*}innerBoundaryIs"):
                                inner_coords_el = inner.find(".//{*}coordinates")
                                if inner_coords_el is None:
                                    inner_coords_el = inner.find("coordinates")
                                if inner_coords_el is not None and inner_coords_el.text:
                                    rings.append(parse_kml_coords(inner_coords_el.text))
                            geom = {"type": "Polygon", "coordinates": rings}
            if name:
                props["name"] = name
            if desc:
                props["description"] = desc
            if geom:
                features.append({"type": "Feature", "geometry": geom, "properties": props})

    return {"type": "FeatureCollection", "features": features, "crs_wkt": EPSG_DEFS[4326]["wkt"]}

def parse_kml_coords(text):
    coords = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = line.split(",")
        if len(parts) >= 2:
            coords.append([float(parts[0]), float(parts[1])])
    return coords

def read_gpx(path):
    tree = ET.parse(path)
    root = tree.getroot()
    ns = {}
    if root.tag.startswith("{"):
        ns_uri = root.tag.split("}")[0][1:]
        ns["gpx"] = ns_uri

    features = []

    for wpt in root.iter():
        tag = wpt.tag.split("}")[-1] if "}" in wpt.tag else wpt.tag
        if tag == "wpt":
            lat = float(wpt.get("lat", 0))
            lon = float(wpt.get("lon", 0))
            props = {}
            for child in wpt:
                ctag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if child.text and child.text.strip():
                    props[ctag] = child.text.strip()
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": props,
            })

    for rte in root.iter():
        tag = rte.tag.split("}")[-1] if "}" in rte.tag else rte.tag
        if tag == "rte":
            name = ""
            coords = []
            props = {}
            for child in rte:
                ctag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if ctag == "name" and child.text:
                    name = child.text.strip()
                elif ctag == "rtept":
                    lat = float(child.get("lat", 0))
                    lon = float(child.get("lon", 0))
                    coords.append([lon, lat])
            if name:
                props["name"] = name
            if coords:
                features.append({
                    "type": "Feature",
                    "geometry": {"type": "LineString", "coordinates": coords},
                    "properties": props,
                })

    for trk in root.iter():
        tag = trk.tag.split("}")[-1] if "}" in trk.tag else trk.tag
        if tag == "trk":
            name = ""
            segments = []
            props = {}
            for child in trk:
                ctag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if ctag == "name" and child.text:
                    name = child.text.strip()
                elif ctag == "trkseg":
                    coords = []
                    for trkpt in child:
                        pttag = trkpt.tag.split("}")[-1] if "}" in trkpt.tag else trkpt.tag
                        if pttag == "trkpt":
                            lat = float(trkpt.get("lat", 0))
                            lon = float(trkpt.get("lon", 0))
                            coords.append([lon, lat])
                    if coords:
                        segments.append(coords)
            if name:
                props["name"] = name
            if segments:
                if len(segments) == 1:
                    geom = {"type": "LineString", "coordinates": segments[0]}
                else:
                    geom = {"type": "MultiLineString", "coordinates": segments}
                features.append({"type": "Feature", "geometry": geom, "properties": props})

    return {"type": "FeatureCollection", "features": features, "crs_wkt": EPSG_DEFS[4326]["wkt"]}

def read_geopackage(path):
    conn = sqlite3.connect(path)
    conn.enable_load_extension(False)
    cursor = conn.cursor()

    cursor.execute("SELECT srs_id FROM gpkg_spatial_ref_sys WHERE srs_name LIKE '%4326%' LIMIT 1")
    row = cursor.fetchone()
    default_srs = row[0] if row else 4326

    cursor.execute("SELECT table_name, srs_id FROM gpkg_contents WHERE data_type='features'")
    tables = cursor.fetchall()
    if not tables:
        conn.close()
        raise ValueError("No feature tables found in GeoPackage")

    table_name, srs_id = tables[0]

    cursor.execute(f"PRAGMA table_info('{table_name}')")
    columns = cursor.fetchall()
    col_names = [c[1] for c in columns if c[1] != "geom"]
    geom_col = None
    for c in columns:
        if c[1] == "geom" or c[1].lower().endswith("geom"):
            geom_col = c[1]
            break
    if geom_col is None:
        geom_col = "geom"

    cursor.execute(f"SELECT * FROM '{table_name}'")
    rows = cursor.fetchall()
    col_map = {c[1]: i for i, c in enumerate(columns)}

    features = []
    for row in rows:
        geom = None
        props = {}

        for cn in col_names:
            idx = col_map.get(cn)
            if idx is not None and idx < len(row):
                props[cn] = row[idx]

        geom_idx = col_map.get(geom_col)
        if geom_idx is not None and geom_idx < len(row):
            geom_blob = row[geom_idx]
            if geom_blob and isinstance(geom_blob, bytes):
                geom = parse_gpkg_geom_blob(geom_blob)

        if geom:
            features.append({"type": "Feature", "geometry": geom, "properties": props})

    conn.close()
    crs_wkt = None
    for key, val in EPSG_DEFS.items():
        if key == srs_id or key == default_srs:
            crs_wkt = val["wkt"]
            break
    if not crs_wkt:
        crs_wkt = EPSG_DEFS[4326]["wkt"]

    return {"type": "FeatureCollection", "features": features, "crs_wkt": crs_wkt}

def parse_gpkg_geom_blob(blob):
    if len(blob) < 8:
        return None
    magic = blob[0:2]
    if magic != b"GP":
        return None
    version = blob[2]
    flags = blob[3]
    endian = flags & 0x01
    if endian == 0:
        endian_char = ">"
    else:
        endian_char = "<"
    srs_id = struct.unpack_from(endian_char + "i", blob, 4)[0]

    envelope_indicator = (flags >> 1) & 0x07
    header_size = 8
    if envelope_indicator == 1:
        header_size = 32
    elif envelope_indicator == 2:
        header_size = 32
    elif envelope_indicator == 3:
        header_size = 56

    if header_size + 5 > len(blob):
        return None

    # WKB starts at header_size: 1 byte order + 4 type + coordinates
    return parse_wkb_geometry(blob, header_size, endian_char)

def parse_wkb_geometry(data, offset, endian_char):
    if offset + 5 > len(data):
        return None
    # Skip WKB byte-order mark (1 byte) and read geometry type (4 bytes)
    wkb_endian = data[offset]
    offset += 1
    if wkb_endian == 0:
        endian_char = ">"
    elif wkb_endian == 1:
        endian_char = "<"
    geom_type = struct.unpack_from(endian_char + "I", data, offset)[0]
    offset += 4

    wkb_type = geom_type & 0xFF

    if wkb_type == 1:
        x = struct.unpack_from(endian_char + "d", data, offset)[0]
        y = struct.unpack_from(endian_char + "d", data, offset + 8)[0]
        return {"type": "Point", "coordinates": [x, y]}
    elif wkb_type == 2:
        num_points = struct.unpack_from(endian_char + "I", data, offset)[0]
        offset += 4
        coords = []
        for i in range(num_points):
            x = struct.unpack_from(endian_char + "d", data, offset)[0]
            y = struct.unpack_from(endian_char + "d", data, offset + 8)[0]
            coords.append([x, y])
            offset += 16
        return {"type": "LineString", "coordinates": coords}
    elif wkb_type == 3:
        num_rings = struct.unpack_from(endian_char + "I", data, offset)[0]
        offset += 4
        rings = []
        for r in range(num_rings):
            num_points = struct.unpack_from(endian_char + "I", data, offset)[0]
            offset += 4
            ring = []
            for i in range(num_points):
                x = struct.unpack_from(endian_char + "d", data, offset)[0]
                y = struct.unpack_from(endian_char + "d", data, offset + 8)[0]
                ring.append([x, y])
                offset += 16
            rings.append(ring)
        return {"type": "Polygon", "coordinates": rings}
    return None

def read_csv(path):
    features = []
    lat_col = lon_col = None

    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        for h in headers:
            hl = h.lower().strip()
            if hl in ("lat", "latitude", "y"):
                lat_col = h
            if hl in ("lon", "lng", "longitude", "x"):
                lon_col = h

        if lat_col is None or lon_col is None:
            for h in headers:
                hl = h.lower().strip()
                if "lat" in hl:
                    lat_col = h
                if "lon" in hl or "lng" in hl:
                    lon_col = h

        if lat_col is None or lon_col is None:
            raise ValueError("Could not find lat/lon columns in CSV")

        for row in reader:
            try:
                lat = float(row[lat_col])
                lon = float(row[lon_col])
            except (ValueError, TypeError):
                continue
            props = {k: v for k, v in row.items() if k not in (lat_col, lon_col)}
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": props,
            })

    return {"type": "FeatureCollection", "features": features, "crs_wkt": EPSG_DEFS[4326]["wkt"]}

def read_input(path, format_hint=None):
    if format_hint and format_hint != "auto":
        # User explicitly told us the format; trust it.
        fmt = format_hint
    else:
        ext = Path(path).suffix.lower()
        fmt = FORMAT_EXTENSIONS.get(ext)
    if fmt is None:
        raise ValueError(f"Unsupported input format: {ext if format_hint is None else format_hint}")

    if fmt == "shp":
        return read_shapefile(path)
    elif fmt == "geojson":
        return read_geojson(path)
    elif fmt == "kml":
        return read_kml(path)
    elif fmt == "gpx":
        return read_gpx(path)
    elif fmt == "gpkg":
        return read_geopackage(path)
    elif fmt == "csv":
        return read_csv(path)
    else:
        raise ValueError(f"Unsupported format: {fmt}")

def apply_filters(data, fields=None, bbox=None, precision=6, target_crs=None, source_epsg=4326, target_epsg=4326):
    features = data["features"]
    if bbox:
        filtered = []
        for feat in features:
            geom = feat.get("geometry")
            if geom and geometry_intersects_bbox(geom, bbox):
                if target_crs:
                    feat["geometry"] = transform_geometry(geom, source_epsg, target_epsg)
                filtered.append(feat)
        features = filtered
    elif target_crs:
        for feat in features:
            if feat.get("geometry"):
                feat["geometry"] = transform_geometry(feat["geometry"], source_epsg, target_epsg)

    if precision is not None:
        for feat in features:
            if feat.get("geometry"):
                feat["geometry"] = round_geometry(feat["geometry"], precision)

    if fields:
        field_list = [f.strip() for f in fields.split(",")]
        for feat in features:
            if feat.get("properties"):
                feat["properties"] = {k: v for k, v in feat["properties"].items() if k in field_list}

    data["features"] = features
    return data

def geometry_intersects_bbox(geom, bbox):
    coords = geom.get("coordinates", [])
    gtype = geom.get("type", "")
    if gtype == "Point":
        return coords_in_bbox(coords, bbox)
    elif gtype in ("LineString", "MultiPoint"):
        return any(coords_in_bbox(c, bbox) for c in coords)
    elif gtype in ("Polygon", "MultiLineString"):
        for ring_or_line in coords:
            if any(coords_in_bbox(c, bbox) for c in ring_or_line):
                return True
        return False
    elif gtype == "MultiPolygon":
        for polygon in coords:
            for ring in polygon:
                if any(coords_in_bbox(c, bbox) for c in ring):
                    return True
        return False
    elif gtype == "GeometryCollection":
        return any(geometry_intersects_bbox(g, bbox) for g in geom.get("geometries", []))
    return True

def transform_geometry(geom, from_epsg, to_epsg):
    if not geom:
        return geom
    gtype = geom.get("type", "")
    coords = geom.get("coordinates")

    if gtype == "Point":
        x, y = transform_point(coords[0], coords[1], from_epsg, to_epsg)
        return {"type": "Point", "coordinates": [x, y]}
    elif gtype == "LineString":
        new_coords = [list(transform_point(c[0], c[1], from_epsg, to_epsg)) for c in coords]
        return {"type": "LineString", "coordinates": new_coords}
    elif gtype == "Polygon":
        new_rings = []
        for ring in coords:
            new_rings.append([list(transform_point(c[0], c[1], from_epsg, to_epsg)) for c in ring])
        return {"type": "Polygon", "coordinates": new_rings}
    elif gtype == "MultiPoint":
        return {"type": "MultiPoint",
                "coordinates": [list(transform_point(c[0], c[1], from_epsg, to_epsg)) for c in coords]}
    elif gtype == "MultiLineString":
        return {"type": "MultiLineString",
                "coordinates": [[list(transform_point(c[0], c[1], from_epsg, to_epsg)) for c in line] for line in coords]}
    elif gtype == "MultiPolygon":
        return {"type": "MultiPolygon",
                "coordinates": [[[list(transform_point(c[0], c[1], from_epsg, to_epsg)) for c in ring] for ring in poly] for poly in coords]}
    return geom

def round_geometry(geom, precision):
    if not geom:
        return geom
    gtype = geom.get("type", "")
    coords = geom.get("coordinates")

    if gtype == "Point":
        return {"type": "Point", "coordinates": round_coords(coords, precision)}
    elif gtype == "LineString":
        return {"type": "LineString", "coordinates": round_coords(coords, precision)}
    elif gtype == "Polygon":
        return {"type": "Polygon", "coordinates": round_coords(coords, precision)}
    elif gtype == "MultiPoint":
        return {"type": "MultiPoint", "coordinates": round_coords(coords, precision)}
    elif gtype == "MultiLineString":
        return {"type": "MultiLineString", "coordinates": round_coords(coords, precision)}
    elif gtype == "MultiPolygon":
        return {"type": "MultiPolygon", "coordinates": round_coords(coords, precision)}
    return geom

def write_geojson(data, path):
    output = {
        "type": "FeatureCollection",
        "features": data["features"],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

def write_kml(data, path):
    kml_ns = "http://www.opengis.net/kml/2.2"
    ET.register_namespace("", kml_ns)
    kml = ET.Element("kml", xmlns=kml_ns)
    doc = ET.SubElement(kml, "Document")
    for feat in data["features"]:
        geom = feat.get("geometry", {})
        props = feat.get("properties", {})
        pm = ET.SubElement(doc, "Placemark")
        if "name" in props:
            name_el = ET.SubElement(pm, "name")
            name_el.text = str(props["name"])
        for k, v in props.items():
            if k != "name" and v is not None:
                ext_data = ET.SubElement(pm, "ExtendedData")
                data_el = ET.SubElement(ext_data, "Data", name=k)
                val_el = ET.SubElement(data_el, "value")
                val_el.text = str(v)
        write_kml_geometry(pm, geom)
    tree = ET.ElementTree(kml)
    tree.write(path, encoding="utf-8", xml_declaration=True)

def write_kml_geometry(parent, geom):
    gtype = geom.get("type", "")
    coords = geom.get("coordinates", [])
    if gtype == "Point":
        point = ET.SubElement(parent, "Point")
        coords_el = ET.SubElement(point, "coordinates")
        coords_el.text = f"{coords[0]},{coords[1]}"
    elif gtype == "LineString":
        ls = ET.SubElement(parent, "LineString")
        coords_el = ET.SubElement(ls, "coordinates")
        lines = [f"{c[0]},{c[1]}" for c in coords]
        coords_el.text = "\n".join(lines)
    elif gtype == "Polygon":
        poly = ET.SubElement(parent, "Polygon")
        for i, ring in enumerate(coords):
            if i == 0:
                outer = ET.SubElement(poly, "outerBoundaryIs")
                lr = ET.SubElement(outer, "LinearRing")
            else:
                inner = ET.SubElement(poly, "innerBoundaryIs")
                lr = ET.SubElement(inner, "LinearRing")
            coords_el = ET.SubElement(lr, "coordinates")
            lines = [f"{c[0]},{c[1]}" for c in ring]
            coords_el.text = "\n".join(lines)

def write_gpx(data, path):
    gpx_ns = "http://www.topografix.com/GPX/1/1"
    ET.register_namespace("", gpx_ns)
    gpx = ET.Element("gpx", xmlns=gpx_ns, version="1.1", creator="vector-convert")
    for feat in data["features"]:
        geom = feat.get("geometry", {})
        props = feat.get("properties", {})
        gtype = geom.get("type", "")
        coords = geom.get("coordinates", [])
        if gtype == "Point":
            wpt = ET.SubElement(gpx, "wpt", lat=str(coords[1]), lon=str(coords[0]))
            if "name" in props:
                name_el = ET.SubElement(wpt, "name")
                name_el.text = str(props["name"])
        elif gtype == "LineString":
            rte = ET.SubElement(gpx, "rte")
            if "name" in props:
                name_el = ET.SubElement(rte, "name")
                name_el.text = str(props["name"])
            for c in coords:
                ET.SubElement(rte, "rtept", lat=str(c[1]), lon=str(c[0]))
    tree = ET.ElementTree(gpx)
    tree.write(path, encoding="utf-8", xml_declaration=True)

def write_csv(data, path):
    features = data["features"]
    if not features:
        with open(path, "w", newline="", encoding="utf-8") as f:
            f.write("longitude,latitude\n")
        return

    all_props = set()
    for feat in features:
        all_props.update(feat.get("properties", {}).keys())

    fieldnames = ["longitude", "latitude"] + sorted(all_props)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for feat in features:
            geom = feat.get("geometry", {})
            coords = geom.get("coordinates", [None, None])
            props = feat.get("properties", {})
            row = {"longitude": coords[0], "latitude": coords[1]}
            row.update(props)
            writer.writerow(row)

def write_shapefile(data, path):
    features = data["features"]
    base = Path(path).with_suffix("")
    shp_path = str(base) + ".shp"
    shx_path = str(base) + ".shx"
    dbf_path = str(base) + ".dbf"
    prj_path = str(base) + ".prj"

    determine_geom_type = "Point"
    for feat in features:
        geom = feat.get("geometry", {})
        if geom.get("type") in ("LineString", "MultiLineString"):
            determine_geom_type = "LineString"
            break
        if geom.get("type") in ("Polygon", "MultiPolygon"):
            determine_geom_type = "Polygon"
            break

    shape_type = {"Point": 1, "LineString": 3, "Polygon": 5}.get(determine_geom_type, 1)

    all_points = []
    for feat in features:
        geom = feat.get("geometry", {})
        coords = geom.get("coordinates", [])
        if geom.get("type") == "Point":
            all_points.append(coords)
        elif geom.get("type") in ("LineString", "Polygon"):
            for ring in coords:
                if isinstance(ring[0], (list, tuple)):
                    for c in ring:
                        all_points.append(c)
                else:
                    all_points.append(ring)

    if all_points:
        xs = [p[0] for p in all_points]
        ys = [p[1] for p in all_points]
        xmin, xmax = min(xs), max(xs)
        ymin, ymax = min(ys), max(ys)
    else:
        xmin = xmax = ymin = ymax = 0.0

    all_fields = set()
    for feat in features:
        all_fields.update(feat.get("properties", {}).keys())
    field_names = sorted(all_fields)

    dbf_fields = []
    for fn in field_names:
        max_len = 1
        for feat in features:
            val = feat.get("properties", {}).get(fn)
            if val is not None:
                max_len = max(max_len, len(str(val)))
        dbf_fields.append({"name": fn, "type": "C", "length": min(max_len + 1, 254), "decimal": 0})

    shp_records = []
    shx_records = []
    current_offset = 50

    for i, feat in enumerate(features):
        geom = feat.get("geometry", {})
        gtype = geom.get("type", "")
        coords = geom.get("coordinates", [])

        rec_content = struct.pack("<I", shape_type)

        if gtype == "Point":
            rec_content += struct.pack("<dd", coords[0], coords[1])
        elif gtype == "LineString":
            num_parts = 1
            num_points = len(coords)
            rec_content += struct.pack("<dddd", xmin, ymin, xmax, ymax)
            rec_content += struct.pack("<II", num_parts, num_points)
            rec_content += struct.pack("<I", 0)
            for c in coords:
                rec_content += struct.pack("<dd", c[0], c[1])
        elif gtype == "Polygon":
            num_parts = len(coords)
            num_points = sum(len(ring) for ring in coords)
            rec_content += struct.pack("<dddd", xmin, ymin, xmax, ymax)
            rec_content += struct.pack("<II", num_parts, num_points)
            pt_offset = 0
            for ring in coords:
                rec_content += struct.pack("<I", pt_offset)
                pt_offset += len(ring)
            for ring in coords:
                for c in ring:
                    rec_content += struct.pack("<dd", c[0], c[1])
        elif gtype == "MultiLineString":
            num_parts = len(coords)
            num_points = sum(len(line) for line in coords)
            rec_content += struct.pack("<dddd", xmin, ymin, xmax, ymax)
            rec_content += struct.pack("<II", num_parts, num_points)
            pt_offset = 0
            for line in coords:
                rec_content += struct.pack("<I", pt_offset)
                pt_offset += len(line)
            for line in coords:
                for c in line:
                    rec_content += struct.pack("<dd", c[0], c[1])
        elif gtype == "MultiPolygon":
            all_rings = []
            for poly in coords:
                all_rings.extend(poly)
            num_parts = len(all_rings)
            num_points = sum(len(ring) for ring in all_rings)
            rec_content += struct.pack("<dddd", xmin, ymin, xmax, ymax)
            rec_content += struct.pack("<II", num_parts, num_points)
            pt_offset = 0
            for ring in all_rings:
                rec_content += struct.pack("<I", pt_offset)
                pt_offset += len(ring)
            for ring in all_rings:
                for c in ring:
                    rec_content += struct.pack("<dd", c[0], c[1])
        else:
            rec_content += struct.pack("<dd", 0.0, 0.0)

        rec_size_words = len(rec_content) // 2
        shp_records.append(struct.pack(">II", i + 1, rec_size_words) + rec_content)
        shx_records.append(struct.pack(">II", current_offset, rec_size_words))
        current_offset += 4 + rec_size_words

    shp_file_size_words = 50 + sum(len(r) // 2 for r in shp_records)
    shp_header = struct.pack(">I", 9994)
    shp_header += b"\x00" * 20
    shp_header += struct.pack(">I", shp_file_size_words)
    shp_header += struct.pack("<I", 1000)
    shp_header += struct.pack("<I", shape_type)
    shp_header += struct.pack("<dddd", xmin, ymin, xmax, ymax)
    shp_header += struct.pack("<dddd", 0, 0, 0, 0)

    with open(shp_path, "wb") as f:
        f.write(shp_header)
        for rec in shp_records:
            f.write(rec)

    shx_file_size_words = 50 + len(features) * 4
    shx_header = struct.pack(">I", 9994)
    shx_header += b"\x00" * 20
    shx_header += struct.pack(">I", shx_file_size_words)
    shx_header += struct.pack("<I", 1000)
    shx_header += struct.pack("<I", shape_type)
    shx_header += struct.pack("<dddd", xmin, ymin, xmax, ymax)
    shx_header += struct.pack("<dddd", 0, 0, 0, 0)

    with open(shx_path, "wb") as f:
        f.write(shx_header)
        for rec in shx_records:
            f.write(rec)

    write_dbf(dbf_path, features, dbf_fields)

    if data.get("crs_wkt"):
        with open(prj_path, "w", encoding="utf-8") as f:
            f.write(data["crs_wkt"])

def write_dbf(path, features, dbf_fields):
    num_records = len(features)
    header_size = 32 + len(dbf_fields) * 32 + 1
    record_size = 1 + sum(f["length"] for f in dbf_fields)

    # Set language driver byte (offset 29) to 0xC8 (Windows ANSI) to support
    # non-ASCII field names and values (e.g. Chinese characters)
    header = struct.pack("<BBBBIHH", 3, 0, 0, 0, num_records, header_size, record_size)
    header += b"\x00" * 17  # reserved bytes 12-28
    header += b"\xC8"       # byte 29: language driver = Windows ANSI
    header += b"\x00" * 2   # reserved bytes 30-31

    for f in dbf_fields:
        name_bytes = f["name"][:10].encode("utf-8", errors="replace").ljust(11, b"\x00")
        header += name_bytes
        header += f["type"].encode("ascii")
        header += b"\x00" * 4
        header += struct.pack("<BB", f["length"], f["decimal"])
        header += b"\x00" * 14

    header += b"\x0D"

    with open(path, "wb") as f:
        f.write(header)
        for feat in features:
            props = feat.get("properties", {})
            rec = b" "
            for field in dbf_fields:
                val = props.get(field["name"])
                if val is None:
                    val_str = ""
                else:
                    val_str = str(val)
                val_bytes = val_str.encode("utf-8", errors="replace")[:field["length"]]
                val_bytes = val_bytes.ljust(field["length"], b" ")
                rec += val_bytes
            f.write(rec)

def write_geopackage(data, path):
    if os.path.exists(path):
        os.remove(path)
    conn = sqlite3.connect(path)
    cursor = conn.cursor()

    cursor.execute("""CREATE TABLE gpkg_spatial_ref_sys (
        srs_name TEXT, srs_id INTEGER PRIMARY KEY, organization TEXT,
        organization_coordsys_id INTEGER, definition TEXT, description TEXT
    )""")
    cursor.execute("INSERT INTO gpkg_spatial_ref_sys VALUES (?, ?, ?, ?, ?, ?)",
                   ("WGS 84", 4326, "EPSG", 4326, EPSG_DEFS[4326]["wkt"], ""))
    cursor.execute("INSERT INTO gpkg_spatial_ref_sys VALUES (?, ?, ?, ?, ?, ?)",
                   ("Undefined Cartesian", -1, "NONE", -1, "", ""))
    cursor.execute("INSERT INTO gpkg_spatial_ref_sys VALUES (?, ?, ?, ?, ?, ?)",
                   ("Undefined Geographic", 0, "NONE", 0, "", ""))

    cursor.execute("""CREATE TABLE gpkg_contents (
        table_name TEXT PRIMARY KEY, data_type TEXT, identifier TEXT,
        description TEXT, last_change DATETIME, min_x REAL, min_y REAL,
        max_x REAL, max_y REAL, srs_id INTEGER
    )""")

    cursor.execute("""CREATE TABLE gpkg_geometry_columns (
        table_name TEXT, column_name TEXT, geometry_type_name TEXT,
        srs_id INTEGER, z INTEGER, m INTEGER,
        CONSTRAINT pk_geom_cols PRIMARY KEY (table_name, column_name)
    )""")

    features = data["features"]
    all_fields = set()
    for feat in features:
        all_fields.update(feat.get("properties", {}).keys())
    field_names = sorted(all_fields)

    col_defs = ["id INTEGER PRIMARY KEY AUTOINCREMENT", "geom BLOB"]
    for fn in field_names:
        col_defs.append(f'"{fn}" TEXT')
    create_sql = f"CREATE TABLE features ({', '.join(col_defs)})"
    cursor.execute(create_sql)

    for feat in features:
        geom = feat.get("geometry", {})
        geom_blob = write_wkb_geometry(geom)
        props = feat.get("properties", {})
        quoted_fields = ['"' + fn + '"' for fn in field_names]
        placeholders = ["?", "?"] + ["?" for _ in field_names]
        insert_sql = "INSERT INTO features (id, geom, " + ", ".join(quoted_fields) + ") VALUES (" + ", ".join(placeholders) + ")"
        values = [None, geom_blob] + [str(props.get(fn, "")) for fn in field_names]
        cursor.execute(insert_sql, values)

    cursor.execute("INSERT INTO gpkg_contents VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                   ("features", "features", "features", "", "2024-01-01T00:00:00.000Z",
                    -180, -90, 180, 90, 4326))
    cursor.execute("INSERT INTO gpkg_geometry_columns VALUES (?, ?, ?, ?, ?, ?)",
                   ("features", "geom", "GEOMETRY", 4326, 0, 0))

    conn.commit()
    conn.close()

def write_wkb_geometry(geom):
    gtype = geom.get("type", "")
    coords = geom.get("coordinates", [])

    buf = io.BytesIO()
    # GeoPackage envelope header
    buf.write(b"GP")
    buf.write(struct.pack("<B", 0))  # version
    buf.write(struct.pack("<B", 0x01))  # flags: little-endian, no envelope
    buf.write(struct.pack("<i", 4326))  # srs_id
    # WKB geometry
    buf.write(struct.pack("<B", 1))

    type_map = {"Point": 1, "LineString": 2, "Polygon": 3,
                "MultiPoint": 4, "MultiLineString": 5, "MultiPolygon": 6}
    wkb_type = type_map.get(gtype, 0)
    buf.write(struct.pack("<I", wkb_type))

    if gtype == "Point":
        buf.write(struct.pack("<dd", coords[0], coords[1]))
    elif gtype == "LineString":
        buf.write(struct.pack("<I", len(coords)))
        for c in coords:
            buf.write(struct.pack("<dd", c[0], c[1]))
    elif gtype == "Polygon":
        buf.write(struct.pack("<I", len(coords)))
        for ring in coords:
            buf.write(struct.pack("<I", len(ring)))
            for c in ring:
                buf.write(struct.pack("<dd", c[0], c[1]))
    elif gtype == "MultiLineString":
        buf.write(struct.pack("<I", len(coords)))
        for line in coords:
            buf.write(struct.pack("<B", 1))
            buf.write(struct.pack("<I", 2))
            buf.write(struct.pack("<I", len(line)))
            for c in line:
                buf.write(struct.pack("<dd", c[0], c[1]))
    elif gtype == "MultiPolygon":
        buf.write(struct.pack("<I", len(coords)))
        for poly in coords:
            buf.write(struct.pack("<B", 1))
            buf.write(struct.pack("<I", 3))
            buf.write(struct.pack("<I", len(poly)))
            for ring in poly:
                buf.write(struct.pack("<I", len(ring)))
                for c in ring:
                    buf.write(struct.pack("<dd", c[0], c[1]))

    return buf.getvalue()

def write_output(data, path, fmt):
    writers = {
        "geojson": write_geojson,
        "kml": write_kml,
        "gpx": write_gpx,
        "csv": write_csv,
        "shp": write_shapefile,
        "gpkg": write_geopackage,
    }
    writer = writers.get(fmt)
    if writer is None:
        raise ValueError(f"Unsupported output format: {fmt}")
    writer(data, path)

def get_info(data):
    features = data["features"]
    num_features = len(features)
    geom_types = set()
    all_fields = set()
    for feat in features:
        geom = feat.get("geometry", {})
        if geom:
            geom_types.add(geom.get("type", "Unknown"))
        all_fields.update(feat.get("properties", {}).keys())

    xs = []
    ys = []
    for feat in features:
        geom = feat.get("geometry", {})
        coords = geom.get("coordinates", [])
        if geom.get("type") == "Point":
            xs.append(coords[0])
            ys.append(coords[1])
        elif geom.get("type") in ("LineString", "Polygon"):
            for ring in coords:
                if isinstance(ring[0], (list, tuple)):
                    for c in ring:
                        xs.append(c[0])
                        ys.append(c[1])
                else:
                    xs.append(ring[0])
                    ys.append(ring[1])

    bounds = None
    if xs and ys:
        bounds = [min(xs), min(ys), max(xs), max(ys)]

    return {
        "feature_count": num_features,
        "geometry_types": sorted(geom_types),
        "fields": sorted(all_fields),
        "crs": data.get("crs_wkt", "Unknown"),
        "bounds": bounds,
    }

def convert(input_path, output_path, output_format, crs=None, precision=6, fields=None, bbox=None, info_only=False, input_format=None):
    data = read_input(input_path, format_hint=input_format)

    if info_only:
        return get_info(data)

    source_epsg = 4326
    target_epsg = None
    if crs:
        try:
            target_epsg = int(crs.replace("EPSG:", "").strip())
        except ValueError:
            target_epsg = 4326

    if bbox and len(bbox) == 4:
        bbox = [float(b) for b in bbox]
    else:
        bbox = None

    data = apply_filters(data, fields=fields, bbox=bbox, precision=precision,
                         target_crs=target_epsg is not None,
                         source_epsg=source_epsg, target_epsg=target_epsg or source_epsg)

    if output_format is None:
        ext = Path(output_path).suffix.lower()
        output_format = FORMAT_EXTENSIONS.get(ext, "geojson")

    write_output(data, output_path, output_format)
    return {"output": output_path, "format": output_format, "features": len(data["features"])}

def main():
    parser = argparse.ArgumentParser(
        description="Vector data format converter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Supported formats: SHP, GeoJSON, KML, GPX, GeoPackage, CSV",
    )
    parser.add_argument("input", help="Input file path")
    parser.add_argument("-o", "--output", help="Output file path")
    parser.add_argument(
        "--format",
        choices=["auto"] + SUPPORTED_FORMATS,
        default="auto",
        help="Input format. 'auto' (default) detects from the file extension; "
             "set explicitly when the extension is missing or wrong "
             "(e.g. --format geojson for a .dat file containing GeoJSON).",
    )
    parser.add_argument("--to", choices=SUPPORTED_FORMATS, help="Output format")
    parser.add_argument("--crs", help="Target CRS (e.g., EPSG:4326, EPSG:3857)")
    parser.add_argument("--precision", type=int, default=6, help="Coordinate decimal places")
    parser.add_argument("--fields", help="Comma-separated field names to keep")
    parser.add_argument("--bbox", nargs=4, type=float, metavar=("minLon", "minLat", "maxLon", "maxLat"),
                        help="Clip to bounding box")
    parser.add_argument("--info", action="store_true", help="Show input file info")
    parser.add_argument("--batch-dir",
                        help="Convert all supported files in this directory; "
                             "outputs go to <dir>/converted/<basename>.<new_ext>")
    parser.add_argument("--batch-format", choices=SUPPORTED_FORMATS,
                        help="Target format for --batch-dir")
    parser.add_argument("--qa", action="store_true",
                        help="Write a QA summary JSON next to the output")

    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"Error: Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    # Batch mode: convert all supported files in a directory
    if args.batch_dir:
        if not args.batch_format:
            print("Error: --batch-dir requires --batch-format", file=sys.stderr)
            sys.exit(1)
        in_dir = Path(args.batch_dir)
        if not in_dir.is_dir():
            print(f"Error: not a directory: {args.batch_dir}", file=sys.stderr)
            sys.exit(1)
        out_dir = in_dir / "converted"
        out_dir.mkdir(parents=True, exist_ok=True)
        ext_map = {"geojson": ".geojson", "shp": ".shp", "kml": ".kml",
                   "gpx": ".gpx", "gpkg": ".gpkg", "csv": ".csv"}
        out_ext = ext_map[args.batch_format]
        qa_files = []
        for src in in_dir.iterdir():
            if not src.is_file():
                continue
            try:
                out = out_dir / (src.stem + out_ext)
                convert(str(src), str(out), args.batch_format,
                        target_crs=args.crs, precision=args.precision,
                        keep_fields=args.fields, clip_bbox=args.bbox)
                qa_files.append(str(out))
                print(f"  {src.name} -> {out.relative_to(in_dir)}")
            except Exception as e:
                print(f"  SKIP {src.name}: {e}", file=sys.stderr)
        if args.qa and qa_files:
            qa_path = out_dir / "batch.qa.json"
            with open(qa_path, "w", encoding="utf-8") as f:
                json.dump({"batch_dir": str(in_dir), "target_format": args.batch_format,
                           "outputs": qa_files, "count": len(qa_files)}, f,
                          ensure_ascii=False, indent=2)
            print(f"QA: {qa_path}")
        return 0

    try:
        if args.info:
            info = convert(args.input, None, None, info_only=True,
                           input_format=args.format)
            print(json.dumps(info, indent=2))
        else:
            if args.output is None:
                ext_map = {"geojson": ".geojson", "shp": ".shp", "kml": ".kml",
                           "gpx": ".gpx", "gpkg": ".gpkg", "csv": ".csv"}
                out_ext = ext_map.get(args.to, ".geojson")
                args.output = str(Path(args.input).with_suffix("")) + "_converted" + out_ext

            result = convert(args.input, args.output, args.to,
                             crs=args.crs, precision=args.precision,
                             fields=args.fields, bbox=args.bbox,
                             input_format=args.format)
            print(f"Converted {result['features']} features to {result['format'].upper()}")
            print(f"Output: {result['output']}")
            if getattr(args, "qa", False):
                qa = {
                    "input": args.input,
                    "output": result["output"],
                    "format": result["format"],
                    "feature_count": result["features"],
                    "crs": args.crs,
                    "bbox": args.bbox,
                    "fields_kept": args.fields,
                    "precision": args.precision,
                }
                qa_path = str(Path(args.output).with_suffix("")) + ".qa.json"
                with open(qa_path, "w", encoding="utf-8") as f:
                    json.dump(qa, f, ensure_ascii=False, indent=2)
                print(f"QA: {qa_path}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
