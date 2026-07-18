"""`vulcan setup-agent` — wire VULCAN into an agent install.

The tracked skill (skills/vulcan/SKILL.md) ships with {{VULCAN_ROOT}}
placeholders so it survives in git and reads correctly from any clone. Weak
runtime models need exact absolute commands, so this command writes a
path-substituted copy to skills/generated/vulcan/SKILL.md (gitignored) and —
for Hermes — registers THAT dir in ~/.hermes/config.yaml ->
skills.external_dirs, migrating any old `<root>/skills` entry so the skill is
never double-registered. Config edits are line surgery, never a YAML re-dump,
so the user's comments and layout survive.
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

from .paths import ROOT

SOURCE = ROOT / "skills" / "vulcan" / "SKILL.md"
GENERATED = ROOT / "skills" / "generated" / "vulcan" / "SKILL.md"


def generate_skill(dest: Path | None = None) -> Path:
    dest = dest or GENERATED
    if not SOURCE.exists():
        raise SystemExit(f"ERROR skill source missing: {SOURCE}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(SOURCE.read_text().replace("{{VULCAN_ROOT}}", str(ROOT)))
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
    """Register skills/generated additively; returns REGISTERED | MIGRATED |
    ALREADY_REGISTERED | NOT_FOUND <path> | MANUAL. MIGRATED = an old
    `<root>/skills` entry (pre-generated-dir layout) was replaced/removed so
    the skill isn't registered twice. Hermes's skill cache is mtime-keyed, so
    a successful edit hot-applies without a gateway restart (docs/RECON.md)."""
    import yaml

    cfg_path = config_path or Path.home() / ".hermes" / "config.yaml"
    if not cfg_path.exists():
        return f"NOT_FOUND {cfg_path}"
    skills_dir = str(ROOT / "skills" / "generated")
    old_dir = str(ROOT / "skills")
    text = cfg_path.read_text()
    parsed = yaml.safe_load(text) or {}
    existing = [str(Path(d).expanduser())
                for d in (((parsed.get("skills") or {}).get("external_dirs")) or [])]
    has_new, has_old = skills_dir in existing, old_dir in existing
    if has_new and not has_old:
        return "ALREADY_REGISTERED"

    if has_old:
        old_line = re.compile(r"^(?P<ind>\s*-\s*)" + re.escape(old_dir) + r"[ \t]*\n",
                              re.MULTILINE)
        m = old_line.search(text)
        if not m:  # quoted or otherwise unusual — hand-edit
            return "MANUAL"
        repl = "" if has_new else f"{m.group('ind')}{skills_dir}\n"
        new_text = old_line.sub(repl, text, count=1)
        outcome = "MIGRATED"
    else:
        new_text = _insert_external_dir(text, skills_dir)
        outcome = "REGISTERED"
    if new_text is None:
        return "MANUAL"
    try:  # never write a config Hermes can't parse
        reparsed = yaml.safe_load(new_text)
        dirs = [str(Path(d).expanduser()) for d in reparsed["skills"]["external_dirs"]]
        assert skills_dir in dirs and old_dir not in dirs
    except Exception:
        return "MANUAL"
    shutil.copy(cfg_path, cfg_path.with_name(cfg_path.name + ".vulcan-bak"))
    cfg_path.write_text(new_text)
    return outcome


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
            shutil.copy(GENERATED, dest)
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
        elif status == "MIGRATED":
            print("MIGRATED ~/.hermes/config.yaml: old <clone>/skills entry replaced "
                  "by <clone>/skills/generated (backup: config.yaml.vulcan-bak)")
        elif status == "ALREADY_REGISTERED":
            print("ALREADY REGISTERED — nothing to change")
        elif status.startswith("NOT_FOUND"):
            print(f"Hermes config not found ({status.split(' ', 1)[1]}).\n"
                  f"Add this line to your Hermes config under skills.external_dirs:\n"
                  f"    - {GENERATED.parent.parent}")
        else:  # MANUAL
            print("Your skills.external_dirs layout is unusual — edit it by hand:\n"
                  f"    add:    - {GENERATED.parent.parent}\n"
                  f"    remove: - {ROOT / 'skills'}   (if present)")
        print("Verify with: hermes skills list | grep -i vulcan")
    elif args.agent == "openclaw":
        status = register_openclaw()
        if status.startswith("COPIED"):
            print(status)
            print("If your OpenClaw uses a workspace skills dir instead, copy "
                  f"{GENERATED} there.")
        else:
            print("No ~/.openclaw/skills dir found (set OPENCLAW_HOME to help "
                  "detection).\nEither copy the generated skill yourself:\n"
                  f"    cp {GENERATED} <your-openclaw>/skills/vulcan/SKILL.md\n"
                  "or follow the generic contract:\n")
            print(GENERIC_CONTRACT.format(root=ROOT, skill=GENERATED))
    else:
        print(GENERIC_CONTRACT.format(root=ROOT, skill=GENERATED))
    return 0
