---
name: vector-convert
display_name: Vector Format Converter
version: 0.1.0
author: rui.duobao
license: MIT-0
description: |
  Convert between vector GIS formats using only Python standard library.
  Supports Shapefile, GeoJSON, KML, GPX, GeoPackage, and CSV.
  Zero external dependencies.
runtime: python>=3.8
tags: [gis, vector, shapefile, geojson, kml, gpx, gpkg, csv, zero-dependency]
---

# Vector Format Converter

Convert between vector GIS formats using only Python standard library.

## Supported Formats

| Format | Extension | Read | Write |
|--------|-----------|------|-------|
| Shapefile | .shp | Yes | Yes |
| GeoJSON | .geojson/.json | Yes | Yes |
| KML | .kml | Yes | Yes |
| GPX | .gpx | Yes | Yes |
| GeoPackage | .gpkg | Yes | Yes |
| CSV | .csv | Yes | Yes |

## Installation

Zero external dependencies. Requires Python 3.8+.

## Usage

### Convert between formats
```bash
python vector-convert.py input.shp --to geojson -o output.geojson
python vector-convert.py input.geojson --to shp -o output.shp
python vector-convert.py input.kml --to gpkg -o output.gpkg
```

### Show file info
```bash
python vector-convert.py input.shp --info
```

### CRS transformation
```bash
python vector-convert.py input.shp --to geojson --crs EPSG:3857
```

### Coordinate precision
```bash
python vector-convert.py input.geojson --to csv --precision 4
```

### Filter fields
```bash
python vector-convert.py input.geojson --to csv --fields name,type,population
```

### Clip to bounding box
```bash
python vector-convert.py input.shp --to geojson --bbox -180 -90 180 90
```

## Features

- **Auto-detect**: Input format detected from file extension
- **CRS transform**: Convert between EPSG codes (4326, 3857, etc.)
- **Precision control**: Round coordinates to N decimal places
- **Field filtering**: Keep only specified property fields
- **Bbox clipping**: Filter features intersecting a bounding box
- **Info mode**: Display feature count, CRS, bounds, and field names
- **Binary parsing**: Reads SHP/DBF/SHX/PRJ files manually
- **GeoPackage**: Reads/writes SQLite-based GPKG format

## Testing

```bash
pytest tests/ -v
```

## License

MIT-0 (No Attribution)

---

## 中文说明

矢量 GIS 格式转换工具，仅使用 Python 标准库，零外部依赖。

### 支持的格式

| 格式 | 扩展名 | 读 | 写 |
|---|---|---|---|
| Shapefile | .shp | 是 | 是 |
| GeoJSON | .geojson/.json | 是 | 是 |
| KML | .kml | 是 | 是 |
| GPX | .gpx | 是 | 是 |
| GeoPackage | .gpkg | 是 | 是 |
| CSV | .csv | 是 | 是 |

### 使用方法

```bash
# 格式转换
python vector-convert.py input.shp --to geojson -o output.geojson
python vector-convert.py input.geojson --to shp -o output.shp
python vector-convert.py input.kml --to gpkg -o output.gpkg

# 查看文件信息
python vector-convert.py input.shp --info

# CRS 转换
python vector-convert.py input.shp --to geojson --crs EPSG:3857

# 坐标精度控制
python vector-convert.py input.geojson --to csv --precision 4

# 字段筛选
python vector-convert.py input.geojson --to csv --fields name,type,population

# 按边界框裁剪
python vector-convert.py input.shp --to geojson --bbox -180 -90 180 90
```

### 特性

- 自动检测输入格式（按扩展名）
- 支持 CRS 转换（EPSG:4326、EPSG:3857 等）
- 坐标精度控制
- 字段筛选
- 边界框裁剪
- 手动解析 SHP/DBF/SHX/PRJ 文件
- 支持 GeoPackage（SQLite 格式）
