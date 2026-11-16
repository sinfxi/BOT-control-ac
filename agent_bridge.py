"""Secure polling bridge between the local Telethon client and the Cloudflare API.

Only the explicitly allow-listed, read-only diagnostics jobs are executable here.
The Telegram session remains local and is never sent to Cloudflare.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import urllib.error
import urllib.request
from typing import Any

from telethon import functions

log = logging.getLogger("tgmanager.agent")


class AgentAPIError(RuntimeError):
    pass


def _request_sync(base_url: str, token: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=body,
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "TGManager-Agent/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            raw = response.read(16_384)
    except urllib.error.HTTPError as exc:
        detail = exc.read(2048).decode("utf-8", "replace")
        raise AgentAPIError(f"Cloudflare API returned HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise AgentAPIError(f"Cloudflare API unavailable: {exc}") from exc
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AgentAPIError("Cloudflare API returned invalid JSON") from exc
    if not isinstance(data, dict):
        raise AgentAPIError("Cloudflare API returned an invalid response")
    return data


async def _request(base_url: str, token: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    return await asyncio.to_thread(_request_sync, base_url, token, path, payload)


async def _execute_job(client: Any, job: dict[str, Any]) -> dict[str, Any]:
    job_type = job.get("type")
    if job_type == "agent.ping":
        started = time.perf_counter()
        await client(functions.PingRequest(ping_id=int(time.time() * 1000) % (2**31)))
        return {"telegram": "reachable", "latency_ms": round((time.perf_counter() - started) * 1000, 2)}
    if job_type == "agent.status":
        me = await client.get_me()
        return {
            "authorized": True,
            "user_id": me.id,
            "username": me.username,
            "display_name": " ".join(p for p in (me.first_name, me.last_name) if p),
        }
    raise AgentAPIError("Unsupported job type; execution denied")


async def run_agent(client: Any, me: Any) -> None:
    """Register and poll the authenticated agent queue until cancelled."""
    base_url = os.getenv("FXI_API_URL", "https://telegram-account.99lq9ohj-kfshcd.workers.dev").strip()
    token = os.getenv("FXI_AGENT_API_KEY", "").strip()
    if not token:
        return
    agent_id = os.getenv("FXI_AGENT_ID", "").strip() or f"tg-{me.id}"
    if not all(ch.isalnum() or ch in "._:-" for ch in agent_id) or not 3 <= len(agent_id) <= 64:
        raise AgentAPIError("FXI_AGENT_ID must be 3-64 characters: letters, digits, dot, underscore, colon or hyphen")

    capabilities = ["agent.ping", "agent.status"]
    await _request(base_url, token, "/v1/agent/register", {
        "agent_id": agent_id, "version": "1.0.0", "capabilities": capabilities
    })
    log.info("Cloudflare agent registered (%s)", agent_id)
    last_heartbeat = 0.0
    backoff = 3.0

    while True:
        try:
            if time.monotonic() - last_heartbeat >= 30:
                await _request(base_url, token, "/v1/agent/heartbeat", {"agent_id": agent_id})
                last_heartbeat = time.monotonic()

            claimed = await _request(base_url, token, "/v1/agent/jobs/claim", {"agent_id": agent_id})
            job = claimed.get("job")
            if job:
                try:
                    result = await _execute_job(client, job)
                    report = {"agent_id": agent_id, "job_id": job["id"], "status": "succeeded", "result": result}
                except Exception as exc:  # report safe error type, never session data
                    log.warning("Agent job %s failed: %s", job.get("id"), type(exc).__name__)
                    report = {
                        "agent_id": agent_id, "job_id": job["id"], "status": "failed",
                        "error": type(exc).__name__,
                    }
                await _request(base_url, token, "/v1/agent/jobs/result", report)
            backoff = 3.0
            await asyncio.sleep(4)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("Cloudflare agent bridge retry: %s", type(exc).__name__)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30.0)
