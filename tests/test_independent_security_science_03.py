from fastapi.testclient import TestClient
from app.main import app


def test_independent_grouped_aggregation_preserves_scalar_identity_and_nulls():
    request = {
        "nodes": [
            {
                "id": "s",
                "op": "source",
                "params": {
                    "rows": [
                        {"g": True, "v": 4},
                        {"g": True, "v": 6},
                        {"g": 1, "v": 2},
                        {"g": "1", "v": 3},
                        {"g": None, "v": 5},
                    ]
                },
            },
            {
                "id": "g",
                "op": "aggregate",
                "depends_on": ["s"],
                "params": {"group_by": ["g"], "field": "v", "operation": "sum"},
            },
        ]
    }
    response = TestClient(app).post("/analyze", json=request)
    assert response.status_code == 200
    result = response.json()["outputs"]["g"]
    assert result == [
        {"g": True, "sum": 10},
        {"g": 1, "sum": 2},
        {"g": "1", "sum": 3},
        {"g": None, "sum": 5},
    ]


def test_independent_group_count_bound_and_invalid_csv_operation_are_validation_errors():
    client = TestClient(app, raise_server_exceptions=False)
    request = {
        "nodes": [
            {
                "id": "s",
                "op": "source",
                "params": {"rows": [{"g": i} for i in range(1001)]},
            },
            {
                "id": "g",
                "op": "aggregate",
                "depends_on": ["s"],
                "params": {"group_by": ["g"], "operation": "count"},
            },
        ]
    }
    assert client.post("/analyze", json=request).status_code == 422
    for operation in [[], {}, ["aggregate"]]:
        response = client.post(
            "/csv/analyze",
            json={
                "csv_text": "x\n1",
                "schema": {"x": "number"},
                "steps": [{"op": operation, "params": {}}],
            },
        )
        assert response.status_code == 422
