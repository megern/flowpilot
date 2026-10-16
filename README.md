# FlowPilot · 0.2.0

**Inspectable data workflow builder.** A bounded, local transformation engine for repeatable tabular preparation. The visual builder handles a linear sequence of filters, column selections and aggregates; the API additionally supports declarative dependency graphs and concatenation.

The interface is a task-specific workbench, with labeled forms or CSV imports, previews, understandable diagnostics, charts/tables, actionable errors and reusable exports. It is a self-hosted engineering tool, not a claim of certified enterprise production readiness. Methods are deterministic and transparent; no paid service or GPU is required.

## Quickstart

```sh
docker compose up --build
```

Open http://127.0.0.1:8000. Click **Load synthetic example**, then **Run analysis**. Bundled data are explicitly synthetic. The full user guide is linked in the application at `/guide` and saved in [docs/USER_GUIDE.md](docs/USER_GUIDE.md). API schemas and examples are at `/docs`.

Run without Docker (Python 3.12):

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install --require-hashes -r requirements-dev.lock
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

For several apps, change the compose host port; each container listens on 8000. Stateless imports are processed in memory. Reports/configurations can contain your data and should be handled accordingly.

## Real functionality

CSV parsing supports quoted commas and newlines, a UTF-8 BOM and CRLF. Headers are trimmed and must be unique. The first eight rows provide a provisional type suggestion; always review it. Blank cells become null. Numeric strings convert only under a number schema; invalid numeric or boolean strings remain strings so downstream operations can reject them rather than silently invent values.

Source, select, filter, aggregate and concat are allowlisted operations. The builder creates source plus step_1, step_2 etc. Cycles, unknown dependencies, invalid fields and unsupported parameters return validation errors. Aggregate count counts rows; sum on empty rows is 0; mean on empty rows is rejected.

There is no Python execution, shell command, HTTP connector, paid service, scheduling, durable job history, retry orchestration or automated action outside this server. This is data preparation, not a general enterprise automation platform.

## Workflow and examples

1. Upload or paste comma-separated CSV with a unique header. Preview it and choose string, number or boolean for every column.
2. Add a filter, select columns or add an aggregate. Filters support eq, gt and lt. Numeric filters need numeric comparison values; boolean filters use true/false.
3. Reorder or remove steps. Each step consumes the previous output; after aggregation, later steps see aggregate column names rather than original fields.
4. Run analysis. Inspect the execution sequence, intermediate row counts and the final result. Tables display a bounded preview; exports include complete retained outputs.
5. Export the final CSV, full report or builder configuration. Reimport the configuration to repeat the workflow after checking types and steps.
6. The synthetic example keeps team A then sums values 10 and 30, producing 40. It is not a real business dataset.

The typed JSON API remains supported:

```sh
curl --fail-with-body http://127.0.0.1:8000/analyze -H 'Content-Type: application/json' --data-binary @examples/synthetic.json
```

CSV-based applications also expose `/csv/preview` and `/csv/analyze`, documented in `/docs`. `examples/synthetic-builder.json` is a complete CSV endpoint request; use it with `/csv/analyze`. Importing CSV never executes spreadsheet formulas. Exported CSV from FlowPilot neutralizes formula-like text. Report/configuration export is JSON; browser print can save the result to PDF. No report is represented as an independent audit certification.

## Validation and evidence

```sh
python -m pytest -q
node --test tests/ui.test.mjs
python -m bandit -r app -ll
python -m pip_audit --disable-pip --no-deps --require-hashes -r requirements.lock
```

New 0.2 validation is recorded under `evidence/rebuild/`. Older evidence documents the earlier implementation and must not be treated as proof of this interface. Meaningful existing arithmetic/security tests are retained. CI checks Python and frontend tests, dependency vulnerabilities, secret patterns, container vulnerabilities and real HTTP smoke operation. Require the `quality` check in repository branch protection to prevent merging failing revisions; a workflow alone cannot enforce that policy.

## Limits and troubleshooting

If a filter rejects all rows, inspect its field, type and comparison before aggregating. If mean fails, the preceding output may be empty. If a field is missing, a select or aggregate may have changed the available columns. The builder does not rename columns or group by a category.

CSV exports quote every cell and prefix potentially formula-like string values with an apostrophe; numeric negatives remain numbers. This reduces spreadsheet formula injection risk but cannot control how every third-party spreadsheet importer behaves.

HTTP JSON requests are bounded at 2 MiB; CSV parsing is bounded at 50 columns/10000 rows. Requests are local CPU work, no outside actions. Authentication and HTTPS are required when deploying beyond a trusted localhost environment. See the user guide for detailed method/resource limitations. This release provides no authentication, durable history or multi-user access management.

## License

MIT. See LICENSE. Review transitive dependency licenses for your distribution. Contributors and review evidence are automated engineering work; no human reviewer is invented.
