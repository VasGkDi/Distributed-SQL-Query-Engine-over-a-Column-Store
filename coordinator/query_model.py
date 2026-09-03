# Helper py file that defines data structures for parsing SQL queries

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

class ComparisonOp(str, Enum):
    EQ = "="
    LT = "<"
    GT = ">"
    BETWEEN = "BETWEEN"


class AggregateFunc(str, Enum):
    COUNT = "COUNT"
    SUM = "SUM"
    AVG = "AVG"
    MIN = "MIN"
    MAX = "MAX"

@dataclass(frozen=True)
class AggregateSpec:
    func: AggregateFunc
    column: Optional[str]

@dataclass(frozen=True)
class FilterClause:
    column: str
    op: ComparisonOp
    value: Any

@dataclass(frozen=True)
class WhereSpec:
    # Can take multiple where clauses with AND
    clauses: list[FilterClause] = field(default_factory=list)

@dataclass(frozen=True)
class Query:
    table: str
    select_columns: list[str] = field(default_factory=list)
    aggregates: list[AggregateSpec] = field(default_factory=list)
    where: Optional[WhereSpec] = None
    group_by: list[str] = field(default_factory=list)