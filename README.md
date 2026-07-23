# Vector Format Converter

Convert between vector GIS formats using only Python standard library.

## Supported Formats

| Format | Read | Write |
|--------|------|-------|
| Shapefile (.shp) | ✅ | ✅ |
| GeoJSON | ✅ | ✅ |
| KML | ✅ | ✅ |
| GPX | ✅ | ✅ |
| GeoPackage (.gpkg) | ✅ | ✅ |
| CSV (lat/lon) | ✅ | ✅ |

## Features

- **Auto-detect** input format from file extension
- **CRS transformation** via EPSG codes (4326, 3857, etc.)
- **Coordinate precision** control
- **Field/property filtering**
- **Bounding box clipping**
- **File info** display (feature count, CRS, bounds, fields)
- **Zero dependencies** - uses only Python standard library
- **Binary parsing** - reads SHP/DBF/SHX/PRJ files manually

## Usage

```bash
python vector-convert.py input.shp --to geojson -o output.geojson
python vector-convert.py input.geojson --info
python vector-convert.py input.shp --to csv --crs EPSG:3857 --precision 4 --fields name,type
python vector-convert.py input.geojson --to shp --bbox -180 -90 180 90
```

## Testing

```bash
pytest tests/ -v
```

## License

MIT-0
