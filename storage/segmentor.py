import json
import os
import shutil

def _chunk_rows(rows:list[dict], segments: list) -> list[list[dict]]:
    # break the total rows into chunks
    if segments <= 0:
        raise ValueError("Segments must be a positive integer")

    print(f"no. of rows at chunking {len(rows)}")
    row_count = len(rows)
    base_size,  remainder = divmod(row_count, segments)

    segments_list: list[list[dict]] = []
    start = 0
    for index in range(segments):
        chunk_size = base_size + (1 if index < remainder else 0 )
        end = start+ chunk_size
        segments_list.append(rows[start:end])
        start=end

    return segments_list

def _segment_dir_name(index: int):
    return f"seg-{index:06d}"

def _build_segment_metadata(rows: list[dict], schema: dict, key_column: str) -> dict:
    # we need column stats that have min and max values for proper segment skipping
    column_stats = {}

    for column in schema:
        column_name = column["name"]
        column_type = column["type"]

        if column_type in ("int64", "float64"):
            if rows:
                values = [row[column_name] for row in rows]

                column_stats[column_name] = {
                    "min": min(values),
                    "max": max(values)
                }
            else:
                column_stats[column_name] = {
                    "min": None,
                    "max": None
                }

    return {
        "key_column": key_column,
        "row_count": len(rows),
        "schema": schema,
        "column_stats": column_stats
    }

def _write_segment(segment_path: str, csv_rows:list[dict], schema_columns:list[dict], key_column: str) -> None:
    if os.path.exists(segment_path):
        shutil.rmtree(segment_path)
    os.makedirs(segment_path, exist_ok= True)

    for column in schema_columns:
        column_name = column["name"]
        column_path = os.path.join(segment_path, f"{column_name}.txt")

        with open(column_path, "w", encoding="utf-8", newline="\n") as f:
            try:
                for row in csv_rows:
                    f.write(f"{row[column_name]}\n")
            except:
                continue

    metadata = _build_segment_metadata(csv_rows, schema_columns, key_column)
    metadata_path = os.path.join(segment_path, "segment_metadata.json")
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
