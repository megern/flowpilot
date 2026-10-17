# FlowPilot — User guide

## Intended use

A bounded, local transformation engine for repeatable tabular preparation. The visual builder handles a linear sequence of filters, column selections and aggregates; the API additionally supports declarative dependency graphs and concatenation.

## Walkthrough

1. Upload or paste comma-separated CSV with a unique header. Preview it and choose string, number or boolean for every column.
2. Add a filter, select columns or add an aggregate. Filters support eq, gt and lt. Numeric filters need numeric comparison values; boolean filters use true/false.
3. Reorder or remove steps. Each step consumes the previous output; after aggregation, later steps see aggregate column names rather than original fields.
4. Run analysis. Inspect the execution sequence, intermediate row counts and the final result. Tables display a bounded preview; exports include complete retained outputs.
5. Export the final CSV, full report or builder configuration. Reimport the configuration to repeat the workflow after checking types and steps.
6. The synthetic example keeps team A then sums values 10 and 30, producing 40. It is not a real business dataset.

## Method and interpretation

CSV parsing supports quoted commas and newlines, a UTF-8 BOM and CRLF. Headers are trimmed and must be unique. The first eight rows provide a provisional type suggestion; always review it. Blank cells become null. Numeric strings convert only under a number schema; invalid numeric or boolean strings remain strings so downstream operations can reject them rather than silently invent values.

Source, select, filter, aggregate and concat are allowlisted operations. The builder creates source plus step_1, step_2 etc. Cycles, unknown dependencies, invalid fields and unsupported parameters return validation errors. Aggregate count counts rows; sum on empty rows is 0; mean on empty rows is rejected.

There is no Python execution, shell command, HTTP connector, paid service, scheduling, durable job history, retry orchestration or automated action outside this server. This is data preparation, not a general enterprise automation platform.

## Examples and troubleshooting

If a filter rejects all rows, inspect its field, type and comparison before aggregating. If mean fails, the preceding output may be empty. If a field is missing, a select or aggregate may have changed the available columns. The builder does not rename columns. Grouped aggregation is available as an explicit optional step parameter.

CSV exports quote every cell and prefix potentially formula-like string values with an apostrophe; numeric negatives remain numbers. This reduces spreadsheet formula injection risk but cannot control how every third-party spreadsheet importer behaves.

## Resource and privacy limits

The HTTP guard bounds state-changing JSON bodies at 2 MiB and rejects excessive nesting, nonfinite numbers and numeric magnitudes beyond 1e100. CSV imports allow up to 50 unique columns and 10000 data records, with 10000-character cells. FlowPilot additionally caps each node at 10000 rows and conservatively bounds retained workflow outputs at 4 MiB. Browser previews and tables are bounded. Splitting files can change the analytical meaning: do not split event cases or evaluation splits arbitrarily.

The application is stateless and does not persist uploads. Your browser may retain downloads and form content; printed reports and configurations can contain the input data. No external resources or paid APIs are contacted. Requests go to the server you opened: self-host on a trusted machine. Authentication, multi-user access controls, secure ingress, rate limiting and operational backups are deployment responsibilities, not claims of this release.

## API and reuse

Open /docs for the complete schema. POST /analyze remains available for typed JSON inputs. CSV-based tools additionally provide POST /csv/preview and POST /csv/analyze. Configuration exports map directly to the relevant endpoint; readiness uses /analyze, the three CSV tools use /csv/analyze. Report exports contain application/version/date, synthetic provenance, original input and analytical output. They are data files, not executable programs.

All bundled examples are synthetic and are labeled. Editing or importing your own input resets that badge and clears stale results. Controls are locked during analysis; a generation check also prevents a late response replacing changed input results. Error messages identify the failed field or operation; correct it and rerun. Failed analyses never certify completion or preserve an old result as current.

## Local operation

Run docker compose up --build and open http://127.0.0.1:8000. Alternatively install requirements-dev.lock with hashes in a Python 3.12 environment and run uvicorn app.main:app --host 127.0.0.1 --port 8000. Change the host port to run multiple tools. No GPU is needed.

## Grouped aggregation in 0.3

Aggregate steps now offer optional “Group by columns”: enter up to eight unique comma-separated column names. Leaving it blank retains the previous whole-table sum, mean or count behavior. A CSV with team A values 10 and 30 and team B value 20 produces A sum 40 and B sum 20 when grouped by team. Multiple columns form a compound key. Grouping happens after all preceding transformations, so selected-away or renamed aggregate columns are not available.

The JSON aggregate params support “group_by”: ["team"]. Results keep the grouping columns and add the operation-named value column, such as sum or count. A grouping column cannot have the same name as the operation result. Groups appear in first-occurrence order and are capped at 1000; the existing 4 MiB retained-output budget still applies.

Typed scalar keys preserve distinctions between boolean true, numeric 1 and text “1”; numeric 1 and 1.0 belong to the same numeric group. Explicit null keys form a null group. Missing grouping columns and list/object keys are rejected. Invalid or missing numeric values are rejected by sum/mean, never silently dropped; count includes all member rows including null cells. With no source rows, grouped aggregation returns no groups. Ungrouped empty count/sum remain zero and mean is rejected. Use explicit CSV column types to control key interpretation.

Configuration import/export preserves group_by, and final CSV/report exports contain complete grouped outputs. The builder remains a linear transformation tool; there is still no scheduling, grouping expression execution or external action.
