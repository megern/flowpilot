from fastapi.testclient import TestClient
from app.main import app


def test_review_order_actual_filter_mean():
    nodes = [
        {
            "id": "mean",
            "op": "aggregate",
            "depends_on": ["filter"],
            "params": {"field": "x", "operation": "mean"},
        },
        {
            "id": "filter",
            "op": "filter",
            "depends_on": ["source"],
            "params": {"field": "x", "comparison": "gt", "value": 2},
        },
        {
            "id": "source",
            "op": "source",
            "params": {"rows": [{"x": 1}, {"x": 3}, {"x": 5}]},
        },
    ]
    response = TestClient(app).post("/analyze", json={"nodes": nodes})
    assert response.status_code == 200
    assert response.json()["outputs"]["mean"] == [{"mean": 4}]
    assert response.json()["execution_order"] == ["source", "filter", "mean"]


def test_review_rejects_dynamic_code():
    response = TestClient(app).post(
        "/analyze",
        json={"nodes": [{"id": "s", "op": "exec", "params": {"code": "print(1)"}}]},
    )
    assert response.status_code == 422


def test_review_huge_integer_has_controlled_error():
    client = TestClient(app, raise_server_exceptions=False)
    data = {
        "nodes": [
            {"id": "s", "op": "source", "params": {"rows": [{"x": 10**400}]}},
            {
                "id": "a",
                "op": "aggregate",
                "depends_on": ["s"],
                "params": {"field": "x"},
            },
        ]
    }
    assert client.post("/analyze", json=data).status_code == 422


def test_review_source_overflow_exponent_controlled():
    response = TestClient(app, raise_server_exceptions=False).post(
        "/analyze",
        content='{"nodes":[{"id":"s","op":"source","params":{"rows":[{"x":1e400}]}}]}',
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422


def test_review_concat_growth_rejected():
    nodes = [
        {"id": "source", "op": "source", "params": {"rows": [{"x": 1}] * 10000}},
        {"id": "concat", "op": "concat", "depends_on": ["source"] * 50},
    ]
    response = TestClient(app).post("/analyze", json={"nodes": nodes})
    assert response.status_code == 422


def test_review_nested_source_bound_and_normal_data():
    nested = {"x": 1}
    for _ in range(40):
        nested = {"nested": nested}
    client = TestClient(app)
    response = client.post(
        "/analyze",
        json={"nodes": [{"id": "s", "op": "source", "params": {"rows": [nested]}}]},
    )
    assert response.status_code == 422
    response = client.post(
        "/analyze",
        json={
            "nodes": [
                {
                    "id": "s",
                    "op": "source",
                    "params": {
                        "rows": [{"nested": [True, None, "synthetic", {"x": 1.5}]}]
                    },
                }
            ]
        },
    )
    assert response.status_code == 200
    assert response.json()["outputs"]["s"][0]["nested"][-1]["x"] == 1.5


def test_review_response_amplification_rejected_below_row_cap():
    client = TestClient(app)
    source = {
        "id": "source",
        "op": "source",
        "params": {"rows": [{"text": "synthetic-" * 5000}]},
    }
    assert client.post("/analyze", json={"nodes": [source]}).status_code == 200
    data = {
        "nodes": [
            source,
            {
                "id": "amplified",
                "op": "concat",
                "depends_on": ["source"] * 20,
            },
        ]
    }
    response = client.post("/analyze", json=data)
    assert response.status_code == 422
    assert "serialized budget" in response.json()["detail"]


def test_review_small_nested_workflow_budget_preserves_values():
    client = TestClient(app)
    nodes = [
        {
            "id": "source",
            "op": "source",
            "params": {
                "rows": [
                    {"x": 2, "text": "سجل اصطناعي", "metadata": {"valid": True}},
                    {"x": 3, "text": "synthetic", "metadata": {"valid": False}},
                ]
            },
        },
        {"id": "copy", "op": "concat", "depends_on": ["source", "source"]},
        {
            "id": "project",
            "op": "select",
            "depends_on": ["copy"],
            "params": {"fields": ["x"]},
        },
        {
            "id": "sum",
            "op": "aggregate",
            "depends_on": ["project"],
            "params": {"field": "x"},
        },
    ]
    response = client.post("/analyze", json={"nodes": nodes})
    assert response.status_code == 200
    outputs = response.json()["outputs"]
    assert outputs["sum"] == [{"sum": 10}]
    assert outputs["copy"][0]["text"] == "سجل اصطناعي"
    assert len(outputs["project"]) == 4
