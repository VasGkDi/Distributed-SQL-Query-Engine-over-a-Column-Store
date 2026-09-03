import argparse
import json
from typing import Any
from urllib import request
from http.server import BaseHTTPRequestHandler, HTTPServer

from .query_model import Query, AggregateFunc
from .sql_parser import parse_sql

def parse_worker_ports(worker_text: str) -> list[str]:

    ports = worker_text.split(",")
    worker_urls = []
    for port in ports:
        port = port.strip()

        if not port:
            continue
        worker_urls.append(f"http://localhost:{port}/query")

    return worker_urls

def build_worker_request(sql: str) -> dict[str, Any]:
    # the worker needs only the query
    return {
        "sql": sql
    }

def send_query_to_worker(worker_url:str, payload: dict[str, Any]) -> dict[str,Any]:
    body = json.dumps(payload).encode("utf-8")

    req = request.Request(
        worker_url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    with request.urlopen(req, timeout=10) as response:
        # take the json bytes and make them python text
        response_body = response.read()

        print("Coordinator read into bytes")
        response_text = response_body.decode("utf-8")
        print("coordinator decoded bytes succesfully")

        result = json.loads(response_text)
        print("parsed result")

        return result

def merge_partial_results(partial_results: list[dict[str,Any]], query: Query) -> list[dict[str,Any]]:
    # the hard part: take the partials depending on the query and return final result

    if not query.aggregates and not query.group_by:
        rows: list[dict[str, Any]] = []

        for result in partial_results:
            worker_rows = result.get("rows", [])
            rows.extend(worker_rows)

        return rows

    if query.aggregates and not query.group_by:

        final_row: dict[str, Any] = {}

        for aggregate in query.aggregates:
            if aggregate.func == AggregateFunc.COUNT:
                print("from")
                total = 0
                for result in partial_results:
                    for row in result.get("rows",[]):
                        total += row["COUNT(*)"]
                final_row["COUNT(*)"] = total

            elif aggregate.func == AggregateFunc.SUM:

                column = aggregate.column
                key = f"SUM({column})"

                total = 0

                for result in partial_results:
                    for row in result.get("rows", []):
                        total += row[key]

                final_row[key] = total

            elif aggregate.func == AggregateFunc.MIN:

                column = aggregate.column
                key = f"MIN({column})"

                values = []

                for result in partial_results:
                    for row in result.get("rows",[]):
                        if row[key] is not None:
                            values.append(row[key])

                if values:
                    final_row[key] = min(values)
                else:
                    final_row[key] = None

            elif aggregate.func == AggregateFunc.MAX:

                column = aggregate.column
                key = f"MAX({column})"

                values = []

                for result in partial_results:
                    for row in result.get("rows", []):
                        if row[key] is not None:
                            values.append(row[key])


                if values:
                    final_row[key] = max(values)
                else:
                    final_row[key] = None


            elif aggregate.func == AggregateFunc.AVG:
                column = aggregate.column

                sum_key = f"AVG({column})__sum"
                count_key = f"AVG({column})__count"

                total = 0
                count = 0

                for result in partial_results:
                    for row in result.get("rows", []):
                        total += row[sum_key]
                        count += row[count_key]

                if count == 0:
                    final_row[f"AVG({column})"] = None
                else:
                    final_row[f"AVG({column})"] = total /count

        return [final_row]

    if query.group_by:

        groups: dict[tuple, dict[str, Any]] = {}

        for result in partial_results:
            for row in result.get("rows", []):
                # this supports GROUP BY >=2 items
                group_key = tuple(row[column] for column in query.group_by)

                if group_key not in groups:
                    groups[group_key] = {}

                state = groups[group_key]

                for aggregate in query.aggregates:
                    if aggregate.func == AggregateFunc.COUNT:
                        key = "COUNT(*)"

                        if key not in state:
                            state[key] = 0

                        state[key] += row[key]

                    elif aggregate.func == AggregateFunc.SUM:
                        column= aggregate.column
                        key = f"SUM({column})"

                        if key not in state:
                            state[key] = 0

                        state[key] += row[key]

                    elif aggregate.func == AggregateFunc.MIN:
                        column = aggregate.column
                        key = f"MIN({column})"

                        value = row[key]

                        if key not in state:

                            state[key] = value

                        elif value is not None:
                            state[key] = min(state[key], value)

                    elif aggregate.func == AggregateFunc.MAX:
                        column = aggregate.column
                        key = f"MAX({column})"

                        value = row[key]

                        if key not in state:
                            state[key] = value

                        elif value is not None:
                            state[key] = max(state[key], value)

                    elif aggregate.func == AggregateFunc.AVG:

                        column = aggregate.column
                        sum_key = f"AVG({column})__sum"
                        count_key = f"AVG({column})__count"

                        if sum_key not in state:
                            state[sum_key] = 0
                            state[count_key] = 0

                        state[sum_key] += row[sum_key]
                        state[count_key] += row[count_key]


        results: list[dict[str,Any]] = []

        for group_key, state in groups.items():
            result_row: dict[str, Any] = {}

            for index, column in enumerate(query.group_by):
                result_row[column] = group_key[index]


            for aggregate in query.aggregates:
                if aggregate.func == AggregateFunc.COUNT:
                    key = "COUNT(*)"
                    result_row[key] = state[key]

                elif aggregate.func == AggregateFunc.SUM:
                    column =aggregate.column
                    key = f"SUM({column})"

                    result_row[key] = state[key]

                elif aggregate.func == AggregateFunc.MIN:

                    column = aggregate.column
                    key = f"MIN({column})"

                    result_row[key] = state[key]

                elif aggregate.func == AggregateFunc.MAX:

                    column = aggregate.column
                    key = f"MAX({column})"

                    result_row[key] = state[key]

                elif aggregate.func == AggregateFunc.AVG:

                    column = aggregate.column

                    sum_key = f"AVG({column})__sum"
                    count_key = f"AVG({column})__count"

                    total = state[sum_key]
                    count = state[count_key]

                    if count == 0:
                        result_row[f"AVG({column})"] = None
                    else:
                        result_row[f"AVG({column})"] = total / count

            results.append(result_row)

        return results


def execute_distributed_query(sql: str, worker_urls:list[str]) -> tuple[list[dict[str,Any]], dict[str, Any]]:
    query: Query = parse_sql(sql)

    payload = build_worker_request(sql)

    partial_results: list[dict[str, Any]] = []

    for worker_url in worker_urls:
        result = send_query_to_worker(worker_url,payload)

        partial_results.append(result)

    rows = merge_partial_results(partial_results, query)

    total_rows_scanned = 0
    total_segments_skipped = 0
    total_execution_time = 0

    for result in partial_results:
        stats = result.get("execution_stats",{})
        total_rows_scanned += stats.get("rows_scanned", 0)
        total_segments_skipped += stats.get("segments_skipped", 0)
        total_execution_time += stats.get("execution_time_ms", 0)

    execution_stats = {
        "rows_scanned": total_rows_scanned,
        "segments_skipped": total_segments_skipped,
        "execution_time_ms": round(total_execution_time, 2)
    }

    return rows, execution_stats

def format_results_as_table(rows: list[dict[str, Any]], execution_stats: dict[str, Any]) -> str:
    if not rows:
        return (
            "No results.\n\n"
            "Execution Details:\n"
            f"Rows scanned: {execution_stats.get('rows_scanned', 0)}\n"
            f"Segments skipped: {execution_stats.get('segments_skipped', 0)}\n"
            f"Execution time: "
            f"{execution_stats.get('execution_time_ms', 0)} ms"
        )

    columns = list(rows[0].keys())

    # calc the width of every column
    widths: dict[str, int] = {}

    for column in columns:
        width = len(column)
        for row in rows:
            value = str(row.get(column, ""))
            width = max(width, len(value))

        widths[column] = width

    # header and seperator for the table
    header = " | ".join(column.ljust(widths[column]) for column in columns) 
    seperator = "-+-".join("-"* widths[column] for column in columns)

    table_rows = []

    for row in rows:
        line = " | ".join(str(row.get(column, "")).ljust(widths[column]) for column in columns)
        table_rows.append(line)

    execution_details = [
        "",
        "Execution Details:",
        f"Rows scanned: {execution_stats.get('rows_scanned', 0)}",
        f"Segments skipped: {execution_stats.get('segments_skipped', 0)}",
        (
            "Execution time: "
            f"{execution_stats.get('execution_time_ms', 0)} ms"
        ),
    ]

    return "\n".join(
        [
            header, 
            seperator,
            *table_rows,
            *execution_details
        ]
    )

class CoordinatorHandler(BaseHTTPRequestHandler):
    worker_urls: list[str] = []

    def do_POST(self) -> None:
        if self.path != "/query":
            self.send_error(404, "Unknown endpoint")
            return

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        sql = body.decode("utf-8").strip()

        if not sql:
            self.send_error(400, "Empty SQL query")
            return

        try: 
            rows, execution_stats = execute_distributed_query(sql, self.worker_urls)

        except Exception as exc:
            self.send_error(500, str(exc))
            return

        response_text = format_results_as_table(rows, execution_stats)
        response_body = response_text.encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(response_body)

def main() -> None:
    parser = argparse.ArgumentParser(description="Start the distributed-query coordinator.")
    parser.add_argument("--port", type=int, required=True, help="Port on which the coordinator listns" )
    parser.add_argument("--workers", required=True, help="Comma-seperated worker ports")

    args = parser.parse_args()

    worker_urls = parse_worker_ports(args.workers)

    CoordinatorHandler.worker_urls = worker_urls
    server = HTTPServer(("localhost", args.port), CoordinatorHandler)

    print(f"coordinator listening on port {args.port}")
    print(f"workers: {", ".join(worker_urls)}")

    server.serve_forever()

if __name__ == "__main__":
    main()

