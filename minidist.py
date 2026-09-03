from __future__ import annotations
import os
import argparse 
import os
import shutil
from datetime import date, datetime, timezone
import csv
from typing import Any, Dict, List 
import json
from storage.segmentor import _chunk_rows, _segment_dir_name, _write_segment

def do_init(path: str, schema: str) ->None:
    os.makedirs(path, exist_ok=True)

    # Copy schema to the table for easier access
    dest = os.path.join(path, "_schema.ssf")
    shutil.copy(schema, dest)
    print(f"Copied schema to {dest}")


def _read_schema(schema_path: str) -> tuple[list[dict], str]:
    # Parse `_schema.ssf` into column definitions and return the key column
    schema_columns: list[dict] = []
    key_column = ""
    with open(schema_path, "r", encoding="utf-8") as f:
        for line in f:
            line=line.strip()
            if not line or ":" not in line:
                continue

            name, info = line.split(":", 1)
            name = name.strip()
            info = info.strip()
            info_type = info.split()
            column_type = info_type[0] 

            column = {"name": name, "type": column_type}
            if "key" in info_type:
                column["key"] = True
                key_column = name
            if "nullable" in info_type:
                column["nullable"] = True

            schema_columns.append(column) 

    if not key_column:
        raise ValueError(f"No key column found in schema {schema_path!r}")

    return schema_columns, key_column

def _coerce_value(raw_value: str, column_type:str) -> Any:
    if column_type.startswith("int"):
        return int(raw_value)
    if column_type.startswith("float"):
        return float(raw_value)
    if column_type.startswith("bool"):
        return raw_value.strip().lower() in {"1", "true", "yes", "y"}
    if column_type.startswith("date"):
        return date.fromisoformat(raw_value)
    if column_type.startswith("timestamp"):
        millis = int(raw_value)
        return datetime.fromtimestamp(millis/1000, tz=timezone.utc)

    return raw_value

def _read_csv_rows(csv_path: str, schema_columns: list[dict])-> list[dict]:

    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"csv file {csv_path!r} not found. Please provide a valid csv file path")

    rows: List[Dict[str, Any]] = []

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        
        # print(schema_columns)
        # print(type(schema_columns))
        # print(type(schema_columns[0]))

        for raw_row in reader:
            row_dict: Dict[str, Any] = {}

            for column in schema_columns:
                column_name = column["name"]
                column_type = column["type"]

                if column_name not in raw_row:
                    if column["nullable"] == True:
                        continue
                    else:
                        raise KeyError(f"csv file is missing required column {column_name!r}")

                raw_value = raw_row[column_name] # raw_row[id]
                row_dict[column_name] = _coerce_value(raw_value, column_type) # so this is row_dict[id] = coerced value
            rows.append(row_dict)

    return rows


def _sort_rows_by_key(rows: list[dict], key_column: str) -> list[dict]:
    # lambda funcs are called by lambda x: x[], 
    # inside the [] you input the var you want to sort by 
    # key is optional in sorted(), so you have to define it
    return sorted(rows, key=lambda row:row[key_column])


def _print_schema(schema_path: str) -> None:
    schema_columns, key_column = _read_schema(schema_path)
    schema_output = {"key_column": key_column, "columns": schema_columns}
    print(json.dumps(schema_output, indent=2))


def _print_metadata(table_path: str) -> None:
    segments: list[dict] = []
    for entry in sorted(os.listdir(table_path)):
        segment_path = os.path.join(table_path, entry)
        if not (os.path.isdir(segment_path) and entry.startswith("seg-")):
            continue
        with open(os.path.join(segment_path, "segment_metadata.json"), "r", encoding="utf-8") as f:
                metadata = json.load(f)
        segments.append({"name": entry, "metadata": metadata})

    print(json.dumps(segments, indent=2))


def do_load(table_path: str, csv_name:str, sort_key: str, segments: int) -> None:
    schema_path = os.path.join(table_path, "_schema.ssf")
    schema_columns, key_column= _read_schema(schema_path)
    if sort_key != None and key_column != sort_key:
        key_column = sort_key


    rows = _read_csv_rows(csv_name, schema_columns)
    print(f"no. of rows after reading csv rows: {len(rows)}")
    rows = _sort_rows_by_key(rows, key_column)
    print(f"no. of rows after sorting: {len(rows)}")


    chunks = _chunk_rows(rows, segments)

    for i, chunk in enumerate(chunks, start=1):
        segment_name = _segment_dir_name(i)
        segment_path = os.path.join(table_path, segment_name)
        print(f"Writing {segment_name} with {len(chunk)} rows")
        _write_segment(segment_path, chunk, schema_columns, key_column)

    print(f"Done. Wrote {len(chunks)} segments")

def main() -> None:
    parser = argparse.ArgumentParser(prog="minidist")
    sub = parser.add_subparsers(dest="cmd")

    init_parser = sub.add_parser("init", help="initialize a table directory")
    init_parser.add_argument("table_path", help="path to table directory")
    init_parser.add_argument("--schema", required=True, help="path to schema file")

    schema_parser = sub.add_parser("schema", help="inspect schema information")
    schema_sub = schema_parser.add_subparsers(dest="schema_cmd")
    schema_show = schema_sub.add_parser("show", help="show the parsed schema")
    schema_show.add_argument("table_path", help="path to table directory")

    metadata_parser = sub.add_parser("metadata", help="inspect segment metadata")
    metadata_parser.add_argument("table_path", help="path to table directory")

    load_parser = sub.add_parser("load", help="load a CSV into table segments")
    load_parser.add_argument("table_path", help="path to table directory")
    load_parser.add_argument("--csv", required=True, help="path to CSV file")
    load_parser.add_argument("--sort-key", help="path to CSV file", default="id")
    load_parser.add_argument("--segments", type= int, help="path to CSV file", default=None)


    args = parser.parse_args()
    if args.cmd == "init":
        do_init(args.table_path, args.schema)
    elif args.cmd == "schema" and args.schema_cmd == "show":
        schema_path = os.path.join(args.table_path, "_schema.ssf")
        _print_schema(schema_path)
    elif args.cmd == "metadata":
        _print_metadata(args.table_path)
    elif args.cmd == "load":
        do_load(args.table_path, args.csv, args.sort_key, args.segments)
    else:
        parser.print_help(())



if __name__ == "__main__":
    main()