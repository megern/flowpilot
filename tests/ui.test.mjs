import test from "node:test";
import assert from "node:assert/strict";
import {
  csvCell,
  csvExport,
  errorMessage,
  validatedSteps,
  getRevision,
  assertCurrent,
  invalidate,
  action,
  api,
} from "../app/static/common.js";

test("CSV export neutralizes formula-like text without changing numeric negatives", () => {
  assert.equal(csvCell("=SUM(A1:A2)"), '"\'=SUM(A1:A2)"');
  assert.equal(csvCell("  +1"), '"\'  +1"');
  assert.equal(csvCell("-3"), '"\'-3"');
  assert.equal(csvCell(-3), '"-3"');
  assert.equal(csvCell('a,"b"'), '"a,""b"""');
  assert.equal(
    csvExport(["name"], [{ name: "<script>alert(1)</script>" }]),
    '"name"\r\n"<script>alert(1)</script>"',
  );
});
test("builder only accepts supported declarative operations", () => {
  assert.throws(
    () => validatedSteps([{ op: "shell", params: { command: "x" } }]),
    /Unsupported/,
  );
  assert.throws(
    () =>
      validatedSteps(
        Array.from({ length: 50 }, () => ({ op: "select", params: {} })),
      ),
    /49/,
  );
  assert.deepEqual(
    validatedSteps([{ op: "aggregate", params: { operation: "count" } }]),
    [{ op: "aggregate", params: { operation: "count" } }],
  );
});
test("validation errors show the input location and useful message", () => {
  assert.equal(
    errorMessage([
      { loc: ["body", "events", 2, "timestamp"], msg: "Invalid timestamp" },
    ]),
    "body.events.2.timestamp: Invalid timestamp",
  );
});
function fakeDocument() {
  const nodes = new Map();
  const make = () => ({
    disabled: false,
    textContent: "",
    className: "",
    replaceChildren(...children) {
      this.children = children;
    },
  });
  for (const id of [
    "status",
    "run",
    "export-report",
    "print",
    "results",
    "technical",
    "input",
  ]) {
    const n = make();
    n.id = id;
    nodes.set(id, n);
  }
  nodes.get("export-report").disabled = true;
  nodes.get("print").disabled = true;
  global.document = {
    getElementById: (id) => nodes.get(id),
    createElement: () => make(),
    querySelectorAll: () =>
      [...nodes.values()].filter(
        (n) => !["status", "results", "technical"].includes(n.id),
      ),
  };
  return nodes;
}
test("a delayed result is rejected after input generation changes", () => {
  fakeDocument();
  const revision = getRevision();
  invalidate();
  assert.throws(() => assertCurrent(revision), /Inputs changed/);
  assert.doesNotThrow(() => assertCurrent(getRevision()));
});
test("pending work locks controls and restores them after failure without stale exports", async () => {
  const nodes = fakeDocument();
  let resume;
  const pending = new Promise((resolve) => (resume = resolve));
  const call = action(async () => {
    assert.equal(nodes.get("input").disabled, true);
    await pending;
    throw new Error("Synthetic validation failure");
  });
  assert.equal(nodes.get("run").disabled, true);
  assert.equal(nodes.get("input").disabled, true);
  resume();
  await call;
  assert.equal(nodes.get("input").disabled, false);
  assert.equal(nodes.get("run").disabled, false);
  assert.equal(nodes.get("export-report").disabled, true);
  assert.match(nodes.get("status").textContent, /Synthetic validation failure/);
});
test("non-200 API response becomes a validation failure", async () => {
  global.fetch = async () => ({
    ok: false,
    json: async () => ({
      detail: [{ loc: ["body", "csv_text"], msg: "CSV quoting invalid" }],
    }),
  });
  await assert.rejects(
    () => api("/csv/preview", { csv_text: "bad" }),
    /body.csv_text: CSV quoting invalid/,
  );
});

// Execute the real application event handlers with a small DOM fixture and deferred I/O.
// These are frontend state tests; they do not claim full browser rendering coverage.
import { fileURLToPath } from "node:url";
const appSlug = fileURLToPath(new URL("..", import.meta.url))
  .split("/")
  .filter(Boolean)
  .at(-1);
let importSequence = 0;
function applicationDOM() {
  const nodes = new Map();
  class Element {
    constructor(tag = "div") {
      this.tagName = tag;
      this.children = [];
      this.disabled = false;
      this.textContent = "";
      this.value = "";
      this.files = [];
      this.style = {};
      this.listeners = {};
      this.checked = false;
    }
    set id(value) {
      this._id = value;
      nodes.set(value, this);
    }
    get id() {
      return this._id;
    }
    append(...items) {
      this.children.push(...items);
      if (
        this.tagName === "select" &&
        this.value === "" &&
        items[0]?.value !== undefined
      )
        this.value = String(items[0].value);
    }
    replaceChildren(...items) {
      this.textContent = "";
      this.children = [];
      this.append(...items);
    }
    before(...items) {
      this.siblings = items;
    }
    after(...items) {
      this.siblings = items;
    }
    click() {}
    addEventListener(type, handler) {
      this.listeners[type] = handler;
    }
    querySelectorAll(selector) {
      return this.children.flatMap((n) => [
        ...((
          selector === "select"
            ? n.tagName === "select"
            : selector === "label"
              ? n.tagName === "label"
              : n.tagName === "input" &&
                (selector !== "input:checked" || n.checked)
        )
          ? [n]
          : []),
        ...n.querySelectorAll(selector),
      ]);
    }
  }
  const get = (id) => {
    if (!nodes.has(id)) {
      const node = new Element();
      node.id = id;
    }
    return nodes.get(id);
  };
  global.document = {
    getElementById: get,
    createElement: (tag) => new Element(tag),
    querySelectorAll: () => [...nodes.values()],
    querySelector: () => get("input-panel"),
  };
  return { nodes, get };
}
async function realApplication() {
  const fixture = applicationDOM();
  await import("../app/static/app.js?handler-test=" + ++importSequence);
  return fixture;
}
function markEdited(fixture) {
  if (appSlug === "ai-readiness-auditor") {
    fixture.get("score-strategy").value = "1";
    fixture.get("questions").listeners.input();
  } else {
    const field = appSlug === "mlops-doctor" ? "train" : "csv";
    fixture.get(field).value = "new_id,new_value\nnew,99";
    fixture.get(field).oninput();
  }
}
function inputValue(fixture) {
  return fixture.get(
    appSlug === "ai-readiness-auditor"
      ? "score-strategy"
      : appSlug === "mlops-doctor"
        ? "train"
        : "csv",
  ).value;
}
function requestConfiguration() {
  if (appSlug === "ai-readiness-auditor")
    return {
      dimensions: Object.fromEntries(
        ["strategy", "data", "governance", "people", "infrastructure"].map(
          (k) => [k, { score: 5, evidence: ["Synthetic delayed import"] }],
        ),
      ),
    };
  if (appSlug === "mlops-doctor")
    return {
      train_csv: "old,x,y\na,1,0",
      validation_csv: "old,x,y\nb,2,1",
      schema: { old: "string", x: "number", y: "number" },
      features: ["x"],
      id_column: "old",
      target: "y",
    };
  if (appSlug === "processminer-ai")
    return {
      csv_text: "case,activity,time\nold,Start,2026-01-01T00:00:00Z",
      case_column: "case",
      activity_column: "activity",
      timestamp_column: "time",
    };
  return {
    csv_text: "team,value\nold,1",
    schema: { team: "string", value: "number" },
    steps: [],
  };
}
function previewResponse() {
  return {
    ok: true,
    json: async () => ({
      columns: ["old", "x", "y"],
      row_count: 1,
      preview: [{ old: "old", x: "1", y: "0" }],
    }),
  };
}

test("actual configuration-import handler cannot overwrite edits after delayed file read", async () => {
  const fixture = await realApplication();
  let release;
  fixture.get("config-file").files = [
    { size: 50, text: () => new Promise((resolve) => (release = resolve)) },
  ];
  const pending = fixture.get("config-file").onchange();
  markEdited(fixture);
  const newest = inputValue(fixture),
    badge = fixture.get("data-origin").textContent;
  release(JSON.stringify(requestConfiguration()));
  await pending;
  assert.equal(inputValue(fixture), newest);
  assert.equal(fixture.get("data-origin").textContent, badge);
  assert.equal(fixture.get("export-report").disabled, true);
});

if (appSlug !== "ai-readiness-auditor") {
  test("actual preview handler discards delayed schema and mapping after an edit", async () => {
    const fixture = await realApplication();
    const releases = [];
    global.fetch = () => new Promise((resolve) => releases.push(resolve));
    fixture.get("csv").value = "old,x,y\nold,1,0";
    fixture.get("train").value = "old,x,y\nold,1,0";
    fixture.get("validation").value = "old,x,y\nother,2,0";
    fixture.get("preview-data").textContent = "Current preview sentinel";
    fixture.get("schema").textContent = "Current schema sentinel";
    fixture.get("case-column").value = "new_id";
    const pending = fixture.get("preview").onclick();
    assert.ok(releases.length >= 1);
    markEdited(fixture);
    const newest = inputValue(fixture);
    for (const release of releases) release(previewResponse());
    await pending;
    assert.equal(inputValue(fixture), newest);
    assert.equal(
      fixture.get("preview-data").textContent,
      "Current preview sentinel",
    );
    assert.equal(fixture.get("schema").textContent, "Current schema sentinel");
    assert.equal(fixture.get("case-column").value, "new_id");
  });
  test("actual synthetic-example completion cannot label edited input as synthetic", async () => {
    const fixture = await realApplication();
    const releases = [];
    global.fetch = () => new Promise((resolve) => releases.push(resolve));
    const pending = fixture.get("example").onclick();
    assert.ok(releases.length >= 1);
    markEdited(fixture);
    const newest = inputValue(fixture);
    for (const release of releases) release(previewResponse());
    await pending;
    assert.equal(inputValue(fixture), newest);
    assert.match(fixture.get("data-origin").textContent, /Your input/);
    assert.doesNotMatch(fixture.get("data-origin").textContent, /Synthetic/);
  });
  test("actual CSV-file handler cannot overwrite edits after delayed text read", async () => {
    const fixture = await realApplication();
    let release;
    let calls = 0;
    global.fetch = async () => {
      calls++;
      return previewResponse();
    };
    const fileID = appSlug === "mlops-doctor" ? "train-file" : "csv-file";
    fixture.get(fileID).files = [
      { size: 50, text: () => new Promise((resolve) => (release = resolve)) },
    ];
    const pending = fixture.get(fileID).onchange();
    markEdited(fixture);
    const newest = inputValue(fixture);
    release("old,x,y\nold,1,0");
    await pending;
    assert.equal(inputValue(fixture), newest);
    assert.equal(calls, 0);
  });
}

test("grouping columns from the real builder survive configuration export", async () => {
  const fixture = await realApplication();
  global.fetch = async () => ({
    ok: true,
    json: async () => ({
      columns: ["team", "value"],
      row_count: 2,
      preview: [
        { team: "A", value: "1" },
        { team: "B", value: "2" },
      ],
    }),
  });
  await fixture.get("example").onclick();
  fixture.get("group-by-1").value = "team";
  fixture.get("group-by-1").oninput();
  let exported;
  const original = URL.createObjectURL;
  const revoke = URL.revokeObjectURL;
  URL.createObjectURL = (blob) => ((exported = blob), "blob:test");
  URL.revokeObjectURL = () => {};
  try {
    fixture.get("export-config").onclick();
    const value = JSON.parse(await exported.text());
    assert.deepEqual(value.steps[1].params.group_by, ["team"]);
    assert.equal(value.steps[1].params.operation, "sum");
    assert.match(fixture.get("data-origin").textContent, /Your input/);
  } finally {
    URL.createObjectURL = original;
    URL.revokeObjectURL = revoke;
  }
});

test("actual secondary join preserves typed lookup schema and keys in builder export", async () => {
  const fixture = await realApplication();
  global.fetch = async (path, options) => {
    const body = JSON.parse(options.body);
    const secondary = body.csv_text.startsWith("customer,region");
    return {
      ok: true,
      json: async () =>
        secondary
          ? {
              columns: ["customer", "region"],
              row_count: 2,
              preview: [
                { customer: "A", region: "North" },
                { customer: "B", region: "South" },
              ],
            }
          : {
              columns: ["customer", "amount"],
              row_count: 3,
              preview: [
                { customer: "A", amount: "10" },
                { customer: "B", amount: "20" },
                { customer: "A", amount: "5" },
              ],
            },
    };
  };
  await fixture.get("join-example").onclick();
  let exported;
  const original = URL.createObjectURL,
    revoke = URL.revokeObjectURL;
  URL.createObjectURL = (b) => ((exported = b), "blob:test");
  URL.revokeObjectURL = () => {};
  try {
    fixture.get("export-config").onclick();
    const value = JSON.parse(await exported.text());
    assert.equal(value.schema.amount, "number");
    assert.equal(value.join.schema.customer, "string");
    assert.equal(value.join.schema.region, "string");
    assert.deepEqual(value.join.left_on, ["customer"]);
    assert.deepEqual(value.join.right_on, ["customer"]);
    assert.equal(value.join.how, "left");
    assert.equal(value.join.cardinality, "many_to_one");
  } finally {
    URL.createObjectURL = original;
    URL.revokeObjectURL = revoke;
  }
});
test("delayed secondary preview cannot replace schema after primary input edit", async () => {
  const fixture = await realApplication();
  let release;
  global.fetch = () => new Promise((r) => (release = r));
  fixture.get("join-csv").value = "k,v\n1,old";
  const pending = fixture.get("join-preview").onclick();
  markEdited(fixture);
  fixture.get("join-schema").textContent = "Current schema sentinel";
  release(previewResponse());
  await pending;
  assert.equal(
    fixture.get("join-schema").textContent,
    "Current schema sentinel",
  );
  assert.doesNotMatch(fixture.get("data-origin").textContent, /Synthetic/);
});

test("bubbling file change does not invalidate its own secondary CSV import", async () => {
  const fixture = await realApplication();
  let release;
  fixture.get("join-file").files = [
    { size: 50, text: () => new Promise((r) => (release = r)) },
  ];
  global.fetch = async () => ({
    ok: true,
    json: async () => ({
      columns: ["lookup", "v"],
      row_count: 1,
      preview: [{ lookup: "A", v: "1" }],
    }),
  });
  const pending = fixture.get("join-file").onchange();
  fixture
    .get("join-panel")
    .listeners.change({ target: fixture.get("join-file") });
  release("lookup,v\nA,1");
  await pending;
  assert.equal(fixture.get("join-csv").value, "lookup,v\nA,1");
  assert.equal(fixture.get("join-type-v").value, "number");
});

test("joined sample locks Run and new schema controls through both delayed previews", async () => {
  const fixture = await realApplication(),
    pendingRequests = [];
  fixture.get("join-cardinality").value = "one_to_one";
  fixture.get("join-how").value = "inner";
  global.fetch = (path, init) =>
    new Promise((resolve) => pendingRequests.push({ path, init, resolve }));
  const loading = fixture.get("join-example").onclick();
  assert.equal(fixture.get("run").disabled, true);
  assert.equal(fixture.get("join-example").disabled, true);
  assert.equal(fixture.get("csv").disabled, true);
  // Even an explicit handler call must not start analysis during the load.
  await fixture.get("run").onclick();
  assert.equal(pendingRequests.length, 1);
  assert.equal(pendingRequests[0].path, "/csv/preview");
  pendingRequests[0].resolve({
    ok: true,
    json: async () => ({
      columns: ["customer", "amount"],
      row_count: 3,
      preview: [
        { customer: "A", amount: "10" },
        { customer: "B", amount: "20" },
        { customer: "A", amount: "5" },
      ],
    }),
  });
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(pendingRequests.length, 2);
  assert.equal(fixture.get("run").disabled, true);
  assert.equal(fixture.get("type-amount").disabled, true);
  await fixture.get("run").onclick();
  assert.equal(pendingRequests.length, 2);
  pendingRequests[1].resolve({
    ok: true,
    json: async () => ({
      columns: ["customer", "region"],
      row_count: 2,
      preview: [
        { customer: "A", region: "North" },
        { customer: "B", region: "South" },
      ],
    }),
  });
  await loading;
  assert.equal(fixture.get("run").disabled, false);
  assert.equal(fixture.get("csv").disabled, false);
  assert.equal(fixture.get("type-amount").disabled, false);
  assert.equal(fixture.get("join-example").disabled, false);
  assert.equal(fixture.get("export-report").disabled, true);
  assert.match(fixture.get("data-origin").textContent, /Synthetic paired/);
  let request;
  global.fetch = async (path, init) => {
    request = JSON.parse(init.body);
    return {
      ok: false,
      json: async () => ({ detail: "Synthetic transport sentinel" }),
    };
  };
  await fixture.get("run").onclick();
  assert.deepEqual(request.join.schema, {
    customer: "string",
    region: "string",
  });
  assert.equal(request.join.how, "left");
  assert.equal(request.join.cardinality, "many_to_one");
});

test("joined sample restores controls on preview error and never enables stale report exports", async () => {
  const fixture = await realApplication();
  fixture.get("export-report").disabled = false;
  global.fetch = async () => ({
    ok: false,
    json: async () => ({ detail: "Synthetic preview failure" }),
  });
  await fixture.get("join-example").onclick();
  assert.equal(fixture.get("run").disabled, false);
  assert.equal(fixture.get("csv").disabled, false);
  assert.equal(fixture.get("join-example").disabled, false);
  assert.equal(fixture.get("export-report").disabled, true);
  assert.match(fixture.get("status").textContent, /Synthetic preview failure/);
});
