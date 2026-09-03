import json
from typing import Iterator, Any
from pathlib import Path


def read_segment_metadata(segment_dir: Path) -> dict:
    # convert metadata.json info into python dict

    metadata_path = segment_dir/ "segment_metadata.json"
    with open(metadata_path, "r", encoding="utf-8") as f:
        return json.load(f)

def read_column_values(segment_dir: Path, column: str) -> list[str]:
    # get the values from the column
    column_path = segment_dir / f"{column}.txt"
    text = column_path.read_text(encoding="utf-8")

    # return list of the txt items
    return text.splitlines()

def get_column_type(metadata: dict, column: str) -> str:
    for field in metadata["schema"]:
        if field["name"] == column:
            return field["type"]

    raise KeyError(f"Column {column!r} not found in schema")

def convert_value(value: str, column_type: str):
    if column_type == "int64":
        return int(value)
    if column_type == "float64":
        return float(value)
    if column_type == "string":
        return value
    if column_type == "timestamp(ms)":
        return int(value)

    return value

def iter_rows_for_segment(segment_dir: Path, needed_columns: list[str]) -> Iterator[dict]:
    metadata = read_segment_metadata(segment_dir)
    row_count = metadata["row_count"]
    column_values: dict[str, list[Any]] = {}

    for column in needed_columns:
        values = read_column_values(segment_dir, column)
        column_type = get_column_type(metadata, column)
        column_values[column] = [convert_value(value, column_type) for value in values]

    for i in range(row_count):
        row: dict[str, Any] = {}

        for column in needed_columns:
            row[column] = column_values[column][i]

        # we want to iterate over this, instead of loading all rows in a huge list, so we yield:
        yield row
