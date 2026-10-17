"""Loads and validates the administrator-owned registry, policy and task configuration.

Any missing, malformed or drifted configuration raises ConfigError, which fails readiness closed.
Tool descriptions here are admin-approved text; upstream MCP descriptions are never consulted."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, ValidationError

from backend.contracts import Classification, Decision, Intent, Role, Strict
from backend.settings import CONFIG_DIR
from backend.tool_schemas import SCHEMAS, schema_fingerprint


class ConfigError(Exception):
    pass


class FieldSpec(Strict):
    class_: Classification = Field(alias="class")
    avg_value_bytes: int = Field(ge=0)

    model_config = Strict.model_config | {"populate_by_name": True, "strict": False}


class ToolEntry(Strict):
    tool_id: str
    owner: str
    server_id: Literal["crm", "analytics"]
    upstream_name: str
    schema_version: Literal["1.0"]
    description: str
    row_kind: Literal["customer", "transaction", "aggregate", "status"]
    output_shape: Literal["rows", "aggregate", "status", "single"]
    max_rows: int
    max_bytes: int
    approval_mode: Literal["none", "single_use_scoped"]
    selectable_fields: bool
    fields: dict[str, FieldSpec]
    backend_secrets_used: dict[str, Classification] = Field(default_factory=dict)
    schema_sha256: str

    model_config = Strict.model_config | {"strict": False}


class Registry(Strict):
    registry_version: str
    schema_version: Literal["1.0"]
    tools: list[ToolEntry]

    model_config = Strict.model_config | {"strict": False}


class TaskToolRule(Strict):
    decision: Decision
    constraints: dict[str, Any] = Field(default_factory=dict)
    roles: list[Role] | None = None
    approval_ttl_seconds: int | None = None
    single_use: bool = False

    model_config = Strict.model_config | {"strict": False}


class TaskPolicy(Strict):
    purpose: str
    model_visible_classes: list[Classification]
    max_tool_calls: int
    tools: dict[str, TaskToolRule]
    terminal_decision: str | None = None

    model_config = Strict.model_config | {"strict": False}


class RolePolicy(Strict):
    description: str
    tasks: list[Intent]

    model_config = Strict.model_config | {"strict": False}


class HardRules(Strict):
    non_disclosable_classes: list[Classification]
    approval_can_never_override: list[Classification]
    description: str

    model_config = Strict.model_config | {"strict": False}


class Policy(Strict):
    policy_version: str
    default_decision: Literal["DENY"]
    hard_rules: HardRules
    roles: dict[Role, RolePolicy]
    tasks: dict[Intent, TaskPolicy]

    model_config = Strict.model_config | {"strict": False}


class IntentSpec(Strict):
    canonical_request: str
    aliases: list[str]
    coverage: dict[str, Any]
    planner: Literal["candidates", "none"]

    model_config = Strict.model_config | {"strict": False}


class TaskCatalog(Strict):
    tasks_version: str
    max_input_chars: int
    secret_request_patterns: list[str]
    intents: dict[Intent, IntentSpec]

    model_config = Strict.model_config | {"strict": False}


def _canonical_digest(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class TrustedConfig:
    registry: Registry
    policy: Policy
    tasks: TaskCatalog
    registry_digest: str
    policy_digest: str
    tasks_digest: str

    def tool(self, tool_id: str) -> ToolEntry | None:
        for t in self.registry.tools:
            if t.tool_id == tool_id:
                return t
        return None

    @property
    def tool_ids(self) -> list[str]:
        return [t.tool_id for t in self.registry.tools]

    @property
    def combined_digest(self) -> str:
        return hashlib.sha256(
            (self.registry_digest + self.policy_digest + self.tasks_digest).encode()
        ).hexdigest()


def load_config(config_dir: Path = CONFIG_DIR) -> TrustedConfig:
    try:
        raw_reg = json.loads((config_dir / "tool_registry.json").read_text(encoding="utf-8"))
        raw_pol = json.loads((config_dir / "policy.json").read_text(encoding="utf-8"))
        raw_tasks = json.loads((config_dir / "tasks.json").read_text(encoding="utf-8"))
        registry = Registry.model_validate(raw_reg)
        policy = Policy.model_validate(raw_pol)
        tasks = TaskCatalog.model_validate(raw_tasks)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        # Never serialize validation details (they can echo values).
        raise ConfigError(f"CONFIG_INVALID:{type(exc).__name__}") from None

    seen: set[str] = set()
    for tool in registry.tools:
        if tool.tool_id in seen:
            raise ConfigError("CONFIG_DUPLICATE_TOOL")
        seen.add(tool.tool_id)
        if tool.tool_id not in SCHEMAS:
            raise ConfigError("CONFIG_TOOL_WITHOUT_TRUSTED_SCHEMA")
        if tool.schema_sha256 != schema_fingerprint(tool.tool_id):
            raise ConfigError("CONFIG_SCHEMA_FINGERPRINT_MISMATCH")
        out_model = SCHEMAS[tool.tool_id][1]
        if tool.output_shape == "rows":
            row_model = out_model.model_fields["rows"].annotation.__args__[0]  # list[RowModel]
            if set(row_model.model_fields) != set(tool.fields):
                raise ConfigError("CONFIG_FIELD_CLASSIFICATION_INCOMPLETE")
        for spec in tool.fields.values():
            if spec.class_ == Classification.RESTRICTED_SECRET:
                raise ConfigError("CONFIG_SECRET_FIELD_IN_OUTPUT")
    for tp in policy.tasks.values():
        for tool_id in tp.tools:
            if tool_id not in seen:
                raise ConfigError("CONFIG_POLICY_REFERENCES_UNKNOWN_TOOL")
    if set(tasks.intents) != set(policy.tasks):
        raise ConfigError("CONFIG_TASKS_POLICY_MISMATCH")

    return TrustedConfig(
        registry=registry,
        policy=policy,
        tasks=tasks,
        registry_digest=_canonical_digest(raw_reg),
        policy_digest=_canonical_digest(raw_pol),
        tasks_digest=_canonical_digest(raw_tasks),
    )
