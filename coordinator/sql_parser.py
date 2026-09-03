# take the text from the CLI command and turn into query object

from dataclasses import dataclass
import re
from typing import List
from .query_model import (
    AggregateFunc,
    AggregateSpec,
    ComparisonOp,
    FilterClause,
    Query,
    WhereSpec
)


class ParseError(ValueError):
    """Raised when SQL text does not match our supported grammar.
    """


def parse_sql(sql_text:str) -> Query:
    sql_text = sql_text.strip()

    if not sql_text:
        raise ParseError("SQL query cannot be empty")

    # print("Parser starting")

    clauses = split_clauses(sql_text)

    select_columns, aggregates = parse_select_items(clauses.select_sql)

    # print("parse_select_items complete")

    table = clauses.from_sql.strip()

    if not table:
        raise ParseError("Table name cannot be empty")

    where = parse_where(clauses.where_sql)

    # print("Where parser done")

    group_by = parse_group_by(clauses.group_by_sql)

    # print("group_by done")

    return Query(
        table=table,
        select_columns=select_columns,
        aggregates=aggregates,
        where=where,
        group_by=group_by,
    )

@dataclass(frozen=True)
class ClauseSlices:
    select_sql: str
    from_sql: str
    where_sql: str | None
    group_by_sql: str | None

def split_clauses(sql_text: str) -> ClauseSlices:
    sql_text = sql_text.strip()

    sql_text = re.sub(r"\s+", " ", sql_text) # remove excess spaces between words

    match = re.fullmatch(
        r"""
        SELECT\s+
        (.+?)
        \s+FROM\s+
        (\w+)
        (?:\s+WHERE\s+(.+?))?
        (?:\s+GROUP\s+BY\s+(.+))?
        """,
        sql_text,
        flags=re.IGNORECASE | re.VERBOSE,
    )

    if not match:
        raise ParseError(
            f"Unsupported SQL format: {sql_text!r}"
        )

    return ClauseSlices(
        select_sql= match.group(1).strip(),
        from_sql=match.group(2).strip(),
        where_sql = match.group(3).strip() if match.group(3) else None,
        group_by_sql = match.group(4).strip() if match.group(4) else None,
    )

def parse_select_items(select_sql: str) -> tuple[list[str], list[AggregateSpec]]:
    items:List[str] = []
    parts = select_sql.split(",")
    for i in parts:
        items.append(i.strip())

    columns: List[str] = []
    aggregates: List[AggregateSpec] = []
    for item in items:
        aggregate = _parse_aggregate_item(item)

        if aggregate is not None:
            aggregates.append(aggregate)
        else:
            columns.append(item)

    return columns, aggregates

def _parse_aggregate_item(item:str) -> AggregateSpec |None:
    match = re.match(
        r"^(SUM|COUNT|AVG|MIN|MAX)\(([^)]*)\)$",
        item.strip(),
        flags=re.IGNORECASE,
    )

    if not match:
        return None

    function_name = match.group(1).upper()
    function = AggregateFunc(function_name)

    column = match.group(2).strip()

    # In case of count
    if function == AggregateFunc.COUNT and column == "*":
        column = None

    return AggregateSpec(
        func=function,
        column=column
    )

def parse_where(where_sql: str | None) -> WhereSpec | None:
    if where_sql is None or not where_sql.strip():
        return None

    clauses: List[FilterClause] = []

    remaining = where_sql.strip()

    while remaining:
        print("WHERE LOOP:", remaining)

        remaining = remaining.lstrip()

        between_match = re.match(
            r"^(\w+)\s+BETWEEN\s+(\S+)\s+AND\s+(\S+)"
            r"(?:\s+AND\s+(.+))?$",
            remaining,
            flags=re.IGNORECASE,
        )

        if between_match:
            column = between_match.group(1)
            low = _coerce_literal(between_match.group(2))
            high = _coerce_literal(between_match.group(3))

            clauses.append(
                FilterClause(
                    column=column,
                    op=ComparisonOp.BETWEEN,
                    value=(low,high),
                )
            )

            remaining = between_match.group(4) or ""

            continue
        comparison_match = re.match(
            r"^(\w+)\s*(=|>|<)\s*(\S+)"
            r"(?:\s+AND\s+(.+))?$",
            remaining,
            flags=re.IGNORECASE,
        )

        if comparison_match:
            column = comparison_match.group(1)
            operator = comparison_match.group(2)
            value = _coerce_literal(comparison_match.group(3))

            comparison_op = ComparisonOp(operator)

            clauses.append(
                FilterClause(
                    column=column,
                    op=comparison_op,
                    value=value,
                )
            )

            remaining = comparison_match.group(4) or ""

            continue

        raise ParseError(
            f"Unsupported WHERE clause: {remaining!r}"
        )

    return WhereSpec(clauses=clauses)

def parse_group_by(group_sql: str | None) -> list[str]:
    if not group_sql:
        return[]
    return [
        column.strip() for column in group_sql.split(",")
    ]


def _coerce_literal(token: str):
    token = token.strip()

    # in case the token is in "" or ''
    if (
        len(token) >= 2
        and token[0] == token[-1]
        and token[0] in ("'", '"')
    ):
        return token[1:-1]
    try:
        return int(token)
    except ValueError:
        pass
    try:
        return float(token)
    except ValueError:
        pass

    return token

        
