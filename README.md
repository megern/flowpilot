# FlowPilot · 0.4.0

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

Historical 0.2 validation is retained under `evidence/rebuild/`; current 0.3 checks are recorded under `evidence/improvements-0.3/`. Older evidence documents the earlier implementation and must not be treated as proof of this interface. Meaningful existing arithmetic/security tests are retained. CI checks Python and frontend tests, dependency vulnerabilities, secret patterns, container vulnerabilities and real HTTP smoke operation. Require the `quality` check in repository branch protection to prevent merging failing revisions; a workflow alone cannot enforce that policy.

## Limits and troubleshooting

If a filter rejects all rows, inspect its field, type and comparison before aggregating. If mean fails, the preceding output may be empty. If a field is missing, a select or aggregate may have changed the available columns. The builder does not rename columns. Grouped aggregation is available as an explicit optional step parameter.

CSV exports quote every cell and prefix potentially formula-like string values with an apostrophe; numeric negatives remain numbers. This reduces spreadsheet formula injection risk but cannot control how every third-party spreadsheet importer behaves.

HTTP JSON requests are bounded at 2 MiB; CSV parsing is bounded at 50 columns/10000 rows. Requests are local CPU work, no outside actions. Authentication and HTTPS are required when deploying beyond a trusted localhost environment. See the user guide for detailed method/resource limitations. This release provides optional shared-key API access and per-process compute admission. It does not provide durable history or multi-user access management; see docs/OPERATIONS.md.

## License

MIT. See LICENSE. Review transitive dependency licenses for your distribution. Contributors and review evidence are automated engineering work; no human reviewer is invented.

## Grouped aggregation in 0.3

Aggregate steps now offer optional “Group by columns”: enter up to eight unique comma-separated column names. Leaving it blank retains the previous whole-table sum, mean or count behavior. A CSV with team A values 10 and 30 and team B value 20 produces A sum 40 and B sum 20 when grouped by team. Multiple columns form a compound key. Grouping happens after all preceding transformations, so selected-away or renamed aggregate columns are not available.

The JSON aggregate params support “group_by”: ["team"]. Results keep the grouping columns and add the operation-named value column, such as sum or count. A grouping column cannot have the same name as the operation result. Groups appear in first-occurrence order and are capped at 1000; the existing 4 MiB retained-output budget still applies.

Typed scalar keys preserve distinctions between boolean true, numeric 1 and text “1”; numeric 1 and 1.0 belong to the same numeric group. Explicit null keys form a null group. Missing grouping columns and list/object keys are rejected. Invalid or missing numeric values are rejected by sum/mean, never silently dropped; count includes all member rows including null cells. With no source rows, grouped aggregation returns no groups. Ungrouped empty count/sum remain zero and mean is rejected. Use explicit CSV column types to control key interpretation.

Configuration import/export preserves group_by, and final CSV/report exports contain complete grouped outputs. The builder remains a linear transformation tool; there is still no scheduling, grouping expression execution or external action.

Fresh 0.3 validation is saved in `evidence/improvements-0.3/`; older reports describe earlier versions and are not proof of these additions. This is automated developer work with separate release-manager and independent QA gates; no human review or enterprise certification is claimed.

The new synthetic request `examples/synthetic-improvements-03.json` demonstrates this version. POST it to `/csv/analyze`; all data are synthetic.

## Two-source joins in 0.4

The optional secondary CSV section joins data before the existing linear filter/select/aggregate steps. Preview the primary CSV, enable the join, import or paste a secondary CSV, preview it and choose types for both tables. Enter ordered comma-separated left and right key lists (1–8 keys each). Choose inner or left join and declare one_to_one or many_to_one. The synthetic paired join uses three transactions for customers A/B and a two-row region lookup; it produces three rows with right_region before any optional steps.

Numeric 1 and 1.0 match, while boolean true and text “1” stay distinct. Composite keys match only if every component matches. Any null component never matches, including another null, as in SQL. Missing key columns are errors. Nonnull right keys must always be unique; one_to_one additionally requires unique nonnull left keys. Duplicate null keys are allowed because they never match. Many-to-many joins are deliberately rejected. There is no arbitrary expression, remote database connection or executable join predicate.

Left joins preserve every left row and fill unmatched right columns with null; inner joins keep matched left rows only. Right fields are prefixed right_ in the builder. A prefixed name colliding with a left column is rejected rather than silently overwriting it. The JSON DAG API can set right_prefix explicitly. Row order follows the left input. Empty right input has no discoverable right columns, so left rows remain unchanged in a left join. A right table's union of column names determines its output columns; absent non-key right cells become null.

POST /analyze accepts an op join node with exactly two distinct ordered dependencies [left, right] and params left_on, right_on, how, cardinality and optional right_prefix. Both dependencies are real executed source/transform nodes in the DAG. POST /csv/analyze adds an optional join object with secondary csv_text, schema and the same parameters. Old calls without join are unchanged. A joined builder has at most 47 subsequent steps (50 total nodes); every node remains limited to 10,000 rows and the full retained DAG outputs share a conservative 4 MiB budget. The request body remains bounded to 2 MiB, including both CSV strings together.

After a join, select or aggregate the right_ fields just like primary columns. Numeric filters honor secondary column types. Builder configuration/report/final CSV exports retain the join and its actual results. Reimported settings are treated as user input. If cardinality fails, deduplicate or correct the lookup upstream; never discard duplicates silently to make the check pass. Example: examples/synthetic-join.json posts directly to /csv/analyze and groups transaction amount by right_region, producing North=15 and South=20.

Developer validation for 0.4 is saved in `evidence/improvements-0.4/`. Prior evidence describes prior versions. Local developer tests do not establish independent acceptance, hosted CI success or deployment readiness.

## Server access and operating limits

See [Operations](docs/OPERATIONS.md) for optional shared-key API access, per-process request admission, platform notes and the additional work needed for public multi-user hosting.
