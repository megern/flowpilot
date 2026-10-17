from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from .core import Request, analyze
from .guard import InputGuard

app = FastAPI(title="FlowPilot", version="0.3.0")
app.add_middleware(InputGuard)
STATIC = Path(__file__).with_name("static")
app.mount("/assets", StaticFiles(directory=STATIC), name="assets")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.post("/analyze")
def run(request: Request):
    try:
        return analyze(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


from .csv_import import CSVPreview, parse_csv, convert_rows
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal


@app.post("/csv/preview")
def preview_csv(request: CSVPreview):
    try:
        headers, rows = parse_csv(request.csv_text)
        return {"columns": headers, "row_count": len(rows), "preview": rows[:8]}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


class CSVStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: Literal["filter", "select", "aggregate"]
    params: dict


class CSVWorkflow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    csv_text: str = Field(min_length=1, max_length=2097152)
    columns: dict[str, Literal["string", "number", "boolean"]] = Field(alias="schema")
    steps: list[CSVStep] = Field(default_factory=list, max_length=49)


@app.post("/csv/analyze")
def workflow_csv(request: CSVWorkflow):
    try:
        headers, rows = parse_csv(request.csv_text)
        if set(request.columns) != set(headers) or any(
            kind not in {"number", "string", "boolean"}
            for kind in request.columns.values()
        ):
            raise ValueError("Choose a valid type for every CSV column.")
        nodes = [
            {
                "id": "source",
                "op": "source",
                "params": {"rows": convert_rows(rows, request.columns)},
            }
        ]
        for index, step in enumerate(request.steps, start=1):
            nodes.append(
                {
                    "id": f"step_{index}",
                    "op": step.op,
                    "params": step.params,
                    "depends_on": ["source" if index == 1 else f"step_{index - 1}"],
                }
            )
        return analyze(Request(nodes=nodes))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/guide")
def user_guide():
    return FileResponse(STATIC / "guide.html")
