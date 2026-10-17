let revision = 0;
export const getRevision = () => revision;
export const isStale = (error) => error?.code === "STALE_INPUT";
export const assertCurrent = (generation) => {
  if (generation !== revision) {
    const error = new Error(
      "Inputs changed while processing. Run again with the current input.",
    );
    error.code = "STALE_INPUT";
    throw error;
  }
};
export const $ = (id) => document.getElementById(id);
export function el(tag, text = "", className = "") {
  const n = document.createElement(tag);
  if (text !== undefined) n.textContent = String(text);
  if (className) n.className = className;
  return n;
}
export function replace(node, ...children) {
  node.replaceChildren(...children);
}
export function table(headers, rows) {
  const wrap = el("div", "", "table-wrap"),
    t = el("table"),
    head = el("thead"),
    tr = el("tr");
  for (const h of headers) tr.append(el("th", h));
  head.append(tr);
  t.append(head);
  const b = el("tbody");
  for (const row of rows.slice(0, 200)) {
    const r = el("tr");
    for (const v of row)
      r.append(
        el(
          "td",
          v === null
            ? "Missing"
            : typeof v === "object"
              ? JSON.stringify(v)
              : v,
        ),
      );
    b.append(r);
  }
  t.append(b);
  wrap.append(t);
  if (rows.length > 200)
    wrap.append(
      el(
        "p",
        "First 200 rows shown. Export the report for all results.",
        "hint",
      ),
    );
  return wrap;
}
export function previewRows(columns, rows) {
  return table(
    columns,
    rows.slice(0, 8).map((r) => columns.map((c) => r[c] ?? "")),
  );
}
export function bars(items, max) {
  const box = el("div");
  for (const [label, value] of items) {
    const row = el("div", "", "barrow"),
      track = el("div", "", "track"),
      fill = el("div", "", "fill");
    fill.style.width =
      Math.min(100, Math.max(0, (value / (max || 1)) * 100)) + "%";
    track.append(fill);
    row.append(el("span", label), track, el("span", format(value)));
    box.append(row);
  }
  return box;
}
export function format(x) {
  return typeof x === "number"
    ? Number(x.toPrecision(5)).toLocaleString()
    : String(x ?? "Not defined");
}
export function metrics(items) {
  const box = el("div", "", "kpis");
  for (const [name, value] of items) {
    const item = el("div");
    item.append(el("div", format(value), "metric"), el("div", name, "hint"));
    box.append(item);
  }
  return box;
}
export function errorMessage(detail) {
  if (Array.isArray(detail))
    return detail
      .map((e) => [...(e.loc || [])].join(".") + ": " + e.msg)
      .join("\n");
  return typeof detail === "string" ? detail : JSON.stringify(detail);
}
export function status(text, error = false) {
  $("status").textContent = text;
  $("status").className = "status" + (error ? " error" : "");
}
export async function api(path, payload) {
  const generation = getRevision();
  try {
    const response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    assertCurrent(generation);
    const result = await response.json();
    assertCurrent(generation);
    if (!response.ok) throw new Error(errorMessage(result.detail || result));
    return result;
  } catch (error) {
    assertCurrent(generation);
    throw error;
  }
}
export async function action(task) {
  invalidate();
  $("technical").textContent = "Analysis pending.";
  status("Working…");
  const controls = [
    ...document.querySelectorAll("input,select,textarea,button"),
  ].map((n) => [n, n.disabled]);
  for (const [n] of controls) n.disabled = true;
  try {
    await task();
    status("Analysis complete. Results use the data supplied for this run.");
  } catch (e) {
    status(
      e.message + "\nCheck the indicated field or column, then try again.",
      true,
    );
  } finally {
    for (const [n, disabled] of controls)
      if (!["export-report", "print"].includes(n.id)) n.disabled = disabled;
    $("run").disabled = false;
  }
}
export function download(name, data, type = "application/json") {
  const blob = new Blob(
    [typeof data === "string" ? data : JSON.stringify(data, null, 2)],
    { type },
  );
  const url = URL.createObjectURL(blob),
    link = el("a");
  link.href = url;
  link.download = name;
  link.click();
  URL.revokeObjectURL(url);
}
export function csvCell(value) {
  const raw = value === null || value === undefined ? "" : String(value);
  const safe =
    typeof value === "string" && /^[\s]*[=+@-]/.test(raw) ? "'" + raw : raw;
  return '"' + safe.replaceAll('"', '""') + '"';
}
export function csvExport(headers, rows) {
  return [headers, ...rows.map((r) => headers.map((h) => r[h]))]
    .map((r) => r.map(csvCell).join(","))
    .join("\r\n");
}
export async function readFile(input) {
  const file = input.files?.[0];
  if (!file) return null;
  if (file.size > 2097152)
    throw new Error("File exceeds 2 MiB. Reduce or split it before importing.");
  const generation = getRevision();
  try {
    const text = await file.text();
    assertCurrent(generation);
    return text;
  } catch (error) {
    assertCurrent(generation);
    throw error;
  }
}
export function option(value, text = value) {
  const o = el("option", text);
  o.value = value;
  return o;
}
export function setOptions(select, values, selected) {
  replace(select, ...values.map((v) => option(v)));
  if (values.includes(selected)) select.value = selected;
}
export function selectField(id, label, values, value) {
  const box = el("div"),
    l = el("label", label),
    s = el("select");
  s.id = id;
  l.htmlFor = id;
  for (const v of values) s.append(option(v));
  if (value !== undefined) s.value = value;
  box.append(l, s);
  return { box, control: s };
}
export function schemaEditor(node, columns, rows) {
  const controls = {};
  replace(node);
  for (const column of columns) {
    const cells = rows.map((r) => r[column]?.trim()).filter(Boolean);
    const inferred =
      cells.length && cells.every((v) => Number.isFinite(Number(v)))
        ? "number"
        : cells.length &&
            cells.every((v) => ["true", "false"].includes(v.toLowerCase()))
          ? "boolean"
          : "string";
    const f = selectField(
      "type-" + column,
      column + " type",
      ["string", "number", "boolean"],
      column.toLowerCase().includes("id") ? "string" : inferred,
    );
    controls[column] = f.control;
    node.append(f.box);
  }
  return () => Object.fromEntries(columns.map((c) => [c, controls[c].value]));
}
export function bindFile(fileId, textId, onChange, onStart) {
  $(fileId).onchange = async () => {
    try {
      if (onStart) onStart();
      const generation = getRevision();
      const text = await readFile($(fileId));
      assertCurrent(generation);
      if (text !== null) {
        $(textId).value = text;
        await onChange();
      }
    } catch (e) {
      if (isStale(e)) return;
      status(e.message, true);
    }
  };
}
export function newReport(app, input, result, synthetic) {
  return {
    application: app,
    version: "0.3.0",
    created_at: new Date().toISOString(),
    synthetic_example: synthetic,
    input,
    result,
  };
}
export function setupExports(app, getReport, getConfig) {
  $("export-report").onclick = () => {
    const r = getReport();
    if (r) download(app + "-report.json", r);
  };
  $("export-config").onclick = () =>
    download(app + "-config.json", getConfig());
  $("print").onclick = () => window.print();
}
export function invalidate() {
  revision++;
  for (const id of ["export-report", "print"]) $(id).disabled = true;
  $("results").replaceChildren(
    el("p", "Inputs changed. Run analysis to refresh these results.", "empty"),
  );
}
export function validatedSteps(steps) {
  if (steps.length > 49) throw new Error("Use at most 49 steps.");
  return steps.map((step) => {
    if (!["filter", "select", "aggregate"].includes(step.op))
      throw new Error("Unsupported builder step.");
    return { op: step.op, params: step.params };
  });
}
