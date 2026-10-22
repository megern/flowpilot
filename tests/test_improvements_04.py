import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core import Request, analyze

client = TestClient(app)


def workflow(left, right, **params):
    return {
        "nodes": [
            {"id": "right", "op": "source", "params": {"rows": right}},
            {
                "id": "joined",
                "op": "join",
                "depends_on": ["left", "right"],
                "params": {"left_on": ["k"], "right_on": ["id"], **params},
            },
            {"id": "left", "op": "source", "params": {"rows": left}},
        ]
    }


def test_typed_join_sql_null_and_numeric_equivalence():
    r = analyze(
        Request(
            **workflow(
                [{"k": 1}, {"k": True}, {"k": "1"}, {"k": None}, {"k": 2}],
                [
                    {"id": 1.0, "v": "number"},
                    {"id": True, "v": "bool"},
                    {"id": "1", "v": "text"},
                    {"id": None, "v": "never"},
                ],
                how="left",
            )
        )
    )
    assert [row["right_v"] for row in r["outputs"]["joined"]] == [
        "number",
        "bool",
        "text",
        None,
        None,
    ]
    assert r["execution_order"].index("joined") > r["execution_order"].index("left")


def test_many_to_one_allows_repeated_left_but_inner_excludes_unmatched():
    r = client.post(
        "/analyze", json=workflow([{"k": 1}, {"k": 1}, {"k": 2}], [{"id": 1, "v": 4}])
    )
    assert r.status_code == 200 and len(r.json()["outputs"]["joined"]) == 2


@pytest.mark.parametrize(
    "left,right,params",
    [
        ([{"k": 1}, {"k": 1}], [{"id": 1}], {"cardinality": "one_to_one"}),
        ([{"k": 1}], [{"id": 1}, {"id": 1.0}], {}),
        ([{"missing": 1}], [{"id": 1}], {}),
        ([{"k": 1}], [{"other": 1}], {}),
        ([{"k": []}], [{"id": 1}], {}),
        ([{"k": 1, "right_id": 5}], [{"id": 1}], {}),
        ([{"k": 1}], [{"id": 1}], {"how": "outer"}),
        ([{"k": 1}], [{"id": 1}], {"cardinality": "many_to_many"}),
        ([{"k": 1}], [{"id": 1}], {"left_on": []}),
        ([{"k": 1}], [{"id": 1}], {"left_on": ["k"], "right_on": ["id", "x"]}),
    ],
)
def test_bad_join_returns_actionable_422(left, right, params):
    response = client.post("/analyze", json=workflow(left, right, **params))
    assert response.status_code == 422 and response.json()["detail"]


def test_csv_join_then_grouped_aggregate_and_empty_secondary_key():
    r = client.post(
        "/csv/analyze",
        json={
            "csv_text": "customer,amount\nA,10\nB,20\nA,5",
            "schema": {"customer": "string", "amount": "number"},
            "join": {
                "csv_text": "customer,region\nA,North\nB,South",
                "schema": {"customer": "string", "region": "string"},
                "left_on": ["customer"],
                "right_on": ["customer"],
            },
            "steps": [
                {
                    "op": "aggregate",
                    "params": {
                        "field": "amount",
                        "operation": "sum",
                        "group_by": ["right_region"],
                    },
                }
            ],
        },
    )
    assert r.status_code == 200
    assert r.json()["outputs"]["step_1"] == [
        {"right_region": "North", "sum": 15},
        {"right_region": "South", "sum": 20},
    ]


def test_join_retains_budget_and_two_distinct_dependencies():
    payload = workflow(
        [{"k": i, "v": "x" * 1000} for i in range(800)],
        [{"id": i} for i in range(800)],
        how="left",
    )
    response = client.post("/analyze", json=payload)
    assert response.status_code == 422 and "budget" in response.json()["detail"]
    payload = workflow([{"k": 1}], [{"id": 1}])
    payload["nodes"][1]["depends_on"] = ["left", "left"]
    assert client.post("/analyze", json=payload).status_code == 422


@pytest.mark.parametrize("invalid", [{}, [], [1]])
def test_null_composite_key_never_bypasses_later_scalar_validation(invalid):
    payload = workflow(
        [{"k": None, "other": invalid}],
        [{"id": None, "next": 1}],
        left_on=["k", "other"],
        right_on=["id", "next"],
        how="left",
    )
    assert client.post("/analyze", json=payload).status_code == 422
