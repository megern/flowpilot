import {
  getRevision,
  isStale,
  assertCurrent,
  $,
  el,
  replace,
  table,
  previewRows,
  metrics,
  api,
  action,
  status,
  newReport,
  setupExports,
  invalidate,
  bindFile,
  readFile,
  schemaEditor,
  selectField,
  setOptions,
  validatedSteps,
  csvExport,
  download,
} from "./common.js";
let steps = [],
  columns = [],
  getSchema = () => ({}),
  synthetic = false,
  report = null;
function dirty() {
  synthetic = false;
  report = null;
  $("data-origin").textContent = "Your input · changed";
  $("technical").textContent = "Inputs changed. Run again.";
  invalidate();
}
$("csv").oninput = dirty;
$("schema").onchange = dirty;
async function preview() {
  report = null;
  invalidate();
  const generation = getRevision();
  const r = await api("/csv/preview", { csv_text: $("csv").value });
  assertCurrent(generation);
  columns = r.columns;
  replace(
    $("preview-data"),
    el(
      "p",
      `${r.row_count} source rows · first ${r.preview.length} shown`,
      "hint",
    ),
    previewRows(columns, r.preview),
  );
  getSchema = schemaEditor($("schema"), columns, r.preview);
  renderSteps();
  return { ...r, generation };
}
$("preview").onclick = async () => {
  try {
    dirty();
    const prepared = await preview();
    assertCurrent(prepared.generation);
    status("CSV parsed. Review column types and add your steps.");
  } catch (e) {
    if (isStale(e)) return;
    status(e.message, true);
  }
};
bindFile(
  "csv-file",
  "csv",
  async () => {
    dirty();
    const prepared = await preview();
    assertCurrent(prepared.generation);
    status("Imported your CSV. Review the inferred column types.");
  },
  dirty,
);
function renderSteps() {
  replace($("steps"));
  steps.forEach((step, index) => {
    const box = el("div", "", "step");
    box.append(el("h3", `${index + 1}. ${step.op}`));
    const controls = el("div");
    if (step.op === "filter") {
      const field = selectField(
          "filter-field-" + index,
          "Column",
          columns,
          step.params.field,
        ),
        comparison = selectField(
          "comparison-" + index,
          "Keep rows when",
          ["eq", "gt", "lt"],
          step.params.comparison,
        );
      const label = el("label", "Comparison value"),
        input = el("input");
      input.id = "value-" + index;
      label.htmlFor = input.id;
      input.value = step.params.value ?? "";
      field.control.onchange = () => {
        step.params.field = field.control.value;
        dirty();
      };
      comparison.control.onchange = () => {
        step.params.comparison = comparison.control.value;
        dirty();
      };
      input.oninput = () => {
        step.params.value = input.value;
        dirty();
      };
      controls.append(field.box, comparison.box, label, input);
    } else if (step.op === "select") {
      const label = el("label", "Columns to keep (comma-separated)"),
        input = el("input");
      input.id = "fields-" + index;
      label.htmlFor = input.id;
      input.value = (step.params.fields || []).join(", ");
      input.oninput = () => {
        step.params.fields = input.value
          .split(",")
          .map((x) => x.trim())
          .filter(Boolean);
        dirty();
      };
      controls.append(label, input);
    } else {
      const field = selectField(
          "aggregate-field-" + index,
          "Numeric column",
          columns,
          step.params.field,
        ),
        op = selectField(
          "operation-" + index,
          "Operation",
          ["sum", "mean", "count"],
          step.params.operation,
        );
      field.control.onchange = () => {
        step.params.field = field.control.value;
        dirty();
      };
      op.control.onchange = () => {
        step.params.operation = op.control.value;
        dirty();
      };
      const groupLabel = el(
          "label",
          "Group by columns (comma-separated, optional)",
        ),
        groupInput = el("input");
      groupInput.id = "group-by-" + index;
      groupLabel.htmlFor = groupInput.id;
      groupInput.value = (step.params.group_by || []).join(", ");
      groupInput.oninput = () => {
        step.params.group_by = groupInput.value
          .split(",")
          .map((value) => value.trim())
          .filter(Boolean);
        dirty();
      };
      controls.append(
        groupLabel,
        groupInput,
        el(
          "p",
          "Blank groups all rows together. Up to 8 columns and 1,000 groups. Null keys form a group; missing columns are errors. Boolean, numeric and text keys stay distinct.",
          "hint",
        ),
      );
      controls.append(
        field.box,
        op.box,
        el(
          "p",
          "Count uses all rows. Sum/mean require numeric values; choose the output of prior steps carefully.",
          "hint",
        ),
      );
    }
    box.append(controls);
    const actions = el("div", "", "actions");
    for (const [text, handler, disabled] of [
      [
        "Move up",
        () => {
          [steps[index - 1], steps[index]] = [steps[index], steps[index - 1]];
        },
        index === 0,
      ],
      [
        "Move down",
        () => {
          [steps[index + 1], steps[index]] = [steps[index], steps[index + 1]];
        },
        index === steps.length - 1,
      ],
      ["Remove", () => steps.splice(index, 1), false],
    ]) {
      const b = el("button", text);
      b.disabled = disabled;
      b.onclick = () => {
        handler();
        dirty();
        renderSteps();
      };
      actions.append(b);
    }
    box.append(actions);
    $("steps").append(box);
  });
}
function add(op) {
  if (steps.length >= 49) {
    status("Maximum 49 builder steps. Remove a step first.", true);
    return;
  }
  if (!columns.length) {
    status("Preview your CSV before adding steps.", true);
    return;
  }
  steps.push({
    op,
    params:
      op === "filter"
        ? { field: columns[0], comparison: "eq", value: "" }
        : op === "select"
          ? { fields: [...columns] }
          : {
              field:
                columns.find((c) => getSchema()[c] === "number") || columns[0],
              operation: "sum",
            },
  });
  dirty();
  renderSteps();
}
for (const op of ["filter", "select", "aggregate"])
  $("add-" + op).onclick = () => add(op);
function config() {
  const schema = getSchema();
  const transformed = steps.map((s) => ({ op: s.op, params: { ...s.params } }));
  for (const step of transformed) {
    if (step.op === "filter" && schema[step.params.field] === "number") {
      const raw = step.params.value;
      if (String(raw).trim() === "" || !Number.isFinite(Number(raw)))
        throw new Error("Numeric filters need a finite comparison value.");
      step.params.value = Number(raw);
    }
    if (step.op === "filter" && schema[step.params.field] === "boolean") {
      if (!["true", "false"].includes(String(step.params.value).toLowerCase()))
        throw new Error("Boolean filter values must be true or false.");
      step.params.value = String(step.params.value).toLowerCase() === "true";
    }
  }
  return {
    csv_text: $("csv").value,
    schema,
    steps: validatedSteps(transformed),
  };
}
$("example").onclick = async () => {
  try {
    dirty();
    $("csv").value = "team,value\nA,10\nB,20\nA,30";
    steps = [
      { op: "filter", params: { field: "team", comparison: "eq", value: "A" } },
      { op: "aggregate", params: { field: "value", operation: "sum" } },
    ];
    const prepared = await preview();
    assertCurrent(prepared.generation);
    synthetic = true;
    $("data-origin").textContent = "Synthetic example · no real records";
    status(
      "Synthetic workflow loaded: keep team A, then sum value. Expected total: 40.",
    );
  } catch (e) {
    if (isStale(e)) return;
    status(e.message, true);
  }
};
$("config-file").onchange = async () => {
  try {
    dirty();
    const generation = getRevision();
    const text = await readFile($("config-file"));
    assertCurrent(generation);
    if (text === null) return;
    const data = JSON.parse(text);
    if (
      typeof data.csv_text !== "string" ||
      !Array.isArray(data.steps) ||
      !data.schema
    )
      throw new Error(
        "Use a FlowPilot builder configuration exported by this tool.",
      );
    validatedSteps(data.steps);
    steps = data.steps.map((s) => ({ op: s.op, params: { ...s.params } }));
    $("csv").value = data.csv_text;
    dirty();
    const prepared = await preview();
    assertCurrent(prepared.generation);
    for (const [c, t] of Object.entries(data.schema)) {
      const select = document.getElementById("type-" + c);
      if (select && ["number", "boolean", "string"].includes(t))
        select.value = t;
    }
    status("Imported configuration. Check types and steps before running.");
  } catch (e) {
    if (isStale(e)) return;
    dirty();
    status("Cannot import configuration: " + e.message, true);
  }
};
$("run").onclick = () =>
  action(async () => {
    report = null;
    const input = config(),
      generation = getRevision(),
      result = await api("/csv/analyze", input);
    assertCurrent(generation);
    report = newReport("FlowPilot", input, result, synthetic);
    const final = result.outputs[result.execution_order.at(-1)];
    replace(
      $("results"),
      metrics([
        ["Executed nodes", result.execution_order.length],
        ["Final rows", final.length],
      ]),
      el("p", result.execution_order.join(" → "), "notice"),
    );
    for (const id of result.execution_order) {
      const rows = result.outputs[id],
        details = el("details");
      details.open = id === result.execution_order.at(-1);
      details.append(el("summary", id + " · " + rows.length + " rows"));
      if (rows.length) {
        const cols = [...new Set(rows.flatMap((r) => Object.keys(r)))];
        details.append(
          table(
            cols,
            rows.slice(0, 100).map((r) => cols.map((c) => r[c] ?? null)),
          ),
        );
        if (rows.length > 100)
          details.append(
            el(
              "p",
              "First 100 rows shown. Export the report or final CSV for all rows.",
              "hint",
            ),
          );
      } else
        details.append(
          el(
            "p",
            "No rows. Check whether the preceding filter excluded all data.",
          ),
        );
      $("results").append(details);
    }
    if (final.length) {
      const exportButton = el("button", "Export final CSV");
      exportButton.onclick = () =>
        download(
          "flowpilot-final.csv",
          csvExport([...new Set(final.flatMap((r) => Object.keys(r)))], final),
          "text/csv",
        );
      $("results").append(exportButton);
    }
    $("results").append(
      el(
        "p",
        "Next: inspect intermediate outputs, adjust your steps, then export the configuration for reuse. This engine does not schedule jobs or execute scripts.",
        "hint",
      ),
    );
    $("technical").textContent = JSON.stringify(result, null, 2);
    $("export-report").disabled = false;
    $("print").disabled = false;
  });
setupExports(
  "flowpilot",
  () => report,
  () => {
    try {
      return config();
    } catch (e) {
      if (isStale(e)) return;
      status(e.message, true);
      return { csv_text: $("csv").value, schema: getSchema(), steps };
    }
  },
);
