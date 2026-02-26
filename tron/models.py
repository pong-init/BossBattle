"""Pydantic models matching the Arcade Contextual Access webhook OpenAPI spec.

These models are the contract — the server validates requests against them
and returns responses that match what Arcade's engine expects.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Shared types ────────────────────────────────────────────────


class ToolInfo(BaseModel):
    name: str
    toolkit: str
    version: str


class OAuth2Details(BaseModel):
    scopes: list[str] = Field(default_factory=list)
    at: dict[str, Any] = Field(default_factory=dict)
    user_info: dict[str, Any] = Field(default_factory=dict)


class Authorization(BaseModel):
    provider_id: str = ""
    oauth2: Optional[OAuth2Details] = None


class HookContext(BaseModel):
    authorization: list[Authorization] = Field(default_factory=list)
    secrets: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    user_id: str = ""


class HookCode(str, Enum):
    OK = "OK"
    CHECK_FAILED = "CHECK_FAILED"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"


# ── Pre-execution hook ──────────────────────────────────────────


class PreHookRequest(BaseModel):
    execution_id: str
    tool: ToolInfo
    inputs: dict[str, Any] = Field(default_factory=dict)
    context: HookContext = Field(default_factory=HookContext)


class PreHookOverride(BaseModel):
    inputs: dict[str, Any] = Field(default_factory=dict)
    secrets: list[dict[str, Any]] = Field(default_factory=list)


class PreHookResult(BaseModel):
    code: HookCode = HookCode.OK
    error_message: str = ""
    override: Optional[PreHookOverride] = None


# ── Post-execution hook ─────────────────────────────────────────


class PostHookRequest(BaseModel):
    execution_id: str
    tool: ToolInfo
    inputs: dict[str, Any] = Field(default_factory=dict)
    success: bool = True
    output: Any = None
    execution_code: str = ""
    execution_error: str = ""
    context: HookContext = Field(default_factory=HookContext)


class PostHookOverride(BaseModel):
    output: Any = None


class PostHookResult(BaseModel):
    code: HookCode = HookCode.OK
    error_message: str = ""
    override: Optional[PostHookOverride] = None


# ── Access hook ─────────────────────────────────────────────────


class ToolRequirement(BaseModel):
    requirements: dict[str, Any] = Field(default_factory=dict)
    version: str = ""


class AccessToolkitSpec(BaseModel):
    tools: dict[str, list[ToolRequirement]] = Field(default_factory=dict)


class AccessHookRequest(BaseModel):
    user_id: str
    toolkits: dict[str, dict[str, dict[str, list[ToolRequirement]]]] = Field(
        default_factory=dict
    )


class AccessHookResult(BaseModel):
    only: Optional[dict[str, AccessToolkitSpec]] = None
    deny: Optional[dict[str, AccessToolkitSpec]] = None


# ── Health ──────────────────────────────────────────────────────


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class HealthResponse(BaseModel):
    status: HealthStatus = HealthStatus.HEALTHY
