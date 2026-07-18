"""`vulcan setup-agent` — wire VULCAN into an agent install.

Writes skills/vulcan/SKILL.md from the tracked template with THIS clone's real
path substituted (agents need exact absolute commands, so the skill is
generated per-clone rather than tracked). For Hermes it also registers the
skill additively in ~/.hermes/config.yaml -> skills.external_dirs using line
surgery — never a YAML re-dump, so the user's comments and layout survive.
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

from .paths import ROOT

TEMPLATE = ROOT / "skills" / "vulcan" / "SKILL.md.template"
SKILL = ROOT / "skills" / "vulcan" / "SKILL.md"


def generate_skill(dest: Path | None = None) -> Path:
    dest = dest or SKILL
    if not TEMPLATE.exists():
        raise SystemExit(f"ERROR skill template missing: {TEMPLATE}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(TEMPLATE.read_text().replace("{{VULCAN_ROOT}}", str(ROOT)))
    return dest


def _insert_external_dir(text: str, skills_dir: str) -> str | None:
    """Insert skills_dir into skills.external_dirs by line surgery.

    Returns the new text, or None when the file's shape is unusual enough
    that hand-editing is safer (e.g. an inline non-empty flow list).
    """
    lines = text.splitlines(keepends=True)
    skills_i = next(
        (i for i, l in enumerate(lines) if re.match(r"^skills:\s*(#.*)?$", l)), None
    )
    if skills_i is None:
        tail = "" if (not lines or lines[-1].endswith("\n")) else "\n"
        return text + f"{tail}skills:\n  external_dirs:\n    - {skills_dir}\n"
    for i in range(skills_i + 1, len(lines)):
        if re.match(r"^\S", lines[i]):  # left the skills: block
            break
        if re.match(r"^\s+external_dirs:\s*\[.*\S.*\]", lines[i]):
            return None  # inline non-empty list — don't guess, hand-edit
        m = re.match(r"^(\s+)external_dirs:\s*(\[\s*\])?\s*(#.*)?$", lines[i])
        if m:
            if m.group(2):  # `external_dirs: []` — convert to block form
                lines[i] = re.sub(r"\[\s*\]", "", lines[i].rstrip()).rstrip() + "\n"
            item = f"{m.group(1)}  - {skills_dir}\n"
            return "".join(lines[: i + 1]) + item + "".join(lines[i + 1 :])
    # skills: exists but has no external_dirs — add one right under it
    block = f"  external_dirs:\n    - {skills_dir}\n"
    return "".join(lines[: skills_i + 1]) + block + "".join(lines[skills_i + 1 :])


def register_hermes(config_path: Path | None = None) -> str:
    """Additive registration; returns REGISTERED | ALREADY_REGISTERED |
    NOT_FOUND <path> | MANUAL. Hermes's skill cache is mtime-keyed, so a
    successful edit hot-applies without a gateway restart (docs/RECON.md)."""
    import yaml

    cfg_path = config_path or Path.home() / ".hermes" / "config.yaml"
    if not cfg_path.exists():
        return f"NOT_FOUND {cfg_path}"
    skills_dir = str(ROOT / "skills")
    text = cfg_path.read_text()
    parsed = yaml.safe_load(text) or {}
    existing = ((parsed.get("skills") or {}).get("external_dirs")) or []
    if skills_dir in [str(Path(d).expanduser()) for d in existing]:
        return "ALREADY_REGISTERED"
    new_text = _insert_external_dir(text, skills_dir)
    if new_text is None:
        return "MANUAL"
    try:  # never write a config Hermes can't parse
        reparsed = yaml.safe_load(new_text)
        assert skills_dir in reparsed["skills"]["external_dirs"]
    except Exception:
        return "MANUAL"
    shutil.copy(cfg_path, cfg_path.with_name(cfg_path.name + ".vulcan-bak"))
    cfg_path.write_text(new_text)
    return "REGISTERED"


def register_openclaw() -> str:
    """Copy the generated SKILL.md into an OpenClaw skills dir if one exists."""
    candidates = []
    if os.environ.get("OPENCLAW_HOME"):
        candidates.append(Path(os.environ["OPENCLAW_HOME"]).expanduser() / "skills")
    candidates.append(Path.home() / ".openclaw" / "skills")
    for c in candidates:
        if c.is_dir():
            dest = c / "vulcan" / "SKILL.md"
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(SKILL, dest)
            return f"COPIED {dest}"
    return "NOT_FOUND"


GENERIC_CONTRACT = """\
The 3-step contract for wiring ANY agent (full doctrine: {skill}):
  1. INVOKE   {root}/bin/vulcan run <voice-file>     (background it; 2-10 min)
              or `run --latest` after listing your platform's voice-note cache
              in config.yaml -> trigger.voice_cache_dirs (or VULCAN_VOICE_DIRS).
  2. RELAY    stream the `STATUS n/7 ...` lines as short progress messages.
  3. DELIVER  on DONE: send the file from `DELIVER MEDIA:<path>` plus the
              POST_KIT_START...END text. On ERROR: map the last STATUS stage to
              a user message (playbook in SKILL.md section 7); retry at most once.
  Cleanup on user approval: {root}/bin/vulcan cleanup <RUN_ID>"""


def cmd_setup_agent(args) -> int:
    skill = generate_skill()
    print(f"WROTE {skill} (paths bound to this clone: {ROOT})")
    if args.agent == "hermes":
        status = register_hermes()
        if status == "REGISTERED":
            print("REGISTERED in ~/.hermes/config.yaml -> skills.external_dirs "
                  "(backup: config.yaml.vulcan-bak; hot-applies, no restart needed)")
        elif status == "ALREADY_REGISTERED":
            print("ALREADY REGISTERED — nothing to change")
        elif status.startswith("NOT_FOUND"):
            print(f"Hermes config not found ({status.split(' ', 1)[1]}).\n"
                  f"Add this line to your Hermes config under skills.external_dirs:\n"
                  f"    - {ROOT / 'skills'}")
        else:  # MANUAL
            print("Your skills.external_dirs layout is unusual — add this entry "
                  f"by hand:\n    - {ROOT / 'skills'}")
        print("Verify with: hermes skills list | grep -i vulcan")
    elif args.agent == "openclaw":
        status = register_openclaw()
        if status.startswith("COPIED"):
            print(status)
            print("If your OpenClaw uses a workspace skills dir instead, copy "
                  f"{SKILL} there.")
        else:
            print("No ~/.openclaw/skills dir found (set OPENCLAW_HOME to help "
                  "detection).\nEither copy the generated skill yourself:\n"
                  f"    cp {SKILL} <your-openclaw>/skills/vulcan/SKILL.md\n"
                  "or follow the generic contract:\n")
            print(GENERIC_CONTRACT.format(root=ROOT, skill=SKILL))
    else:
        print(GENERIC_CONTRACT.format(root=ROOT, skill=SKILL))
    return 0
