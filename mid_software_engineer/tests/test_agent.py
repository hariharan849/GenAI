from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from mid_software_engineer.agent import (
    DEFAULT_GSTACK_SKILLS,
    MID_SOFTWARE_ENGINEER_SYSTEM_PROMPT,
    create_mid_software_engineer_agent,
    validate_skill_paths,
)


def test_default_skills_are_limited_to_requested_gstack_skills() -> None:
    assert DEFAULT_GSTACK_SKILLS == (
        "C:/Users/HARI/.agents/skills/office-hours/",
        "C:/Users/HARI/.agents/skills/autoplan/",
        "C:/Users/HARI/.agents/skills/ship/",
    )


def test_system_prompt_contains_required_workflow_gates() -> None:
    prompt = MID_SOFTWARE_ENGINEER_SYSTEM_PROMPT

    assert "Product-owner intake" in prompt
    assert "Design flow" in prompt
    assert "Architect approval gate" in prompt
    assert "Unit tests" in prompt
    assert "Demo" in prompt
    assert "office-hours" in prompt
    assert "autoplan" in prompt
    assert "ship" in prompt


def test_validate_skill_paths_requires_skill_md(tmp_path: Path) -> None:
    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()

    with pytest.raises(FileNotFoundError):
        validate_skill_paths([str(skill_dir)])

    (skill_dir / "SKILL.md").write_text("---\nname: test\n---\n", encoding="utf-8")
    validate_skill_paths([str(skill_dir)])


def test_create_agent_passes_deepagents_configuration(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    skill_dir = tmp_path / "office-hours"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: office-hours\n---\n", encoding="utf-8")

    captured: dict[str, object] = {}

    def fake_create_deep_agent(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {"agent": "created", "kwargs": kwargs}

    class FakeFilesystemBackend:
        def __init__(self, root_dir: str, virtual_mode: bool = True) -> None:
            self.root_dir = root_dir
            self.virtual_mode = virtual_mode

    deepagents_module = types.ModuleType("deepagents")
    deepagents_module.create_deep_agent = fake_create_deep_agent  # type: ignore[attr-defined]

    filesystem_module = types.ModuleType("deepagents.backends.filesystem")
    filesystem_module.FilesystemBackend = FakeFilesystemBackend  # type: ignore[attr-defined]

    backends_module = types.ModuleType("deepagents.backends")
    backends_module.filesystem = filesystem_module  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "deepagents", deepagents_module)
    monkeypatch.setitem(sys.modules, "deepagents.backends", backends_module)
    monkeypatch.setitem(sys.modules, "deepagents.backends.filesystem", filesystem_module)

    agent = create_mid_software_engineer_agent(
        model="openai:gpt-5.4",
        backend_root=tmp_path,
        skills=[str(skill_dir)],
        debug=True,
    )

    assert agent["agent"] == "created"
    assert captured["model"] == "openai:gpt-5.4"
    assert captured["skills"] == [str(skill_dir)]
    assert captured["system_prompt"] == MID_SOFTWARE_ENGINEER_SYSTEM_PROMPT
    assert captured["debug"] is True
    assert captured["name"] == "mid-software-engineer"
    assert captured["tools"] == []
    assert captured["backend"].root_dir == str(tmp_path.resolve())  # type: ignore[attr-defined]
    assert captured["backend"].virtual_mode is False  # type: ignore[attr-defined]
