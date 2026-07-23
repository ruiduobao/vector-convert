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
