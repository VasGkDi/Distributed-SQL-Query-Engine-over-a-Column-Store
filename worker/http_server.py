import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from .executor import execute_query
from coordinator.sql_parser import parse_sql


# need an http server that allows communication between the workers and coordinator

def handle_query_payload(payload: dict[str, Any], table_path: str) -> dict[str, Any]:
    # request turns into worker execution
    sql = payload["sql"]

    print("worker parses the sql")
    query = parse_sql(sql)
    print("worker parsed sql")

    results, execution_stats = execute_query(table_path, query)

    print("execution complete with", len(results), "rows")

    response = {
        "status": "ok", 
        "rows": results,
        "execution_stats": execution_stats,
    }

    return response

class QueryHandler(BaseHTTPRequestHandler):
    # parses JSON, calls the worker logic and returns JSON

    def do_POST(self) -> None:
        print("worker received the post request")

        # get the body of the POST in JSON bytes
        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length)

        # decode the json bytes into a python string
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            self.send_error(400, "Request body must be in valid JSON format")
            return

        print("worker parsed payload:", payload)

        # execute the query
        try:
            result = handle_query_payload(payload, self.table_path)
        except Exception as exc:
            self.send_error(500, f"Worker execution failed: {exc}")
            return

        print("worker query finished! Result:", result)

        # result is a python dict, so we turn it back to json text
        body = json.dumps(result).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()

        self.wfile.write(body)

        print("response from wroker sent\n")

    def log_message(self, format:str, *args: Any) -> None:
        # I already have debug messages, i dont need the default logging
        return
def make_handler(table_path: str):
    # HTTPServer needs a class, but each worker has a different segment to work on so 
    # we need to make a class factory that returns classes with the proper segment paths

    class TableQueryHandler(QueryHandler):
        def __init__(self, *args, **kwargs):
            self.table_path = table_path
            super().__init__(*args, **kwargs)

    return TableQueryHandler

def run_worker_server(
        host: str = "127.0.0.1",
        port: int = 8001,
        table_path: str = "data/sales"
) -> None:

    # get a class that knows the segment path
    handler = make_handler(table_path)

    server = HTTPServer(
        (host, port),
        handler,
    )
    print(
        f"Worker listening on http://{host}:{port}"
        f"for table {table_path}"
    )

    try:
        server.serve_forever()

    except KeyboardInterrupt:
        print("worker shutting down")
    finally:
        server.server_close()


if __name__ == "__main__":
    run_worker_server()
