# take the query and executes it on the data

from typing import Any
from coordinator.query_model import(
    AggregateFunc,
    AggregateSpec,
    ComparisonOp,
    FilterClause,
    Query,
    WhereSpec,
)
from storage.storage_reader import (
    read_segment_metadata,
    iter_rows_for_segment
)

import time
from pathlib import Path

def execute_query(table_path: str, query: Query) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    start_time = time.perf_counter()

    needed_columns = needed_columns_for_query(query)

    print("Table path:", table_path)
    print("needed columns:", needed_columns)
    print("query", query)

    rows_scanned = 0
    segments_skipped = 0

    segments = [Path(table_path)]

    # print("before bool")
    if bool(query.aggregates) or bool(query.group_by):
        groups: dict[tuple, dict[str, Any]] = {}

        for segment_dir in segments:
            metadata = read_segment_metadata(segment_dir)

            print("metadata:", metadata)
            print("metadata type:", type(metadata))

            if should_skip_segment(metadata, query.where):
                print("skipping segment:", segment_dir)
                segments_skipped += 1
                continue

            rows = iter_rows_for_segment(segment_dir, needed_columns)
            for row in rows:
                rows_scanned +=1
                if not evaluate_where(row, query.where):
                    continue

                if query.group_by:
                    group_key = tuple(
                        row[column] for column in query.group_by
                    )

                else:
                    group_key = ()

                if group_key not in groups:
                    print("creating state for:", group_key)

                    groups[group_key] = initial_agg_state(query.aggregates)
                    print("initialized the state")
                update_agg_state(groups[group_key], row, query.aggregates)
                print("updated the state")
        results: list[dict[str, Any]] = []
        for group_key, state in groups.items():
            result_row: dict[str, Any] = {}

            for index, column in enumerate(query.group_by):
                result_row[column] = group_key[index]

            result_row.update(
                finalize_agg_state(state, query.aggregates)
            )

            results.append(result_row)

    # in case of simpler select
    else:
        # print("inside else")

        results = []

        for segment_dir in segments:
            metadata = read_segment_metadata(segment_dir)
            
            if should_skip_segment(metadata, query.where):
                segments_skipped += 1
                continue
            rows = iter_rows_for_segment(segment_dir, needed_columns)

            
            for row in rows:
                rows_scanned += 1
                if not evaluate_where(row, query.where):
                    continue
                result_row = {}

                for column in query.select_columns:
                    result_row[column] = row[column]

                results.append(result_row)

    elapsed_seconds = time.perf_counter() - start_time

    execution_stats = {
        "rows_scanned": rows_scanned,
        "segments_skipped": segments_skipped,
        "execution_time_ms": round(elapsed_seconds * 1000, 2)

    }
    return results, execution_stats

def should_skip_segment(metadata: dict[str, Any], where: WhereSpec | None) -> bool:
    if where is None:
        return False

    column_stats = metadata.get("column_stats", {})

    for clause in where.clauses:

        stats = column_stats.get(clause.column)

        # We don't have min/max information for this column
        if stats is None:
            continue

        min_value = stats["min"]
        max_value = stats["max"]

        if min_value is None or max_value is None:
            continue

        if clause.op == ComparisonOp.GT:
            if max_value <= clause.value:
                return True

        elif clause.op == ComparisonOp.LT:
            if min_value >= clause.value:
                return True

        elif clause.op == ComparisonOp.EQ:
            if clause.value < min_value or clause.value > max_value:
                return True

        elif clause.op == ComparisonOp.BETWEEN:
            if clause.value[1] < min_value or clause.value[0] > max_value:
                return True

    return False

def evaluate_clause(row: dict[str, Any], clause: FilterClause) -> bool:
    row_value = row[clause.column]

    if clause.op == ComparisonOp.EQ:
        return row_value == clause.value

    elif clause.op == ComparisonOp.LT:
        return row_value < clause.value

    elif clause.op == ComparisonOp.GT:
        return row_value > clause.value

    elif clause.op == ComparisonOp.BETWEEN:
        return clause.value[0] <= row_value <= clause.value[1]

    return False

def evaluate_where(row: dict[str, Any], where: WhereSpec | None) -> bool:
    if where is None:
        return True

    for clause in where.clauses:
        if not evaluate_clause(row, clause):
            return False

    return True

def needed_columns_for_query(query: Query) -> list[str]:
    columns: list[str] = []

    columns.extend(query.select_columns)

    if query.where is not None:
        for clause in query.where.clauses:
            columns.append(clause.column)

    columns.extend(query.group_by)

    for aggregate in query.aggregates:
        if aggregate.column is not None:
            columns.append(aggregate.column)

    return list(dict.fromkeys(columns)) # cleans up any duplicates

def initial_agg_state(aggs: list[AggregateSpec]) -> dict[str, Any]:
    # used for aggregation

    state: dict[str, Any] = {}
    print("initial state")
    for aggregate in aggs:
        if aggregate.func == AggregateFunc.COUNT:
            state["COUNT(*)"] = 0
        elif aggregate.func == AggregateFunc.SUM:
            state[f"SUM({aggregate.column})"] = 0
        elif aggregate.func == AggregateFunc.MIN:
            state[f"MIN({aggregate.column})"] = None
        elif aggregate.func == AggregateFunc.MAX:
            state[f"MAX({aggregate.column})"] = None
        elif aggregate.func == AggregateFunc.AVG:
            state[f"AVG({aggregate.column})__sum"] = 0
            state[f"AVG({aggregate.column})__count"] = 0
    print("initial state complete")
    return state

def update_agg_state(state: dict[str, Any], row: dict[str, Any], aggs: list[AggregateSpec]) -> None:
    for aggregate in aggs:
        if aggregate.func == AggregateFunc.COUNT:
            state["COUNT(*)"] += 1

        elif aggregate.func == AggregateFunc.SUM:
            value = row[aggregate.column]
            # print(value, type(value))
            # print("STATE:", state)
            # print("KEY:", f"SUM({aggregate.column})")

            state[f"SUM({aggregate.column})"] += value

        elif aggregate.func == AggregateFunc.MIN:
            column = aggregate.column
            value = row[column]
            key = f"MIN({column})"

            if state[key] is None or value < state[key]:
                state[key] = value

        elif aggregate.func == AggregateFunc.MAX:
            column = aggregate.column
            value = row[column]
            key = f"MAX({column})"

            if state[key] is None or value > state[key]:
                state[key] = value

        elif aggregate.func == AggregateFunc.AVG:
            state[f"AVG({aggregate.column})__sum"] += row[aggregate.column]
            state[f"AVG({aggregate.column})__count"] += 1

def finalize_agg_state(state: dict[str, Any], aggs: list[AggregateSpec]) -> dict[str, Any]:

    result: dict[str, Any] = {}

    for aggregate in aggs:

        if aggregate.func == AggregateFunc.COUNT:
            key = "COUNT(*)"
            result[key] = state[key]

        elif aggregate.func == AggregateFunc.SUM:
            key = f"SUM({aggregate.column})"
            result[key] = state[key]

        elif aggregate.func == AggregateFunc.MIN:
            key = f"MIN({aggregate.column})"
            result[key] = state[key]

        elif aggregate.func == AggregateFunc.MAX:
            key = f"MAX({aggregate.column})"
            result[key] = state[key]

        elif aggregate.func == AggregateFunc.AVG:
            sum_key = f"AVG({aggregate.column})__sum"
            count_key = f"AVG({aggregate.column})__count"

            total = state[sum_key]
            count = state[count_key]

            # The coordinator needs both the sum and the count from every worker respectively
            result[sum_key] = total
            result[count_key] = count

    return result

    
