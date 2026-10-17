"""Independent regression for observed missing-record loss in CSV import."""

import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.mark.parametrize(
    "csv_text, expected",
    [
        ("id,value\n,\na,1", [{"id": "", "value": ""}, {"id": "a", "value": "1"}]),
        ('id,value\n"",""\na,1', [{"id": "", "value": ""}, {"id": "a", "value": "1"}]),
        ("id,value\n\na,1\n\n", [{"id": "a", "value": "1"}]),
        ('value\n""\n1', [{"value": ""}, {"value": "1"}]),
    ],
)
def test_independent_preserve_explicit_empty_records(csv_text, expected):
    response = TestClient(app).post("/csv/preview", json={"csv_text": csv_text})
    assert response.status_code == 200, response.text
    assert response.json()["row_count"] == len(expected)
    assert response.json()["preview"] == expected


def test_independent_count_does_not_hide_missing_record():
    response = TestClient(app).post(
        "/csv/analyze",
        json={
            "csv_text": "id,value\n,\na,1",
            "schema": {"id": "string", "value": "number"},
            "steps": [{"op": "aggregate", "params": {"operation": "count"}}],
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["outputs"]["step_1"] == [{"count": 2}]
