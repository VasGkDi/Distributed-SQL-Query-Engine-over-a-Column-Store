# Distributed SQL Query Engine over a Column Store

A small distributed SQL query engine built around column-oriented storage. The project was developed as the final project for **CS50** and as a practical application of concepts from my **MSc class in Big Data Management**.

## Overview

Traditional row-oriented execution reads complete records even when a query needs only one or two fields. This project stores each column separately, allowing workers to read only the data required by a query. CSV data is parsed according to a user-defined schema, converted to the appropriate Python types, sorted by a key, and divided into independently stored segments.

The system is divided into three components:

- **CLI and storage layer:** Initializes tables, validates and loads CSV data, creates segments, and exposes schema and metadata inspection commands.
- **Workers:** Each worker owns one segment, reads the required column files, applies filters, and computes local rows or aggregate results.
- **Coordinator:** Accepts SQL over HTTP, sends the query to the configured workers, and merges their partial results into a final response.

For aggregation queries, workers calculate local counts, sums, averages, minimums, maximums, or grouped results. The coordinator then combines those partial results. Segment metadata stores information such as row counts and key ranges, providing the basis for skipping segments that cannot satisfy a filter.

## Features

- Column-oriented storage with one file per column
- Schema-driven type conversion for integers, floats, booleans, dates, and timestamps
- Sorted, independently addressable data segments
- Distributed execution through HTTP coordinator and worker services
- `WHERE` clauses with `=`, `<`, `>`, `BETWEEN`, and `AND`
- `GROUP BY` with multiple columns
- `COUNT`, `SUM`, `AVG`, `MIN`, and `MAX` aggregates
- Segment metadata inspection and query execution statistics

## Supported Query Shape

```sql
SELECT <columns or aggregate expressions>
FROM <table>
[WHERE <condition> [AND <condition> ...]]
[GROUP BY <columns>];
```

The current parser is intentionally limited. Joins, `OR`, ordering, aliases, limits, updates, and deletes are planned extensions rather than supported SQL features.

## Requirements

- Python 3.10 or newer
- PowerShell, Command Prompt, or another shell capable of running Python commands
- No external Python packages are required by the current implementation

Run the commands below from the project root.

## Quick Start

### 1. Initialize a table

```powershell
python minidist.py init data/sales --schema _schema.ssf
```

The schema is copied into the table directory for use during loading and inspection.

### 2. Load and segment the CSV data

```powershell
python minidist.py load data/sales --csv sales.csv --sort-key id --segments 3
```

The included sample data contains the columns `id`, `region`, and `amount`. The `--segments` value must be a positive integer.

### 3. Inspect the table

```powershell
python minidist.py schema show data/sales
python minidist.py metadata data/sales
```

Each generated segment contains files such as `id.txt`, `region.txt`, `amount.txt`, and `segment_metadata.json`.

### 4. Start the workers

Start one worker per segment in separate terminals:

```powershell
python -m worker.worker --port 9001 --data data/sales --segment seg-000001
python -m worker.worker --port 9002 --data data/sales --segment seg-000002
python -m worker.worker --port 9003 --data data/sales --segment seg-000003
```

### 5. Start the coordinator

In another terminal, start the coordinator with the worker ports:

```powershell
python -m coordinator.coordinator --port 8080 --workers 9001,9002,9003
```

### 6. Submit a query

```powershell
curl.exe -X POST http://localhost:8080/query -d "SELECT region, SUM(amount) FROM sales GROUP BY region"
```

## Example Queries

```sql
SELECT amount FROM sales;
SELECT id, amount FROM sales WHERE amount > 300;
SELECT amount FROM sales WHERE amount BETWEEN 100 AND 200;
SELECT amount FROM sales WHERE amount > 100 AND region = 'EU';
SELECT COUNT(*) FROM sales;
SELECT AVG(amount) FROM sales;
SELECT region, COUNT(*) FROM sales GROUP BY region;
SELECT region, SUM(amount) FROM sales WHERE amount > 100 GROUP BY region;
```

## Project Structure

```text
minidist.py                 Table initialization and CSV loading CLI
coordinator/                SQL parsing, HTTP coordination, result merging
worker/                     Worker server and query execution
storage/                    Segment creation and column-file reading
_schema.ssf                 Example table schema
sales.csv                   Example input data
```

## Design Goals and Limitations

This project focuses on the mechanics of a distributed, column-oriented execution model rather than production database completeness. Workers are configured manually, each worker owns one segment, and the coordinator currently sends work to the configured workers. The system does not yet provide replication, fault tolerance, authentication, concurrent scheduling, or a persistent catalog.

## Future Work

- Add joins, `OR`, ordering, aliases, and limits
- Improve metadata-based predicate pushdown
- Add concurrent worker scheduling and failure handling
- Add a persistent catalog and table discovery
- Add automated tests, benchmarks, and comparison with row-oriented execution

## Academic Context

This project was created for CS50's final project and further developed as a practical Big Data systems project. The architecture was designed and implemented by me. I used LLMs selectively for researching standard approaches, considering edge cases, and debugging. 