from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def join(left, right, **params):
    return {
        "nodes": [
            {"id": "l", "op": "source", "params": {"rows": left}},
            {"id": "r", "op": "source", "params": {"rows": right}},
            {
                "id": "j",
                "op": "join",
                "depends_on": ["l", "r"],
                "params": {
                    "left_on": ["id"],
                    "right_on": ["id"],
                    "how": "left",
                    **params,
                },
            },
        ]
    }


def test_typed_join_nulls_numeric_equivalence_and_unmatched_left_rows():
    payload = join(
        [{"id": True}, {"id": 1.0}, {"id": "1"}, {"id": None}],
        [
            {"id": 1, "v": "number"},
            {"id": "1", "v": "text"},
            {"id": None, "v": "null"},
            {"id": None, "v": "another-null"},
        ],
    )
    response = client.post("/analyze", json=payload)
    assert response.status_code == 200
    output = response.json()["outputs"]["j"]
    assert [row["right_v"] for row in output] == [None, "number", "text", None]
    assert [row["id"] for row in output] == [True, 1, "1", None]


def test_cardinality_collisions_and_retained_output_budget_are_enforced():
    assert (
        client.post(
            "/analyze", json=join([{"id": 1}], [{"id": 1}, {"id": 1.0}])
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/analyze",
            json=join([{"id": 1}, {"id": 1.0}], [{"id": 1}], cardinality="one_to_one"),
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/analyze",
            json=join([{"id": 1, "right_v": "original"}], [{"id": 1, "v": "new"}]),
        ).status_code
        == 422
    )
    payload = join(
        [{"id": i} for i in range(100)],
        [{"id": i, "v": "x" * 5000} for i in range(100)],
    )
    assert client.post("/analyze", json=payload).status_code == 422


def test_composite_null_does_not_hide_an_invalid_object_key_component():
    payload = join(
        [{"a": None, "b": {"nested": 1}}],
        [{"a": None, "b": {"nested": 1}}],
        left_on=["a", "b"],
        right_on=["a", "b"],
    )
    assert client.post("/analyze", json=payload).status_code == 422


def test_csv_join_mapping_and_grouped_result_are_actual_computation():
    payload = {
        "csv_text": "id,amount\nA,10\nA,5\nB,20",
        "schema": {"id": "string", "amount": "number"},
        "join": {
            "csv_text": "id,region\nA,North\nB,South",
            "schema": {"id": "string", "region": "string"},
            "left_on": ["id"],
            "right_on": ["id"],
            "how": "left",
            "cardinality": "many_to_one",
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
    }
    response = client.post("/csv/analyze", json=payload)
    assert response.status_code == 200
    assert response.json()["outputs"]["step_1"] == [
        {"right_region": "North", "sum": 15},
        {"right_region": "South", "sum": 20},
    ]
