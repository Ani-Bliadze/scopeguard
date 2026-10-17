export type Persona = "sales_analyst" | "customer_support";

export interface SessionInfo {
  persona: Persona;
  principal: string;
  session_id: string;
  csrf_token: string;
  access_paused: boolean;
  features: { approvals: boolean; probes: string[] };
  mode: string;
  label: string;
}

export interface Health {
  status: string;
  config_valid: boolean;
  fixture: { customers: number; sales: number } | null;
  upstreams: Record<string, boolean>;
  planner_mode: string;
  answer_mode: string;
  live_model: string | null;
  approvals_enabled: boolean;
  config_digest: string | null;
}

export interface Exposure {
  max_classification: string;
  requested_fields: string[];
  requested_classes: string[];
  customer_rows_requested: number;
  transaction_rows_requested: number;
  aggregate_rows_expected: number;
  personal_field_values_requested: number;
  estimated_bytes: number;
  tool_calls: number;
}

export interface Candidate {
  candidate_id: string;
  origin: string;
  tools: string[];
  valid: boolean;
  covers_task: boolean;
  decision: "ALLOW" | "DENY" | "APPROVAL_REQUIRED" | "TRANSFORM";
  reason_codes: string[];
  exposure: Exposure | null;
  selected: boolean;
  rank: number | null;
  rationale: string;
  self_reported_risk: string | null;
}

export interface Approval {
  approval_id: string;
  task_id: string;
  tool_id: string;
  resource: Record<string, unknown>;
  fields: string[];
  purpose: string;
  single_use: boolean;
  created_at: number;
  expires_at: number;
  status: string;
}

export interface Boundary {
  phase: string;
  provider: string;
  external_request: boolean;
  dispatched: boolean;
  total_bytes: number;
  tool_result_bytes: number;
  customer_rows: number;
  aggregate_rows: number;
  personal_field_values: number;
  canary_hits: number;
  blocked_reason: string | null;
}

export interface SalesRow {
  region: string;
  value_cents: number;
  transaction_count: number;
}

export interface Task {
  task_id: string;
  kind: "task" | "probe";
  probe: string | null;
  status: string;
  intent: string | null;
  canonical_request: string | null;
  persona: Persona;
  duration_ms: number;
  block: { code: string; message: string } | null;
  planner: { mode?: string; model?: string | null; fallback_reason?: string | null; attempted?: string };
  answer: {
    mode?: string;
    model?: string | null;
    verified?: boolean | null;
    fallback_reason?: string | null;
    attempted?: string;
    live_answer_discarded?: boolean;
  };
  candidates: Candidate[];
  selected_candidate_id: string | null;
  approval: Approval | null;
  execution: {
    transport?: string;
    protocol_version?: string | null;
    listed_tools?: string[];
    steps?: { tool_id: string; ok: boolean; error_code: string | null }[];
    worker_error?: string | null;
    verified_mcp_round_trip?: boolean;
    attempted_calls?: string[];
  };
  result: { kind: string; data: Record<string, unknown>; answer_text: string } | null;
  metrics: Record<string, number | boolean | string[]>;
  boundary: Boundary[];
  terminal: boolean;
}

export interface AuditEvent {
  seq: number;
  ts: number;
  task_id: string;
  run_id: string | null;
  principal: string;
  stage: string;
  tool_id: string | null;
  decision: string | null;
  reason_code: string | null;
  fields: string[];
  classes: string[];
  counts: Record<string, number>;
  message: string;
  model_mode: string | null;
  candidate_id: string | null;
}

export interface PolicySummary {
  policy_version: string;
  registry_version: string;
  default_decision: string;
  hard_rules: string;
  roles: Record<string, { description: string; tasks: string[] }>;
  tasks: Record<string, { purpose: string; model_visible_classes: string[]; tools: Record<string, string> }>;
  tools: {
    tool_id: string;
    server: string;
    description: string;
    row_kind: string;
    max_rows: number;
    approval_mode: string;
    fields: Record<string, string>;
    backend_secrets_used: Record<string, string>;
  }[];
  unsupported_surfaces: string[];
}
