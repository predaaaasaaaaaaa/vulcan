"""setup-agent: SKILL.md generation + additive Hermes-config surgery."""

import yaml

from vulcan import setup_agent
from vulcan.paths import ROOT

GEN_DIR = str(ROOT / "skills" / "generated")


def test_generate_skill_substitutes_root(tmp_path):
    dest = tmp_path / "SKILL.md"
    setup_agent.generate_skill(dest)
    text = dest.read_text()
    assert "{{VULCAN_ROOT}}" not in text
    assert f"{ROOT}/bin/vulcan run --latest" in text


def test_register_inserts_into_existing_block(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "agent:\n  model: x\n"
        "skills:\n  external_dirs:\n    - /other/skills\n  template_vars: true\n"
        "curator:\n  enabled: false\n"
    )
    assert setup_agent.register_hermes(cfg) == "REGISTERED"
    parsed = yaml.safe_load(cfg.read_text())
    assert GEN_DIR in parsed["skills"]["external_dirs"]
    assert "/other/skills" in parsed["skills"]["external_dirs"]
    assert parsed["skills"]["template_vars"] is True  # neighbours survive
    assert parsed["curator"] == {"enabled": False}
    assert (tmp_path / "config.yaml.vulcan-bak").exists()  # backup written


def test_register_is_idempotent(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(f"skills:\n  external_dirs:\n    - {GEN_DIR}\n")
    before = cfg.read_text()
    assert setup_agent.register_hermes(cfg) == "ALREADY_REGISTERED"
    assert cfg.read_text() == before


def test_register_migrates_old_skills_entry(tmp_path):
    """Pre-generated-dir installs registered <root>/skills directly — the entry
    must be replaced, not duplicated (two dirs would register the skill twice)."""
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        f"skills:\n  external_dirs:\n    - {ROOT}/skills\n  template_vars: true\n"
    )
    assert setup_agent.register_hermes(cfg) == "MIGRATED"
    parsed = yaml.safe_load(cfg.read_text())
    assert parsed["skills"]["external_dirs"] == [GEN_DIR]
    assert parsed["skills"]["template_vars"] is True


def test_register_drops_old_entry_when_new_present(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        f"skills:\n  external_dirs:\n    - {ROOT}/skills\n    - {GEN_DIR}\n"
    )
    assert setup_agent.register_hermes(cfg) == "MIGRATED"
    assert yaml.safe_load(cfg.read_text())["skills"]["external_dirs"] == [GEN_DIR]


def test_register_creates_missing_block(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("agent:\n  model: x\n")
    assert setup_agent.register_hermes(cfg) == "REGISTERED"
    assert GEN_DIR in yaml.safe_load(cfg.read_text())["skills"]["external_dirs"]


def test_register_converts_inline_empty_list(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("skills:\n  external_dirs: []\n  inline_shell: false\n")
    assert setup_agent.register_hermes(cfg) == "REGISTERED"
    parsed = yaml.safe_load(cfg.read_text())
    assert parsed["skills"]["external_dirs"] == [GEN_DIR]
    assert parsed["skills"]["inline_shell"] is False


def test_register_bails_on_inline_nonempty_list(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("skills:\n  external_dirs: [/a, /b]\n")
    before = cfg.read_text()
    assert setup_agent.register_hermes(cfg) == "MANUAL"
    assert cfg.read_text() == before  # untouched


def test_register_missing_config(tmp_path):
    assert setup_agent.register_hermes(tmp_path / "nope.yaml").startswith("NOT_FOUND")
