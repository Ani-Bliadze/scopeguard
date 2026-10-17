// ScopeGuard pitch deck generator (PptxGenJS). Every metric shown is read from measured evidence in
// docs/demo_results.json (+ docs/demo_results_live.json). The build FAILS rather than inventing numbers.
// Usage: npm run pitch:build   (from the repo root)

const fs = require("fs");
const path = require("path");
const pptxgen = require("pptxgenjs");
const { applyTheme } = require("./lib/apply_theme.js");

const ROOT = path.join(__dirname, "..");
const A = (...p) => path.join(__dirname, "assets", ...p);
const OUT = path.join(__dirname, "ScopeGuard_Pitch.pptx");

// ------------------------------------------------------------------ evidence (fail closed)
function fail(msg) {
  console.error("DECK BUILD FAILED:", msg);
  process.exit(1);
}
function readJson(p) {
  if (!fs.existsSync(p)) fail(`missing ${path.relative(ROOT, p)}; run scripts.run_demo_scenarios first`);
  return JSON.parse(fs.readFileSync(p, "utf8"));
}
const E = readJson(path.join(ROOT, "docs", "demo_results.json"));
const LIVE = fs.existsSync(path.join(ROOT, "docs", "demo_results_live.json"))
  ? readJson(path.join(ROOT, "docs", "demo_results_live.json"))
  : null;
const SA = E.scenarios.A_safe_replan_sales_by_region;
const SB1 = E.scenarios.B1_secret_request_hard_deny;
const SB2 = E.scenarios.B2_backend_credential_use;
const PROBES = E.scenarios.D_compromised_agent_probes_scripted;
const risky = SA.candidates.find((c) => c.tool === "crm.get_customers");
const txn = SA.candidates.find((c) => c.tool === "analytics.get_transactions");
const safe = SA.candidates.find((c) => c.selected);
if (SA.status !== "COMPLETED" || !SA.independent_sql_totals_match) fail("scenario A did not complete with SQL-matching totals");
if (!risky || risky.decision !== "DENY" || !safe || safe.tool !== "analytics.get_sales_summary") fail("unexpected plan selection");
if (SA.metrics.personal_field_values_returned_to_model !== 0) fail("personal values reached the model");
if (SB1.block_code !== "HARD_DENY_SECRET_DISCLOSURE") fail("secret scenario not hard-denied");
if (!SB2.result || SB2.result.connected !== true) fail("connection scenario failed");
if (E.model_boundary_scan.canary_occurrences !== 0) fail("canary found in model-bound payloads");
const probeList = Object.values(PROBES);
if (!probeList.every((p) => p.metrics.prohibited_upstream_dispatches === 0)) fail("a probe reached upstream");
const shots = ["demo-sales.png", "demo-secret.png", "demo-connection.png"];
for (const s of shots) if (!fs.existsSync(A(s))) fail(`missing screenshot pitch/assets/${s}; run capture_demo --assets`);
fs.writeFileSync(A("evidence.json"), JSON.stringify({ deterministic: E, live: LIVE }, null, 2));

const n = (v) => Number(v).toLocaleString("en-US");
const M = SA.metrics;
const PY = E.tests.python;
const E2E = E.tests.e2e;
const probesDenied = probeList.reduce((s, p) => s + p.metrics.gateway_calls_denied, 0);
const probeCalls = probeList.length;
const liveModel = LIVE && LIVE.effective_provider !== "deterministic" ? LIVE.live_model : null;
const liveOk = liveModel && LIVE.scenarios.A_safe_replan_sales_by_region.status === "COMPLETED"
  && LIVE.scenarios.A_safe_replan_sales_by_region.metrics.personal_field_values_returned_to_model === 0;
const shotLabel = liveOk ? `live mode (${liveModel})` : "deterministic demo mode";

// ------------------------------------------------------------------ theme + layouts
const THEME = {
  name: "ScopeGuard Night",
  headFontFace: "Calibri",
  bodyFontFace: "Calibri",
  colors: {
    dk1: "0B1220", lt1: "F2F6FC", dk2: "142033", lt2: "9AA9C2",
    accent1: "2DD4BF", accent2: "FB7185", accent3: "FBBF24", accent4: "7DD3FC", accent5: "C4B5FD", accent6: "34D399",
    hlink: "7DD3FC", folHlink: "C4B5FD",
  },
};
const HEX = { navy: "0B1220", panel: "142033", panel2: "1B2A42", line: "2A3A55", white: "F2F6FC", muted: "9AA9C2",
  teal: "2DD4BF", rose: "FB7185", amber: "FBBF24", sky: "7DD3FC" };

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.333 x 7.5 in
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
pres.title = "ScopeGuard pitch";
pres.subject = "Privacy-aware data firewall for MCP-powered AI agents";
pres.author = "ScopeGuard hackathon team";
const C = pres.SchemeColor;
const K = { navy: C.text1, panel: C.text2, white: C.background1, muted: C.background2, teal: C.accent1, rose: C.accent2,
  amber: C.accent3, sky: C.accent4, violet: C.accent5 };
const S = pres.shapes;

const FOOTER = { text: "ScopeGuard · synthetic, task-scoped local demo", options: { x: 0.6, y: 7.02, w: 6, h: 0.3, fontSize: 10, color: K.muted, margin: 0 } };
pres.defineSlideMaster({
  title: "SG_CONTENT",
  background: { color: HEX.navy },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 0.38, w: 12.13, h: 0.9, fontSize: 34, bold: true,
      color: K.white, valign: "middle", align: "left", margin: 0 }, text: "" } },
    { text: FOOTER },
  ],
  slideNumber: { x: 12.23, y: 7.02, w: 0.5, h: 0.3, fontSize: 10, color: HEX.muted, align: "right" },
});
pres.defineSlideMaster({
  title: "SG_HERO",
  background: { color: HEX.navy },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 1.25, w: 6.6, h: 2.6, fontSize: 40, bold: true,
      color: K.white, valign: "top", align: "left", margin: 0 }, text: "" } },
    { text: FOOTER },
  ],
});
pres.defineSlideMaster({
  title: "SG_CLOSE",
  background: { color: HEX.navy },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 5.55, w: 12.13, h: 0.95, fontSize: 36, bold: true,
      color: K.teal, valign: "middle", align: "left", margin: 0 }, text: "" } },
    { text: FOOTER },
  ],
  slideNumber: { x: 12.23, y: 7.02, w: 0.5, h: 0.3, fontSize: 10, color: HEX.muted, align: "right" },
});

// ------------------------------------------------------------------ helpers
function txt(slide, text, o) {
  slide.addText(text, { isTextBox: true, margin: 0, color: K.white, fontSize: 16, valign: "top", ...o });
}
function card(slide, x, y, w, h, o = {}) {
  slide.addShape(S.ROUNDED_RECTANGLE, {
    x, y, w, h, rectRadius: o.r ?? 0.12, objectName: o.name,
    fill: { color: o.fill ?? K.panel, transparency: o.transparency ?? 0 },
    line: { color: o.line ?? HEX.line, width: o.lineW ?? 1 },
    shadow: o.shadow ? { type: "outer", color: "000000", opacity: 0.35, blur: 8, offset: 3, angle: 90 } : undefined,
  });
}
function icon(slide, name, color, x, y, size) {
  slide.addImage({ path: A("icons", `${name}-${color}.png`), x, y, w: size, h: size, altText: name });
}
function iconChip(slide, name, color, scheme, x, y, size = 0.62) {
  slide.addShape(S.ROUNDED_RECTANGLE, { x, y, w: size, h: size, rectRadius: 0.14, fill: { color: scheme, transparency: 82 },
    line: { color: scheme, width: 1, transparency: 40 } });
  icon(slide, name, color, x + size * 0.18, y + size * 0.18, size * 0.64);
}
function pill(slide, x, y, w, text, scheme, o = {}) {
  slide.addShape(S.ROUNDED_RECTANGLE, { x, y, w, h: o.h ?? 0.36, rectRadius: 0.18, fill: { color: scheme, transparency: 80 },
    line: { color: scheme, width: 1 }, objectName: o.name });
  txt(slide, text, { x, y, w, h: o.h ?? 0.36, fontSize: o.size ?? 12, bold: true, color: scheme, align: "center", valign: "middle" });
}
function arrow(slide, x, y, w, h, scheme, o = {}) {
  slide.addShape(S.LINE, { x, y, w, h, flipV: !!o.flipV, line: { color: scheme, width: o.width ?? 2,
    endArrowType: o.noHead ? undefined : "triangle", dashType: o.dash ? "dash" : "solid" }, objectName: o.name });
}
function chip(slide, x, y, text, scheme, w, size = 13) {
  const width = w ?? Math.max(0.8, 0.1 * text.length + 0.3);
  slide.addShape(S.ROUNDED_RECTANGLE, { x, y, w: width, h: 0.36, rectRadius: 0.18, fill: { color: scheme, transparency: 82 },
    line: { color: scheme, width: 0.75 } });
  txt(slide, text, { x, y, w: width, h: 0.36, fontSize: size, color: scheme, align: "center", valign: "middle", fontFace: "Consolas" });
  return width;
}
const CLASS_SCHEME = { PUBLIC: K.muted, INTERNAL: K.sky, CONFIDENTIAL: K.amber, PERSONAL: K.rose };
const FIELD_CLASS = { region: "INTERNAL", email: "PERSONAL", synthetic_personal_id: "PERSONAL", total_spend_cents: "CONFIDENTIAL",
  amount_cents: "CONFIDENTIAL", value_cents: "INTERNAL", transaction_count: "INTERNAL", month: "INTERNAL" };

// ================================================================== Slide 1 — Hook
pres.addSection({ title: "Hook" });
let s = pres.addSlide({ masterName: "SG_HERO", sectionTitle: "Hook" });
s.addText("Your AI agent needs an answer. Not your entire database.", { placeholder: "title" });
txt(s, [{ text: "ScopeGuard", options: { bold: true, color: K.teal, breakLine: true } },
  { text: "The intelligent data firewall for MCP-powered agents" }],
  { x: 0.6, y: 4.0, w: 7.0, h: 0.85, fontSize: 20, color: K.white });
txt(s, `Measured on a synthetic ${n(E.fixture.customers)}-customer CRM with real MCP tool calls.`,
  { x: 0.6, y: 5.0, w: 6.4, h: 0.4, fontSize: 14, color: K.muted });
// graphic: agent → blocked broad export vs. delivered minimal result
iconChip(s, "bot", "white", K.sky, 7.95, 3.18, 1.1);
txt(s, "AI agent", { x: 7.75, y: 4.36, w: 1.5, h: 0.35, fontSize: 14, align: "center", color: K.muted });
arrow(s, 9.15, 2.3, 0.95, 1.05, K.rose, { flipV: true, dash: true, name: "risky path" });
arrow(s, 9.15, 4.0, 0.95, 1.05, K.teal, { name: "safe path" });
card(s, 10.15, 1.3, 2.6, 1.85, { line: HEX.rose, fill: K.panel, shadow: true, name: "blocked card" });
iconChip(s, "ban", "rose", K.rose, 10.35, 1.48, 0.6);
txt(s, n(risky.customer_rows_requested_estimate), { x: 11.05, y: 1.45, w: 1.6, h: 0.65, fontSize: 32, bold: true, color: K.rose });
txt(s, "customer records requested by a broad plan", { x: 10.35, y: 2.2, w: 2.3, h: 0.55, fontSize: 13, color: K.white });
pill(s, 10.35, 2.72, 2.2, "BLOCKED · NEVER EXECUTED", K.rose, { size: 11, h: 0.3 });
card(s, 10.15, 4.2, 2.6, 1.85, { line: HEX.teal, fill: K.panel, shadow: true, name: "safe card" });
iconChip(s, "check", "teal", K.teal, 10.35, 4.38, 0.6);
txt(s, String(M.aggregate_rows_returned_to_model), { x: 11.05, y: 4.35, w: 1.6, h: 0.65, fontSize: 32, bold: true, color: K.teal });
txt(s, "regional totals delivered to the model", { x: 10.35, y: 5.1, w: 2.3, h: 0.55, fontSize: 13, color: K.white });
pill(s, 10.35, 5.62, 2.2, `${M.personal_field_values_returned_to_model} PERSONAL VALUES`, K.teal, { size: 11, h: 0.3 });
s.addNotes(
  "[0:00–0:15] One sentence: ScopeGuard lets AI agents finish the job without reading data they don't need.\n" +
  `On screen: the broad plan asked for ${n(risky.customer_rows_requested_estimate)} customer records and was blocked before it ran; ` +
  `the model received ${M.aggregate_rows_returned_to_model} regional totals and ${M.personal_field_values_returned_to_model} personal values.\n` +
  `Evidence: docs/demo_results.json (${E.label}, generated ${E.generated_at}). The 5,000 is a registry estimate for an unexecuted plan, not a leak that happened.`,
);

// ================================================================== Slide 2 — Problem
pres.addSection({ title: "Problem and solution" });
s = pres.addSlide({ masterName: "SG_CONTENT", sectionTitle: "Problem and solution" });
s.addText("One simple question. One very broad tool.", { placeholder: "title" });
card(s, 0.6, 1.55, 4.1, 4.55, { name: "question card" });
iconChip(s, "user", "white", K.sky, 0.85, 1.8, 0.62);
txt(s, "The user asks", { x: 1.6, y: 1.9, w: 2.9, h: 0.4, fontSize: 16, color: K.muted });
card(s, 0.85, 2.6, 3.6, 1.15, { fill: K.navy, line: HEX.sky, r: 0.2 });
txt(s, "“Summarize September sales by region.”", { x: 1.0, y: 2.7, w: 3.3, h: 0.95, fontSize: 20, bold: true, valign: "middle" });
txt(s, "What the task needs", { x: 0.85, y: 4.1, w: 3.6, h: 0.35, fontSize: 16, color: K.muted });
txt(s, `${M.aggregate_rows_returned_to_model} regional totals`, { x: 0.85, y: 4.5, w: 3.6, h: 0.75, fontSize: 36, bold: true, color: K.teal });
txt(s, "North · South · East · West", { x: 0.85, y: 5.3, w: 3.6, h: 0.4, fontSize: 16, color: K.muted });
arrow(s, 4.8, 3.8, 0.45, 0, K.muted, { width: 2.5 });
card(s, 5.35, 1.55, 7.38, 4.55, { name: "broad call card", line: HEX.rose });
iconChip(s, "database", "rose", K.rose, 5.6, 1.8, 0.62);
txt(s, "What a broad CRM tool call requests", { x: 6.35, y: 1.9, w: 6.0, h: 0.4, fontSize: 16, color: K.muted });
txt(s, [
  { text: "crm.get_customers(", options: { breakLine: true } },
  { text: "   fields=[region, email, synthetic_personal_id,", options: { breakLine: true } },
  { text: "           total_spend_cents],", options: { breakLine: true } },
  { text: "   month=\"2026-09\", limit=5000)" },
], { x: 5.6, y: 2.55, w: 6.9, h: 1.35, fontSize: 16, fontFace: "Consolas", color: K.sky });
let cx = 5.6;
for (const f of risky.requested_field_names) cx += chip(s, cx, 4.0, f, CLASS_SCHEME[FIELD_CLASS[f]]) + 0.12;
txt(s, n(risky.customer_rows_requested_estimate), { x: 5.6, y: 4.6, w: 2.2, h: 0.75, fontSize: 40, bold: true, color: K.rose });
txt(s, "customer rows requested", { x: 5.6, y: 5.35, w: 2.4, h: 0.5, fontSize: 14, color: K.white });
txt(s, n(risky.personal_values_requested_estimate), { x: 8.4, y: 4.6, w: 2.4, h: 0.75, fontSize: 40, bold: true, color: K.rose });
txt(s, "personal values requested", { x: 8.4, y: 5.35, w: 2.6, h: 0.5, fontSize: 14, color: K.white });
pill(s, 10.6, 4.82, 1.9, "max class: PERSONAL", K.rose, { size: 12 });
card(s, 0.6, 6.25, 12.13, 0.6, { fill: K.rose, transparency: 88, line: HEX.rose, r: 0.08 });
txt(s, "The task needs regional totals; the tool exposes thousands of customer records.",
  { x: 0.85, y: 6.25, w: 11.7, h: 0.6, fontSize: 18, bold: true, valign: "middle" });
s.addNotes(
  "[0:15–0:40] A normal request, an abnormal amount of data. Chips are colored by the trusted registry classification: " +
  "rose = PERSONAL, amber = CONFIDENTIAL, blue = INTERNAL.\n" +
  `${n(E.fixture.customers)} synthetic customers is the demo fixture size, not a market statistic. ` +
  `${n(risky.customer_rows_requested_estimate)} rows / ${n(risky.personal_values_requested_estimate)} personal values are ESTIMATES the evaluator computes from the registry for this candidate; it was never executed.`,
);

// ================================================================== Slide 3 — Differentiator
s = pres.addSlide({ masterName: "SG_CONTENT", sectionTitle: "Problem and solution" });
s.addText("Block, replan, complete", { placeholder: "title" });
function flow(slide, x, y, steps, gap = 0.4, size = 15) {
  let px = x;
  steps.forEach((st, i) => {
    const w = st.w ?? 1.3;
    slide.addShape(S.ROUNDED_RECTANGLE, { x: px, y, w, h: 0.62, rectRadius: 0.12, fill: { color: st.c, transparency: 82 },
      line: { color: st.c, width: 1 } });
    txt(slide, st.t, { x: px, y, w, h: 0.62, fontSize: size, bold: true, color: st.c, align: "center", valign: "middle" });
    px += w;
    if (i < steps.length - 1) {
      arrow(slide, px + 0.05, y + 0.31, gap - 0.12, 0, K.muted, { width: 1.5 });
      px += gap;
    }
  });
}
card(s, 0.6, 1.5, 5.85, 2.45, { name: "traditional card" });
iconChip(s, "x", "rose", K.rose, 0.85, 1.72, 0.55);
txt(s, "Traditional gateway", { x: 1.55, y: 1.68, w: 4.6, h: 0.35, fontSize: 16, color: K.muted });
txt(s, "Block and stop", { x: 1.55, y: 2.0, w: 4.6, h: 0.5, fontSize: 24, bold: true, color: K.rose });
flow(s, 0.85, 2.95, [{ t: "Broad request", c: K.sky, w: 1.55 }, { t: "Blocked", c: K.rose, w: 1.3 }, { t: "Task fails", c: K.rose, w: 1.45 }]);
card(s, 6.88, 1.5, 5.85, 2.45, { name: "scopeguard card", line: HEX.teal });
iconChip(s, "shield", "teal", K.teal, 7.13, 1.72, 0.55);
txt(s, "ScopeGuard", { x: 7.83, y: 1.68, w: 4.6, h: 0.35, fontSize: 16, color: K.muted });
txt(s, "Block, replan, complete", { x: 7.83, y: 2.0, w: 4.7, h: 0.5, fontSize: 24, bold: true, color: K.teal });
flow(s, 7.13, 2.95, [{ t: "Broad request", c: K.sky, w: 1.3 }, { t: "Blocked", c: K.rose, w: 0.95 }, { t: "Replanned", c: K.amber, w: 1.1 },
  { t: "Answered", c: K.teal, w: 1.05 }], 0.32, 14);
const layers = [
  { n: "1", h: "Hard policy", b: "Admin-owned rules outside the LLM. Secrets are never disclosed.", i: "scroll", c: K.sky, col: "sky" },
  { n: "2", h: "AI candidate planning", b: "The LLM proposes plans from an approved catalog. It never authorizes.", i: "brain", c: K.violet, col: "white" },
  { n: "3", h: "Runtime enforcement", b: "Every MCP call and every result is checked before the model sees it.", i: "filter", c: K.teal, col: "teal" },
];
layers.forEach((L, i) => {
  const x = 0.6 + i * 4.18;
  card(s, x, 4.25, 3.77, 1.85, { name: `layer ${L.n}` });
  iconChip(s, L.i, L.col, L.c, x + 0.22, 4.45, 0.58);
  txt(s, `${L.n}. ${L.h}`, { x: x + 0.95, y: 4.5, w: 2.7, h: 0.45, fontSize: 18, bold: true });
  txt(s, L.b, { x: x + 0.22, y: 5.15, w: 3.35, h: 0.85, fontSize: 15, color: K.white });
  if (i < 2) arrow(s, x + 3.8, 5.17, 0.36, 0, K.muted, { width: 1.5 });
});
txt(s, "Security that helps the agent finish its job safely.", { x: 0.6, y: 6.3, w: 12.13, h: 0.5, fontSize: 20, italic: true,
  color: K.teal, align: "center" });
s.addNotes(
  "[0:40–1:05] Simplified design contrast, not a benchmark of any specific product. Many gateways stop at a deny. ScopeGuard denies the broad " +
  "plan, then completes the task on an authorized lower-exposure route.\nThree independent layers: (1) deterministic policy and a trusted " +
  "registry; (2) an LLM that only proposes candidate plans (its self-reported risk is ignored); (3) the gateway re-checks every MCP tools/call " +
  "and inspects both result channels before anything reaches the model.",
);

// ================================================================== Slide 4 — Architecture
s = pres.addSlide({ masterName: "SG_CONTENT", sectionTitle: "Problem and solution" });
s.addText("How it works: agents only ever talk to ScopeGuard", { placeholder: "title" });
function node(slide, x, y, w, h, title, sub, ic, icCol, scheme, name) {
  card(slide, x, y, w, h, { line: scheme === K.teal ? HEX.teal : HEX.line, name, shadow: true });
  iconChip(slide, ic, icCol, scheme, x + (w - 0.55) / 2, y + 0.18, 0.55);
  txt(slide, title, { x: x + 0.08, y: y + 0.8, w: w - 0.16, h: 0.4, fontSize: 16, bold: true, align: "center" });
  txt(slide, sub, { x: x + 0.1, y: y + 1.2, w: w - 0.2, h: h - 1.3, fontSize: 13, color: K.muted, align: "center" });
}
node(s, 0.6, 2.05, 1.65, 2.15, "User", "dashboard · demo persona", "user", "white", K.sky, "user");
node(s, 2.65, 2.05, 2.5, 2.15, "Control plane", "policy engine · AI planner · evaluator", "brain", "white", K.violet, "control plane");
node(s, 5.55, 2.05, 1.75, 2.15, "Agent worker", "MCP client · no creds · one fixed URL", "network", "sky", K.sky, "agent worker");
node(s, 7.7, 2.05, 2.35, 2.15, "ScopeGuard gateway", "MCP server · grant · policy · output filter", "shield", "teal", K.teal, "gateway");
node(s, 10.75, 1.45, 1.98, 1.55, "Private Analytics", "", "chart", "white", K.sky, "analytics");
node(s, 10.75, 3.25, 1.98, 1.55, "Private CRM", "", "database", "white", K.sky, "crm");
arrow(s, 2.27, 3.12, 0.36, 0, K.muted);
arrow(s, 5.17, 3.12, 0.36, 0, K.muted);
arrow(s, 7.32, 3.12, 0.36, 0, K.sky);
arrow(s, 10.07, 2.7, 0.66, 0.45, K.teal, { flipV: true });
arrow(s, 10.07, 3.45, 0.66, 0.5, K.teal);
pill(s, 7.7, 4.35, 2.35, "ALLOW → aggregate only", K.teal, { size: 12 });
pill(s, 7.7, 4.8, 2.35, "DENY → no upstream call", K.rose, { size: 12 });
// backend-only secret path
card(s, 10.75, 5.15, 1.98, 1.25, { line: HEX.amber, name: "vault" });
iconChip(s, "key", "amber", K.amber, 10.9, 5.33, 0.5);
txt(s, "Backend-only credential", { x: 11.45, y: 5.28, w: 1.2, h: 0.6, fontSize: 12, bold: true, color: K.amber });
txt(s, "used, never returned", { x: 10.9, y: 5.92, w: 1.75, h: 0.35, fontSize: 12, color: K.muted });
arrow(s, 11.74, 4.83, 0, 0.3, K.amber, { flipV: true, name: "key to CRM" });
// model sees sanitized result only
card(s, 2.65, 5.15, 4.65, 1.25, { line: HEX.teal, name: "model" });
iconChip(s, "sparkles", "teal", K.teal, 2.85, 5.38, 0.55);
txt(s, "LLM sees only the sanitized result", { x: 3.55, y: 5.3, w: 3.65, h: 0.4, fontSize: 16, bold: true });
txt(s, `e.g. ${M.aggregate_rows_returned_to_model} aggregate rows, or {"connected": true}`, { x: 3.55, y: 5.72, w: 3.65, h: 0.45, fontSize: 13, color: K.muted, fontFace: "Consolas" });
arrow(s, 3.9, 4.22, 0, 0.9, K.teal);
txt(s, "Worker → gateway: MCP Streamable HTTP  ·  gateway → private servers: MCP stdio  ·  registered tools only",
  { x: 0.6, y: 6.55, w: 12.13, h: 0.35, fontSize: 14, color: K.muted });
s.addNotes(
  "[1:05–1:35] The agent worker is a separate process with one fixed destination: the ScopeGuard MCP endpoint (Streamable HTTP). " +
  "It has no database path, no backend credential and no LLM key. The gateway re-checks every call against server-owned grant state, " +
  "then calls private CRM/Analytics MCP servers over stdio (no sockets). The CRM holds a synthetic canary credential and uses it to verify " +
  "its connection; the model gets only connected: true. Using a secret is not the same as exposing it.\n" +
  "Honest scope: application boundary, not an OS sandbox; demo personas are not production identity.",
);

// ================================================================== Slide 5 — Plans compared
pres.addSection({ title: "Proof" });
s = pres.addSlide({ masterName: "SG_CONTENT", sectionTitle: "Proof" });
s.addText("Three candidate plans, one safe choice", { placeholder: "title" });
const cols = [{ h: "Plan", x: 0.85, w: 0.6 }, { h: "Tool call", x: 1.5, w: 3.35 }, { h: "Data requested", x: 4.95, w: 3.9 },
  { h: "Rows (est.)", x: 9.0, w: 1.1 }, { h: "Personal", x: 10.05, w: 1.15 }, { h: "Decision", x: 11.2, w: 1.4 }];
cols.forEach((c) => txt(s, c.h, { x: c.x, y: 1.45, w: c.w, h: 0.35, fontSize: 14, color: K.muted, bold: true }));
const rows = [
  { c: risky, label: "A", d: "DENY", note: "not executed", scheme: K.rose, line: HEX.rose },
  { c: txn, label: "B", d: "MORE EXPOSURE", note: "denied for this task", scheme: K.amber, line: HEX.amber },
  { c: safe, label: "C", d: "SELECTED", note: "executed", scheme: K.teal, line: HEX.teal },
];
rows.forEach((r, i) => {
  const y = 1.9 + i * 1.12;
  card(s, 0.6, y, 12.13, 0.98, { line: r.line, fill: r.c.selected ? K.panel : K.panel, name: `plan ${r.label}` });
  txt(s, r.label, { x: 0.85, y, w: 0.6, h: 0.98, fontSize: 26, bold: true, color: r.scheme, valign: "middle" });
  txt(s, r.c.tool, { x: 1.5, y, w: 3.4, h: 0.98, fontSize: 15, fontFace: "Consolas", color: K.sky, valign: "middle" });
  let fx = 4.95;
  r.c.requested_field_names.slice(0, 4).forEach((f) => {
    const short = f === "synthetic_personal_id" ? "personal_id" : f === "total_spend_cents" ? "spend" : f === "transaction_count" ? "tx_count" : f;
    fx += chip(s, fx, y + 0.31, short, CLASS_SCHEME[FIELD_CLASS[f]], Math.max(0.7, 0.093 * short.length + 0.28), 12) + 0.06;
  });
  const rowsReq = r.c.customer_rows_requested_estimate + r.c.transaction_rows_requested_estimate;
  txt(s, rowsReq ? n(rowsReq) : `${M.aggregate_rows_returned_to_model} agg.`, { x: 9.0, y, w: 1.05, h: 0.98, fontSize: 20, bold: true, valign: "middle" });
  txt(s, n(r.c.personal_values_requested_estimate), { x: 10.05, y, w: 1.1, h: 0.98, fontSize: 20, bold: true, valign: "middle",
    color: r.c.personal_values_requested_estimate ? K.rose : K.teal });
  pill(s, 11.12, y + 0.16, 1.48, r.d, r.scheme, { size: 11 });
  txt(s, r.note, { x: 11.02, y: y + 0.56, w: 1.68, h: 0.3, fontSize: 12, color: K.muted, align: "center" });
});
card(s, 0.6, 5.35, 5.95, 1.45, { fill: K.amber, transparency: 90, line: HEX.amber, name: "estimate box" });
txt(s, "Candidate request (A, B)", { x: 0.85, y: 5.48, w: 5.5, h: 0.4, fontSize: 16, bold: true, color: K.amber });
txt(s, "Estimated from the trusted registry. Rejected before execution, so no upstream call was made.",
  { x: 0.85, y: 5.9, w: 5.5, h: 0.8, fontSize: 15 });
card(s, 6.78, 5.35, 5.95, 1.45, { fill: K.teal, transparency: 90, line: HEX.teal, name: "measured box" });
txt(s, "Executed response (C), measured", { x: 7.03, y: 5.48, w: 5.5, h: 0.4, fontSize: 16, bold: true, color: K.teal });
txt(s, `${M.aggregate_rows_returned_to_model} aggregate rows · ${M.tool_result_bytes_model_bound} bytes · ${M.personal_field_values_returned_to_model} personal values · totals = independent SQL`,
  { x: 7.03, y: 5.9, w: 5.5, h: 0.8, fontSize: 15 });
const liveCands = liveOk ? LIVE.scenarios.A_safe_replan_sales_by_region.candidates.length : 0;
s.addNotes(
  "[1:35–2:00] Ranking is deterministic and lexicographic: authorized and task-sufficient first, then lowest max classification, " +
  "fewest personal values, fewest rows, fewest bytes. LLM self-reported risk is displayed but ignored.\n" +
  `Rows column for A/B = estimates; for C = measured aggregate rows. Evidence: ${E.label}.` +
  (liveOk ? ` In the live run, ${liveModel} proposed ${liveCands} candidates covering the same three strategies, and the same aggregate plan was selected.` : ""),
);

// ================================================================== Slide 6 — Live demo
s = pres.addSlide({ masterName: "SG_CONTENT", sectionTitle: "Proof" });
s.addText("Live demo: watch the scope shrink", { placeholder: "title" });
card(s, 0.6, 1.45, 8.1, 5.22, { fill: K.panel, line: HEX.line, name: "screenshot frame", shadow: true });
const SX = 0.7, SY = 1.55, SW = 7.9, SH = 7.9 / 1.6;
s.addImage({ path: A("demo-sales.png"), x: SX, y: SY, w: SW, h: SH, altText: "ScopeGuard dashboard after the sales-by-region run" });
const callouts = [[0.232, 0.165], [0.235, 0.295], [0.612, 0.165]];
callouts.forEach(([fx, fy], i) => {
  const cxp = SX + SW * fx, cyp = SY + SH * fy;
  s.addShape(S.OVAL, { x: cxp - 0.18, y: cyp - 0.18, w: 0.36, h: 0.36, fill: { color: K.amber }, line: { color: K.navy, width: 2 } });
  txt(s, String(i + 1), { x: cxp - 0.18, y: cyp - 0.18, w: 0.36, h: 0.36, fontSize: 14, bold: true, color: K.navy, align: "center", valign: "middle" });
});
const beats = [
  ["Unsafe request blocked", `Broad CRM export (${n(risky.customer_rows_requested_estimate)} rows requested) denied and never executed`],
  ["Safe alternative executes", `Aggregate tool runs over real MCP; ${M.aggregate_rows_returned_to_model} aggregate rows returned`],
  ["The trace proves it", `${M.customer_rows_returned_to_model} customer records and ${M.personal_field_values_returned_to_model} personal values reached the model`],
];
beats.forEach(([h, b], i) => {
  const y = 1.55 + i * 1.5;
  s.addShape(S.OVAL, { x: 8.98, y, w: 0.5, h: 0.5, fill: { color: K.amber }, line: { color: K.amber, width: 1 } });
  txt(s, String(i + 1), { x: 8.98, y, w: 0.5, h: 0.5, fontSize: 18, bold: true, color: K.navy, align: "center", valign: "middle" });
  txt(s, h, { x: 9.65, y: y - 0.02, w: 3.1, h: 0.45, fontSize: 18, bold: true });
  txt(s, b, { x: 9.65, y: y + 0.45, w: 3.1, h: 0.9, fontSize: 14, color: K.muted });
});
txt(s, `Screenshot of the running app, ${shotLabel}. Offline deterministic mode runs the same enforcement.`,
  { x: 8.98, y: 6.05, w: 3.75, h: 0.6, fontSize: 12, color: K.muted, italic: true });
s.addNotes(
  "[2:00–2:55] LIVE DEMO (about 55 s). Before the talk: run_local --mode live (or deterministic), open http://127.0.0.1:8000.\n" +
  "1) Click 'A · Safe replan'. Point at the candidate cards: the broad CRM export is DENIED · NOT EXECUTED; aggregate is SELECTED.\n" +
  "2) Point at the tiles: 5,000 requested (estimate, never executed) → 0 customer records → 0 personal values → Answered.\n" +
  "3) Click 'B1 · Secret request': hard deny before any planner or model call. Click 'B2': connected: true only.\n" +
  "4) Optional: click 'Broad CRM export' under probes: denied at the gateway, 0 prohibited upstream dispatches.\n" +
  "FALLBACK: if the network or LLM fails, the UI labels the deterministic fallback; if the laptop fails, show docs/screenshots/*.png and say they are screenshots.",
);

// ================================================================== Slide 7 — Evidence
s = pres.addSlide({ masterName: "SG_CONTENT", sectionTitle: "Proof" });
s.addText("The answer was delivered. The extra data was not.", { placeholder: "title" });
card(s, 0.6, 1.45, 6.6, 4.85, { name: "chart card" });
s.addChart(pres.charts.BAR, [
  { name: "Requested by rejected plan (estimate)", labels: ["Customer records", "Personal values"],
    values: [risky.customer_rows_requested_estimate, risky.personal_values_requested_estimate] },
  { name: "Delivered to the model (measured)", labels: ["Customer records", "Personal values"],
    values: [M.customer_rows_returned_to_model, M.personal_field_values_returned_to_model] },
], {
  x: 0.8, y: 1.6, w: 6.2, h: 4.55, barDir: "bar", barGrouping: "clustered", barGapWidthPct: 60,
  chartColors: [HEX.rose, HEX.teal], showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: "[>=1000]#\\,##0;0",
  dataLabelColor: HEX.white, dataLabelFontSize: 16, dataLabelFontBold: true, dataLabelFontFace: "+mn-lt",
  catAxisLabelColor: HEX.white, catAxisLabelFontSize: 16, catAxisLabelFontFace: "+mn-lt", catAxisLineShow: false,
  valAxisHidden: true, valGridLine: { style: "none" }, valAxisMaxVal: 12500, catGridLine: { style: "none" },
  showLegend: true, legendPos: "b", legendColor: HEX.white, legendFontSize: 14, legendFontFace: "+mn-lt",
  showTitle: true, title: "Sales-by-region task", titleColor: HEX.muted, titleFontSize: 14, titleFontFace: "+mn-lt",
  plotArea: { fill: { color: HEX.panel } }, chartArea: { fill: { color: HEX.panel } }, objectName: "evidence chart",
});
const stats = [
  { v: String(M.aggregate_rows_returned_to_model), l: "aggregate rows delivered; totals match independent SQL", c: K.teal },
  { v: "Done", l: "task completed with a verified MCP round-trip", c: K.teal },
  { v: String(E.model_boundary_scan.canary_occurrences), l: `canary hits in ${E.model_boundary_scan.payloads_recorded} model-bound payloads scanned`, c: K.teal },
  { v: `${probesDenied}/${probeCalls}`, l: "tampered agent calls denied; 0 prohibited upstream dispatches", c: K.amber },
];
stats.forEach((st, i) => {
  const x = 7.45 + (i % 2) * 2.7, y = 1.45 + Math.floor(i / 2) * 2.0;
  card(s, x, y, 2.55, 1.85, { name: `stat ${i + 1}` });
  txt(s, st.v, { x: x + 0.2, y: y + 0.15, w: 2.2, h: 0.75, fontSize: 36, bold: true, color: st.c });
  txt(s, st.l, { x: x + 0.2, y: y + 0.9, w: 2.2, h: 0.85, fontSize: 13, color: K.white });
});
const testLine = [PY ? `${PY.passed}/${PY.tests} Python tests` : null, E2E ? `${E2E.passed}/${E2E.tests} browser E2E` : null]
  .filter(Boolean).join(" · ") + " passed";
card(s, 7.45, 5.45, 5.25, 0.85, { name: "tests" });
iconChip(s, "check", "teal", K.teal, 7.62, 5.6, 0.55);
txt(s, testLine || "Test results not recorded", { x: 8.35, y: 5.45, w: 4.25, h: 0.85, fontSize: 15, bold: true, valign: "middle" });
txt(s, "Measured in a synthetic, task-scoped local demo; not a universal safety guarantee.",
  { x: 0.6, y: 6.45, w: 12.13, h: 0.4, fontSize: 13, italic: true, color: K.muted });
s.addNotes(
  "[2:55–3:20] Rose = what the rejected plan REQUESTED (registry estimate, never executed). Teal = what was DELIVERED to the model " +
  "(measured at the model boundary). Both teal values are 0, so their bars have zero length.\n" +
  `Source: docs/demo_results.json, ${E.label}, generated ${E.generated_at}; fixture sha256 ${E.fixture.fixture_sha256.slice(0, 12)}…, ` +
  `config digest ${E.config_digest_prefix}. Normal run: candidates rejected = ${M.candidates_rejected}, gateway calls denied = ${M.gateway_calls_denied} ` +
  "(rejections happen before execution). The 4/4 denials come from separate scripted compromised-agent probes.\n" +
  (testLine ? `Tests referenced in the evidence file: ${testLine}.` : ""),
);

// ================================================================== Slide 8 — Close
pres.addSection({ title: "Close" });
s = pres.addSlide({ masterName: "SG_CLOSE", sectionTitle: "Close" });
s.addText("Don't give agents more data. Give them a safer route.", { placeholder: "title" });
txt(s, "Who it is for", { x: 0.6, y: 0.5, w: 6, h: 0.45, fontSize: 20, bold: true, color: K.muted });
const users = [["building", "Enterprise AI builders", "ship MCP agents without broad data grants"], ["bank", "Banks and fintech", "keep secrets and PII out of model context"],
  ["headset", "Customer support", "one field, one customer, approved once"], ["chart", "Analytics teams", "aggregate answers, not raw exports"]];
users.forEach(([ic, h, b], i) => {
  const x = 0.6 + i * 3.08;
  card(s, x, 1.05, 2.9, 1.9, { name: `user ${i + 1}` });
  iconChip(s, ic, "teal", K.teal, x + 0.22, 1.25, 0.58);
  txt(s, h, { x: x + 0.22, y: 1.92, w: 2.55, h: 0.42, fontSize: 17, bold: true });
  txt(s, b, { x: x + 0.22, y: 2.32, w: 2.55, h: 0.55, fontSize: 13, color: K.muted });
});
txt(s, "Roadmap (not built yet)", { x: 0.6, y: 3.25, w: 6, h: 0.45, fontSize: 20, bold: true, color: K.muted });
const road = ["More MCP connectors", "Verified approvals", "Production identity (OIDC/SSO)", "Policy as code"];
road.forEach((r, i) => {
  const x = 0.6 + i * 3.08;
  card(s, x, 3.8, 2.75, 0.85, { fill: K.violet, transparency: 88, line: HEX.line, name: `roadmap ${i + 1}` });
  txt(s, r, { x: x + 0.15, y: 3.8, w: 2.45, h: 0.85, fontSize: 16, bold: true, valign: "middle", align: "center" });
  if (i < 3) arrow(s, x + 2.78, 4.22, 0.27, 0, K.muted, { width: 1.5 });
});
txt(s, [
  { text: "Website  ", options: { color: K.muted } },
  { text: "scopeguard-ai-shield.lovable.app", options: { color: K.sky, hyperlink: { url: "https://scopeguard-ai-shield.lovable.app/" } } },
  { text: "     Code  ", options: { color: K.muted } },
  { text: "github.com/Ani-Bliadze/scopeguard", options: { color: K.sky, hyperlink: { url: "https://github.com/Ani-Bliadze/scopeguard" } } },
], { x: 0.6, y: 4.92, w: 12.13, h: 0.45, fontSize: 18, objectName: "links" });
s.addNotes(
  "[3:20–3:40] Intended users, not customers: we claim no users, savings or partners. Roadmap items are not implemented.\n" +
  "Close with the line on the slide, then invite questions. Point at the links: the public website (https://scopeguard-ai-shield.lovable.app/) and the code (https://github.com/Ani-Bliadze/scopeguard).",
);

// ------------------------------------------------------------------ write + theme
(async () => {
  await pres.writeFile({ fileName: OUT });
  await applyTheme(OUT, THEME);
  console.log(`wrote ${path.relative(ROOT, OUT)} (8 slides) from ${E.label} evidence${liveOk ? ` + live run (${liveModel})` : ""}`);
})().catch((e) => fail(e.message));
