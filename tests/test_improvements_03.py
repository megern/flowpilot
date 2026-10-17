import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def run(rows, params):
    return client.post(
        "/analyze",
        json={
            "nodes": [
                {"id": "s", "op": "source", "params": {"rows": rows}},
                {"id": "g", "op": "aggregate", "depends_on": ["s"], "params": params},
            ]
        },
    )


@pytest.mark.parametrize(
    "operation, expected", [("sum", [40, 20]), ("mean", [20, 20]), ("count", [2, 1])]
)
def test_grouped_known_results(operation, expected):
    rows = [{"team": "A", "v": 10}, {"team": "B", "v": 20}, {"team": "A", "v": 30}]
    response = run(rows, {"operation": operation, "field": "v", "group_by": ["team"]})
    assert response.status_code == 200
    assert response.json()["outputs"]["g"] == [
        {"team": "A", operation: expected[0]},
        {"team": "B", operation: expected[1]},
    ]


def test_boolean_number_text_null_keys_are_distinct_and_numeric_one_unified():
    response = run(
        [{"key": k} for k in [True, 1, 1.0, "1", None, False, 0]],
        {"operation": "count", "group_by": ["key"]},
    )
    assert response.status_code == 200
    result = response.json()["outputs"]["g"]
    assert result == [
        {"key": True, "count": 1},
        {"key": 1, "count": 2},
        {"key": "1", "count": 1},
        {"key": None, "count": 1},
        {"key": False, "count": 1},
        {"key": 0, "count": 1},
    ]


@pytest.mark.parametrize(
    "rows,params",
    [
        ([{}], {"operation": "count", "group_by": ["missing"]}),
        ([{"a": []}], {"operation": "count", "group_by": ["a"]}),
        (
            [{"sum": "x", "v": 1}],
            {"operation": "sum", "field": "v", "group_by": ["sum"]},
        ),
        ([{"a": 1}], {"operation": "count", "group_by": ["a", "a"]}),
        ([{"a": 1, "v": None}], {"operation": "sum", "field": "v", "group_by": ["a"]}),
    ],
)
def test_invalid_grouping_is_not_silently_merged(rows, params):
    assert run(rows, params).status_code == 422


def test_group_and_response_budgets_preserved():
    assert (
        run(
            [{"g": i} for i in range(1001)], {"operation": "count", "group_by": ["g"]}
        ).status_code
        == 422
    )
    response = run([], {"operation": "mean", "field": "v", "group_by": ["g"]})
    assert response.status_code == 200 and response.json()["outputs"]["g"] == []
    response = run([], {"operation": "count"})
    assert response.json()["outputs"]["g"] == [{"count": 0}]


def test_multiple_group_columns_and_csv_type_mapping():
    response = client.post(
        "/csv/analyze",
        json={
            "csv_text": "team,enabled,value\nA,true,1\nA,false,3\nA,true,5",
            "schema": {"team": "string", "enabled": "boolean", "value": "number"},
            "steps": [
                {
                    "op": "aggregate",
                    "params": {
                        "group_by": ["team", "enabled"],
                        "field": "value",
                        "operation": "mean",
                    },
                }
            ],
        },
    )
    assert response.status_code == 200
    assert response.json()["outputs"]["step_1"] == [
        {"team": "A", "enabled": True, "mean": 3},
        {"team": "A", "enabled": False, "mean": 3},
    ]
