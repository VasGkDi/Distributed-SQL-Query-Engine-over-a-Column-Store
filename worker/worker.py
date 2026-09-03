import argparse
from .http_server import run_worker_server

def main() -> None:
    parser = argparse.ArgumentParser(description="Start one worker")

    parser.add_argument("--port", type=int, required= True, help="Port on which this worker listens")
    parser.add_argument("--data", required=True, help="Path to the table directory")
    parser.add_argument("--segment", required=True, help="Name of the segment owned by this worker")

    args = parser.parse_args()

    segment_path = f"{args.data}/{args.segment}"

    print(f"Starting worker for segment {args.segment}")
    print(f"Data path: {segment_path}")
    print(f"Listening on port {args.port}")

    run_worker_server(port=args.port, table_path=segment_path)

if __name__ == "__main__":
    main()