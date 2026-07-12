"""Config access — config.yaml + the MiniMax key from Hermes's .env.

The key never leaves process memory and is never logged or written anywhere.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml

from .paths import CONFIG_PATH


@lru_cache(maxsize=1)
def load() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text())


def get(dotted: str, default=None):
    node = load()
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


def minimax_api_key() -> str:
    cfg = load()["director"]
    env_var = cfg["api_key_env"]
    key = os.environ.get(env_var)
    if key:
        return key
    env_file = Path(cfg["env_file"])
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith(f"{env_var}=") and not line.startswith("#"):
                value = line.split("=", 1)[1].strip().strip("'\"")
                if value:
                    return value
    raise RuntimeError(
        f"{env_var} not found in environment or {env_file} — cannot run Director"
    )


def telegram_env(name_key: str) -> str | None:
    """Read a Telegram-related env var (token/chat id) from env or Hermes .env."""
    cfg = load()["delivery"]
    env_var = cfg[name_key]
    val = os.environ.get(env_var)
    if val:
        return val
    env_file = Path(load()["director"]["env_file"])
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith(f"{env_var}=") and not line.startswith("#"):
                v = line.split("=", 1)[1].strip().strip("'\"")
                if v:
                    return v
    return None
