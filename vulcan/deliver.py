"""Stage 7 — delivery to Telegram.

Primary path: Hermes's send_message tool does the actual sending — the CLI just
prints machine-readable STATUS/DELIVER lines that the SKILL.md tells Hermes to
relay (MEDIA:<path> convention, traced in RECON.md §1).

Fallback path (config delivery.mode=direct_bot): send via the bot token from
Hermes's .env directly — used only if the agent-relay path proves unreliable.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx

from . import config

log = logging.getLogger("vulcan.deliver")


def post_kit_text(post_kit: dict) -> str:
    return (
        f"🪝 {post_kit['hook']}\n\n"
        f"{post_kit['caption']}\n\n"
        f"{' '.join(post_kit['hashtags'])}"
    )


def deliver_direct_bot(mp4_path: Path, post_kit: dict | None, chat_id: str | None = None) -> bool:
    """Direct Bot API sendVideo. Returns True on success."""
    token = config.telegram_env("bot_token_env")
    chat = chat_id or config.telegram_env("chat_id_env")
    if not token or not chat:
        log.error("direct_bot delivery: missing token or chat id")
        return False
    caption = post_kit_text(post_kit)[:1024] if post_kit else ""
    try:
        with httpx.Client(timeout=httpx.Timeout(180, connect=15)) as c:
            with open(mp4_path, "rb") as f:
                r = c.post(
                    f"https://api.telegram.org/bot{token}/sendVideo",
                    data={"chat_id": chat, "caption": caption, "supports_streaming": "true"},
                    files={"video": (mp4_path.name, f, "video/mp4")},
                )
        ok = r.status_code == 200 and r.json().get("ok")
        if not ok:
            log.error("sendVideo failed: %s %s", r.status_code, r.text[:300])
        return bool(ok)
    except Exception as e:
        log.error("direct_bot delivery error: %s", e)
        return False


def emit_delivery_lines(mp4_path: Path, post_kit: dict | None, contact_sheet: Path | None) -> None:
    """Print the lines Hermes's skill relays. MEDIA:<abs path> → native video."""
    print(f"DELIVER MEDIA:{mp4_path.resolve()}")
    if contact_sheet and contact_sheet.exists():
        print(f"DELIVER_SHEET MEDIA:{contact_sheet.resolve()}")
    if post_kit:
        print("POST_KIT_START")
        print(post_kit_text(post_kit))
        print("POST_KIT_END")
