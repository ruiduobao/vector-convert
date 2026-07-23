"""Tests for CLI argument parsing and command-line interface."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


def run_cli(args, cwd=None):
    """Run vector-convert.py CLI."""
    module_path = Path(__file__).parent.parent / "vector-convert.py"
    cmd = [sys.executable, str(module_path)] + args
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    return result


class TestCLI:
    def test_no_args(self):
        result = run_cli([])
        assert result.returncode != 0
        assert "error" in result.stderr.lower() or "required" in result.stderr.lower()

    def test_help(self):
        result = run_cli(["--help"])
        assert result.returncode == 0
        assert "Vector data format converter" in result.stdout

    def test_info_geojson(self, sample_geojson_path):
        result = run_cli([str(sample_geojson_path), "--info"])
        assert result.returncode == 0
        info = json.loads(result.stdout)
        assert info["feature_count"] == 3
        assert "Point" in info["geometry_types"]

    def test_info_csv(self, sample_csv_path):
        result = run_cli([str(sample_csv_path), "--info"])
        assert result.returncode == 0
        info = json.loads(result.stdout)
        assert info["feature_count"] == 3

    def test_info_kml(self, sample_kml_path):
        result = run_cli([str(sample_kml_path), "--info"])
        assert result.returncode == 0
        info = json.loads(result.stdout)
        assert info["feature_count"] == 2

    def test_convert_geojson_to_csv(self, sample_geojson_path, tmp_dir):
        output = tmp_dir / "out.csv"
        result = run_cli([str(sample_geojson_path), "--to", "csv", "-o", str(output)])
        assert result.returncode == 0
        assert output.exists()
        assert "Converted 3 features" in result.stdout

    def test_convert_geojson_to_kml(self, sample_geojson_path, tmp_dir):
        output = tmp_dir / "out.kml"
        result = run_cli([str(sample_geojson_path), "--to", "kml", "-o", str(output)])
        assert result.returncode == 0
        assert output.exists()

    def test_convert_with_precision(self, sample_geojson_path, tmp_dir):
        output = tmp_dir / "out.csv"
        result = run_cli([str(sample_geojson_path), "--to", "csv", "--precision", "2", "-o", str(output)])
        assert result.returncode == 0
        content = output.read_text()
        lines = content.strip().split("\n")
        assert len(lines) == 4  # header + 3 data

    def test_convert_with_fields(self, sample_geojson_path, tmp_dir):
        output = tmp_dir / "out.csv"
        result = run_cli([str(sample_geojson_path), "--to", "csv", "--fields", "name", "-o", str(output)])
        assert result.returncode == 0
        content = output.read_text()
        assert "population" not in content

    def test_convert_with_bbox(self, sample_geojson_path, tmp_dir):
        output = tmp_dir / "out.geojson"
        result = run_cli([
            str(sample_geojson_path), "--to", "geojson",
            "--bbox", "115", "20", "122", "35", "-o", str(output)
        ])
        assert result.returncode == 0
        data = json.loads(output.read_text())
        assert len(data["features"]) >= 1

    def test_convert_nonexistent_file(self):
        result = run_cli(["nonexistent.geojson", "--to", "csv", "-o", "out.csv"])
        assert result.returncode != 0

    def test_auto_output_name(self, sample_geojson_path, tmp_dir):
        result = run_cli(
            [str(sample_geojson_path), "--to", "csv"],
            cwd=str(tmp_dir),
        )
        assert result.returncode == 0
