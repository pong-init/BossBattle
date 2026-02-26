"""Tron — BossBattle Contextual Access Webhook Server

Implements Arcade's Contextual Access webhook API:
  POST /pre     — Pre-execution hook
  POST /post    — Post-execution hook
  POST /access  — Access control hook
  GET  /health  — Health check

All policy logic lives in policies.yaml — this server is pure plumbing.

Usage:
    uvicorn tron.server:app --port 4242 --reload
"""

from __future__ import annotations

import logging
import os

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from tron.engine import PolicyEngine
from tron.models import (
    AccessHookRequest,
    AccessHookResult,
    HealthResponse,
    HealthStatus,
    HookCode,
    PostHookRequest,
    PostHookResult,
    PreHookRequest,
    PreHookResult,
)

logging.basicConfig(level=logging.INFO, format="[TRON] %(message)s")
logger = logging.getLogger("tron")

app = FastAPI(
    title="Tron — BossBattle Policy Hooks",
    description="Config-driven Contextual Access webhook for Arcade",
    version="0.1.0",
)

engine = PolicyEngine()

# ── Auth ────────────────────────────────────────────────────────

security = HTTPBearer()


async def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    expected = os.environ.get("TRON_BEARER_TOKEN", "")
    if not expected:
        logger.warning("TRON_BEARER_TOKEN not set — accepting all requests")
        return credentials.credentials
    if credentials.credentials != expected:
        raise HTTPException(status_code=401, detail="Invalid bearer token")
    return credentials.credentials


# ── Routes ──────────────────────────────────────────────────────


@app.post("/pre", response_model=PreHookResult)
async def pre_hook(
    request: PreHookRequest,
    _token: str = Depends(verify_token),
) -> PreHookResult:
    logger.info("PRE  %s (user=%s)", request.tool.name, request.context.user_id)
    result = engine.evaluate_pre(request)
    if result.code != HookCode.OK:
        logger.warning("PRE  BLOCKED %s — %s", request.tool.name, result.error_message)
    elif result.override:
        logger.info("PRE  OVERRIDE %s — %s", request.tool.name, result.override.inputs)
    return result


@app.post("/post", response_model=PostHookResult)
async def post_hook(
    request: PostHookRequest,
    _token: str = Depends(verify_token),
) -> PostHookResult:
    logger.info("POST %s (success=%s)", request.tool.name, request.success)
    result = engine.evaluate_post(request)
    if result.override:
        logger.info("POST REDACTED %s", request.tool.name)
    return result


@app.post("/access", response_model=AccessHookResult)
async def access_hook(
    request: AccessHookRequest,
    _token: str = Depends(verify_token),
) -> AccessHookResult:
    logger.info("ACCESS user=%s", request.user_id)
    result = engine.evaluate_access(request)
    if result.deny:
        denied = [
            f"{tk}/{t}"
            for tk, spec in result.deny.items()
            for t in spec.tools
        ]
        logger.info("ACCESS DENIED %s for %s", denied, request.user_id)
    return result


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    try:
        engine.reload()
        return HealthResponse(status=HealthStatus.HEALTHY)
    except Exception as e:
        logger.error("Health check failed: %s", e)
        return HealthResponse(status=HealthStatus.UNHEALTHY)
