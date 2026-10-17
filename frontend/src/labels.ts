export const REASONS: Record<string, string> = {
  TOOL_NOT_ALLOWED_FOR_TASK: "Tool not approved for this task purpose",
  ALLOWED_BY_TASK_POLICY: "Allowed by task policy",
  ALLOWED_WITH_SCOPED_APPROVAL: "Allowed by one-time scoped approval",
  APPROVAL_REQUIRED: "Needs a scoped one-time approval",
  HARD_DENY_SECRET_DISCLOSURE: "Hard deny: secrets are never disclosed to the model",
  UNKNOWN_TOOL: "Unknown tool: not in the trusted registry",
  INVALID_ARGUMENTS: "Arguments rejected by trusted schema",
  ARGUMENT_OUT_OF_SCOPE: "Argument outside the task scope",
  FIELD_CLASS_NOT_PERMITTED: "Requests data classes not permitted for this task",
  TASK_NOT_PERMITTED_FOR_ROLE: "Persona may not run this task",
  STEP_NOT_IN_GRANT: "Call is not an unconsumed step of the approved plan",
  UNSUPPORTED_TASK: "Not a supported task",
  WRONG_MONTH: "Wrong month",
  WRONG_METRIC: "Wrong metric",
  LIMIT_TRUNCATES_DATA: "Row limit would truncate the answer",
  OMITS_REGIONS: "Omits regions",
  REDUCER_REQUIRED: "Needs a reducer to answer",
  MISSING_REGION_OR_AMOUNT: "Missing region or amount",
  DOES_NOT_ANSWER_TASK: "Does not answer the task",
  BLOCKED_NO_SAFE_PLAN: "No authorized, sufficient plan",
  OUTPUT_SCHEMA_VIOLATION: "Upstream output failed the trusted schema",
  SECRET_PATTERN_IN_OUTPUT: "Secret pattern found in upstream output",
  UPSTREAM_TIMEOUT: "Upstream timed out (no retry)",
  APPROVAL_DENIED: "Approval denied",
  APPROVAL_EXPIRED: "Approval expired",
  SESSION_ACCESS_PAUSED: "Data access paused for this session",
  PROBE_BLOCKED: "Tampered call denied at the gateway",
  LOWEST_EXPOSURE_AUTHORIZED_SUFFICIENT_PLAN: "Lowest-exposure authorized plan that answers the task",
  OUTPUT_ACCEPTED: "Output validated and rebuilt",
  SUPPORTED_TASK: "Supported task",
};

export const reason = (code?: string | null) => (code ? REASONS[code] ?? code.replaceAll("_", " ").toLowerCase() : "");

export const CLASS_STYLE: Record<string, string> = {
  PUBLIC: "bg-slate-600/30 text-slate-200 ring-slate-400/30",
  INTERNAL: "bg-sky-500/15 text-sky-200 ring-sky-400/30",
  CONFIDENTIAL: "bg-amber-400/15 text-amber-200 ring-amber-300/40",
  PERSONAL: "bg-rose-500/15 text-rose-200 ring-rose-400/40",
  RESTRICTED_SECRET: "bg-fuchsia-500/20 text-fuchsia-200 ring-fuchsia-400/40",
};

export const PROBE_LABELS: Record<string, string> = {
  broad_export: "Broad CRM export",
  secret_tool: "Call private secret tool",
  extra_fields: "Smuggle extra fields",
  replay: "Replay approved step",
};

export const INTENT_LABELS: Record<string, string> = {
  SALES_BY_REGION_2026_09: "September sales by region",
  CRM_CONNECTION_STATUS: "CRM connection check",
  SECRET_DISCLOSURE_ATTEMPT: "Secret disclosure attempt",
  NOTIFY_CUSTOMER_105: "Notify customer #105",
};

export const fmtUSD = (cents: number) =>
  (cents / 100).toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 });
export const fmtInt = (n: number) => n.toLocaleString("en-US");
