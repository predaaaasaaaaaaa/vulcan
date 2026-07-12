"""MiniMax-M3 client — Anthropic-compatible /v1/messages endpoint.

No Anthropic services are ever called; base_url points at api.minimax.io
(Hermes's own provider, key read from Hermes's .env at call time).
"""

from __future__ import annotations

import json
import logging
import time

import httpx

from .. import config

log = logging.getLogger("vulcan.director")


class DirectorError(RuntimeError):
    pass


def chat(system: str, user: str, max_tokens: int | None = None,
         temperature: float | None = None) -> str:
    cfg = config.load()["director"]
    url = cfg["base_url"].rstrip("/") + "/v1/messages"
    headers = {
        "x-api-key": config.minimax_api_key(),
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {
        "model": cfg["model"],
        "max_tokens": max_tokens or cfg["max_tokens"],
        "temperature": cfg.get("temperature", 0.2) if temperature is None else temperature,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    last_err: Exception | None = None
    for attempt in range(4):
        try:
            with httpx.Client(timeout=httpx.Timeout(cfg.get("timeout_s", 240), connect=15)) as c:
                r = c.post(url, headers=headers, json=body)
            if r.status_code in (429, 500, 502, 503, 529):
                raise DirectorError(f"transient {r.status_code}: {r.text[:200]}")
            r.raise_for_status()
            data = r.json()
            parts = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
            text = "".join(parts).strip()
            if not text:
                raise DirectorError(f"empty completion: {json.dumps(data)[:300]}")
            return text
        except (httpx.TimeoutException, httpx.TransportError, DirectorError) as e:
            last_err = e
            wait = 2 ** attempt * 3
            log.warning("MiniMax call failed (attempt %d): %s — retrying in %ds", attempt + 1, e, wait)
            time.sleep(wait)
    raise DirectorError(f"MiniMax unreachable after retries: {last_err}")


def extract_json(text: str) -> dict:
    """Strict-ish JSON extraction: tolerate fences/prose, nothing else."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1]
        t = t[t.find("\n") + 1:] if "\n" in t else t
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end <= start:
        raise DirectorError(f"no JSON object in completion: {text[:200]!r}")
    try:
        return json.loads(t[start:end + 1])
    except json.JSONDecodeError as e:
        raise DirectorError(f"invalid JSON: {e} — head: {t[start:start+200]!r}")
