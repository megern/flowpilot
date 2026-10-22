from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_task_workbench_and_bundled_assets():
    page = client.get("/")
    assert page.status_code == 200
    assert "Load synthetic example" in page.text
    assert "Export report" in page.text
    for path in ["/assets/app.js", "/assets/common.js", "/assets/styles.css", "/guide"]:
        assert client.get(path).status_code == 200
    assert "Intended use" in client.get("/guide").text
    assert app.version == "0.4.0"


from app.csv_import import parse_csv
import pytest


def test_quoted_csv_and_bom_preserve_text():
    headers, rows = parse_csv('\ufeffid,note\r\n001,"comma, and ""quoted"" text"\r\n')
    assert headers == ["id", "note"]
    assert rows == [{"id": "001", "note": 'comma, and "quoted" text'}]


def test_csv_rejects_duplicate_headers_ragged_records_and_invalid_quotes():
    for text in ["a, a\n1,2", "a,b\n1", 'a,b\n"unterminated,2', "a,b\n"]:
        assert client.post("/csv/preview", json={"csv_text": text}).status_code == 422


def test_csv_limits_and_inert_text_preview():
    assert (
        client.post(
            "/csv/preview", json={"csv_text": "a\n" + ("x" * 10001)}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/csv/preview", json={"csv_text": "a\n" + "1\n" * 10001}
        ).status_code
        == 422
    )
    result = client.post(
        "/csv/preview",
        json={"csv_text": "value\n<script>alert(1)</script>\n=SUM(A1:A2)"},
    ).json()
    assert result["preview"][0]["value"] == "<script>alert(1)</script>"
    assert result["preview"][1]["value"] == "=SUM(A1:A2)"
    assert result["row_count"] == 2


def test_real_csv_workflow_filters_and_aggregates():
    payload = {
        "csv_text": "team,value\nA,10\nB,20\nA,30",
        "schema": {"team": "string", "value": "number"},
        "steps": [
            {
                "op": "filter",
                "params": {"field": "team", "comparison": "eq", "value": "A"},
            },
            {"op": "aggregate", "params": {"field": "value", "operation": "sum"}},
        ],
    }
    response = client.post("/csv/analyze", json=payload)
    assert response.status_code == 200
    result = response.json()
    assert result["execution_order"] == ["source", "step_1", "step_2"]
    assert result["outputs"]["step_2"] == [{"sum": 40}]
    assert len(result["outputs"]["step_1"]) == 2


def test_csv_schema_and_numeric_failures_are_actionable():
    base = {
        "csv_text": "id,value\n001,not-a-number",
        "schema": {"id": "string", "value": "number"},
        "steps": [
            {"op": "aggregate", "params": {"field": "value", "operation": "mean"}}
        ],
    }
    result = client.post("/csv/analyze", json=base)
    assert result.status_code == 422 and "numeric" in result.json()["detail"]
    base["steps"] = [{"op": "exec", "params": {}}]
    assert client.post("/csv/analyze", json=base).status_code == 422
    base["steps"] = []
    base["schema"] = {"value": "number"}
    assert client.post("/csv/analyze", json=base).status_code == 422
