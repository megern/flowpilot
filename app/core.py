"""Safe in-memory DAG runner with no dynamic code or network operations."""

from typing import Any, Literal
from math import isfinite
from pydantic import BaseModel, ConfigDict, Field


class Node(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=100)
    op: Literal["source", "select", "filter", "aggregate", "concat", "join"]
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
                "join": {"left_on", "right_on", "how", "cardinality", "right_prefix"},
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
            elif node.op == "join":
                if (
                    len(node.depends_on) != 2
                    or node.depends_on[0] == node.depends_on[1]
                ):
                    raise ValueError(
                        "Join requires two distinct ordered dependencies: left, right"
                    )
                result = join_rows(
                    outputs[node.depends_on[0]], outputs[node.depends_on[1]], p
                )
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


def join_rows(left, right, params):
    """Bounded SQL-like null semantics, with declared right uniqueness."""
    left_on = params.get("left_on")
    right_on = params.get("right_on")
    for columns in [left_on, right_on]:
        if (
            not isinstance(columns, list)
            or not 1 <= len(columns) <= 8
            or any(not isinstance(c, str) or not c for c in columns)
            or len(set(columns)) != len(columns)
        ):
            raise ValueError("Join keys must be 1–8 distinct nonempty column names")
    if len(left_on) != len(right_on):
        raise ValueError("Join key lists must have equal lengths")
    how = params.get("how", "inner")
    cardinality = params.get("cardinality", "many_to_one")
    prefix = params.get("right_prefix", "right_")
    if how not in ("inner", "left") or cardinality not in ("one_to_one", "many_to_one"):
        raise ValueError(
            "Join supports inner/left and one_to_one/many_to_one cardinality only"
        )
    if not isinstance(prefix, str) or not prefix or len(prefix) > 80:
        raise ValueError("Use a nonempty right_prefix up to 80 characters")

    def key(row, columns):
        if any(c not in row for c in columns):
            raise ValueError(
                "Join key is missing; use explicit null for unmatched values"
            )
        tokens = []
        for c in columns:
            v = row[c]
            if v is None:
                tokens.append(("null", None))
            elif isinstance(v, bool):
                tokens.append(("boolean", v))
            elif isinstance(v, (int, float)) and isfinite(v) and abs(v) <= 1e100:
                tokens.append(("number", v))
            elif isinstance(v, str):
                tokens.append(("string", v))
            else:
                raise ValueError(
                    "Join keys must be finite scalar numbers, strings, booleans or null"
                )
        return None if any(kind == "null" for kind, _ in tokens) else tuple(tokens)

    right_columns = sorted({c for row in right for c in row})
    left_columns = {c for row in left for c in row}
    if any(prefix + c in left_columns for c in right_columns):
        raise ValueError(
            "Right-prefixed output column collides with a left column; change right_prefix"
        )
    index = {}
    for row in right:
        k = key(row, right_on)
        if k is not None:
            if k in index:
                raise ValueError(
                    "Declared join cardinality requires unique nonnull right keys; many-to-many joins are not supported"
                )
            index[k] = row
    seen = set()
    result = []
    for row in left:
        k = key(row, left_on)
        if k is not None and cardinality == "one_to_one":
            if k in seen:
                raise ValueError("one_to_one requires unique nonnull left keys")
            seen.add(k)
        match = index.get(k) if k is not None else None
        if match is not None or how == "left":
            if len(result) >= 10000:
                raise ValueError("Join output exceeds 10000 rows")
            result.append(
                {
                    **row,
                    **{
                        prefix + c: match.get(c) if match is not None else None
                        for c in right_columns
                    },
                }
            )
    return result
