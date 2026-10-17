"""Safe in-memory DAG runner with no dynamic code or network operations."""

from typing import Any, Literal
from math import isfinite
from pydantic import BaseModel, ConfigDict, Field


class Node(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=100)
    op: Literal["source", "select", "filter", "aggregate", "concat"]
    depends_on: list[str] = Field(default_factory=list, max_length=50)
    params: dict[str, Any] = Field(default_factory=dict)


class Request(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nodes: list[Node] = Field(min_length=1, max_length=50)


def analyze(request: Request) -> dict:
    nodes = {node.id: node for node in request.nodes}
    if len(nodes) != len(request.nodes):
        raise ValueError("Node IDs must be unique")
    if any(dep not in nodes for node in nodes.values() for dep in node.depends_on):
        raise ValueError("Unknown dependency")

    def validate_cells(value, depth=0):
        if depth > 32:
            raise ValueError("Source nesting exceeds 32 levels")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if abs(value) > 1e100 or not isfinite(value):
                raise ValueError(
                    "Source numeric values must be finite with magnitude at most 1e100"
                )
        elif isinstance(value, dict):
            for item in value.values():
                validate_cells(item, depth + 1)
        elif isinstance(value, list):
            for item in value:
                validate_cells(item, depth + 1)

    size_cache = {}

    def estimated_size(value):
        if isinstance(value, str):
            return 6 * len(value) + 2
        if value is None or isinstance(value, bool):
            return 5
        if isinstance(value, (int, float)):
            return 128
        cached = size_cache.get(id(value))
        if cached is not None:
            return cached
        if isinstance(value, dict):
            size = 2 + sum(
                estimated_size(str(key)) + estimated_size(item) + 2
                for key, item in value.items()
            )
        elif isinstance(value, list):
            size = 2 + sum(estimated_size(item) + 1 for item in value)
        else:
            raise ValueError("Workflow values must be JSON-compatible")
        size_cache[id(value)] = size
        return size

    output_budget = 0
    outputs, order = {}, []
    pending = dict(nodes)
    while pending:
        ready = [n for n in pending.values() if all(d in outputs for d in n.depends_on)]
        if not ready:
            raise ValueError("Workflow has a dependency cycle")
        for node in ready:
            p = node.params
            allowed = {
                "source": {"rows"},
                "select": {"fields"},
                "filter": {"field", "comparison", "value"},
                "aggregate": {"field", "operation", "group_by"},
                "concat": set(),
            }[node.op]
            if set(p) - allowed:
                raise ValueError("Unexpected parameters for " + node.op)
            if node.op in ("filter", "aggregate") and (
                node.op == "filter" or p.get("operation", "sum") != "count"
            ):
                if not isinstance(p.get("field"), str):
                    raise ValueError("Field must be a string")
            if node.op == "source":
                if node.depends_on:
                    raise ValueError("Source cannot depend on another node")
                rows = p.get("rows", [])
                if not isinstance(rows, list) or any(
                    not isinstance(r, dict) for r in rows
                ):
                    raise ValueError("Source rows must be objects")
                validate_cells(rows)
                result = rows
            elif node.op == "concat":
                if not node.depends_on:
                    raise ValueError("Concat requires dependencies")
                if sum(len(outputs[dep]) for dep in node.depends_on) > 10000:
                    raise ValueError("Node output exceeds 10000 rows")
                result = [row for dep in node.depends_on for row in outputs[dep]]
            else:
                if len(node.depends_on) != 1:
                    raise ValueError("Transform requires exactly one dependency")
                rows = outputs[node.depends_on[0]]
                field = p.get("field")
                if node.op == "select":
                    fields = p.get("fields")
                    if not isinstance(fields, list) or any(
                        not isinstance(f, str) for f in fields
                    ):
                        raise ValueError("Select fields must be a list of strings")
                    if any(any(f not in row for f in fields) for row in rows):
                        raise ValueError("Select field is missing")
                    result = [{f: row[f] for f in fields} for row in rows]
                elif node.op == "filter":
                    comparison = p.get("comparison", "eq")
                    if comparison not in ("eq", "gt", "lt"):
                        raise ValueError("Comparison must be eq, gt or lt")
                    if any(field not in row for row in rows):
                        raise ValueError("Filter field is missing")
                    value = p.get("value")
                    try:
                        result = [
                            r
                            for r in rows
                            if (
                                r[field] == value
                                if comparison == "eq"
                                else r[field] > value
                                if comparison == "gt"
                                else r[field] < value
                            )
                        ]
                    except TypeError as exc:
                        raise ValueError("Filter values are not comparable") from exc
                else:
                    operation = p.get("operation", "sum")
                    if operation not in ("sum", "mean", "count"):
                        raise ValueError(
                            "Aggregate operation must be sum, mean or count"
                        )
                    result = aggregate_rows(
                        rows, field, operation, p.get("group_by", [])
                    )
            if len(result) > 10000:
                raise ValueError("Node output exceeds 10000 rows")
            output_budget += estimated_size(result)
            if output_budget > 4194304:
                raise ValueError(
                    "Workflow outputs exceed conservative 4 MiB serialized budget"
                )
            outputs[node.id] = result
            order.append(node.id)
            del pending[node.id]
    return {"execution_order": order, "outputs": outputs}


def aggregate_rows(rows, field, operation, group_by):
    """Group scalar keys without conflating booleans, numbers and text."""
    if (
        not isinstance(group_by, list)
        or len(group_by) > 8
        or any(not isinstance(c, str) or not c for c in group_by)
        or len(set(group_by)) != len(group_by)
    ):
        raise ValueError(
            "group_by must contain at most eight unique nonempty column names"
        )
    if operation in group_by:
        raise ValueError(
            "Grouping column conflicts with the aggregate output name: " + operation
        )
    groups = {}
    if not group_by:
        groups[()] = ({}, rows)
    else:
        for row in rows:
            if any(column not in row for column in group_by):
                raise ValueError(
                    "Grouping column is missing; explicit null keys are allowed"
                )
            values = [row[column] for column in group_by]
            key = []
            for value in values:
                if value is None:
                    key.append(("null", None))
                elif isinstance(value, bool):
                    key.append(("boolean", value))
                elif (
                    isinstance(value, (int, float))
                    and abs(value) <= 1e100
                    and isfinite(value)
                ):
                    key.append(("number", value))
                elif isinstance(value, str):
                    key.append(("string", value))
                else:
                    raise ValueError(
                        "Grouping keys must be finite scalar numbers, strings, booleans or null"
                    )
            token = tuple(key)
            if token not in groups:
                if len(groups) >= 1000:
                    raise ValueError("Grouped aggregate exceeds 1000 groups")
                groups[token] = (dict(zip(group_by, values)), [])
            groups[token][1].append(row)
    result = []
    for key_values, members in groups.values():
        if operation == "count":
            value = len(members)
        else:
            values = [row.get(field) for row in members]
            if any(
                isinstance(v, bool)
                or not isinstance(v, (int, float))
                or abs(v) > 1e100
                or not isfinite(v)
                for v in values
            ):
                raise ValueError(
                    "Aggregate field must be numeric, with no missing or null values"
                )
            if operation == "mean" and not values:
                raise ValueError("Cannot average empty data")
            value = sum(values) if operation == "sum" else sum(values) / len(values)
        if not isfinite(value):
            raise ValueError("Aggregate result exceeds finite numeric range")
        result.append({**key_values, operation: value})
    return result
