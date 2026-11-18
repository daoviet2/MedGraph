"""Hợp đồng PromptRegistry: version, metadata và render biến."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from medgraph.llm.prompts import PromptError, PromptRegistry, PromptTemplate


def _write_prompt(root: Path, name: str, version: str, body: str = "Hello {{term}}") -> None:
    directory = root / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{version}.md").write_text(
        "---\n"
        f"name: {name}\n"
        f"version: {version}\n"
        "description: Test prompt\n"
        "model_tier: small\n"
        "output_schema: AliasDraftBatch\n"
        "variables: [term]\n"
        "---\n"
        f"{body}",
        encoding="utf-8",
    )


@pytest.mark.unit
def test_real_prompts_have_matching_version_and_required_metadata() -> None:
    root = Path("prompts")
    files = list(root.glob("*/v*.md"))
    assert files
    registry = PromptRegistry(root)
    for path in files:
        prompt = registry.get(path.parent.name, path.stem)
        assert prompt.name == path.parent.name
        assert prompt.version == path.stem
        assert prompt.description
        assert prompt.model_tier in ("small", "large")
        assert prompt.output_schema

    aliases = registry.get("build_aliases", "v1")
    assert aliases.output_schema == "AliasDraftBatch"
    assert "không bịa thuật ngữ" in aliases.body.lower()
    assert "tiếng Việt đời thường" in aliases.body
    assert "JSON" in aliases.body


@pytest.mark.unit
def test_latest_uses_numeric_version_and_older_version_remains_readable(tmp_path: Path) -> None:
    _write_prompt(tmp_path, "aliases", "v1", "old {{term}}")
    _write_prompt(tmp_path, "aliases", "v2", "second {{term}}")
    _write_prompt(tmp_path, "aliases", "v10", "new {{term}}")
    registry = PromptRegistry(tmp_path)

    assert registry.get("aliases").version == "v10"
    assert registry.get("aliases").render(term="ho") == "new ho"
    assert registry.get("aliases", "v1").render(term="ho") == "old ho"


@pytest.mark.unit
def test_render_requires_exact_variables_and_keeps_inserted_braces_literal(tmp_path: Path) -> None:
    _write_prompt(tmp_path, "aliases", "v1", "{{term}} / {{term}}")
    prompt = PromptRegistry(tmp_path).get("aliases")
    assert prompt.render(term="{{other}}") == "{{other}} / {{other}}"
    with pytest.raises(PromptError, match="missing"):
        prompt.render()
    with pytest.raises(PromptError, match="extra"):
        prompt.render(term="ho", unused="x")
    with pytest.raises(PromptError, match="must be strings"):
        prompt.render(term=123)  # type: ignore[arg-type]


@pytest.mark.unit
def test_malformed_metadata_and_path_mismatch_are_rejected(tmp_path: Path) -> None:
    _write_prompt(tmp_path, "aliases", "v1")
    path = tmp_path / "aliases" / "v1.md"
    source = path.read_text(encoding="utf-8")
    path.write_text(source.replace("version: v1", "version: v2"), encoding="utf-8")
    with pytest.raises(PromptError, match="does not match path"):
        PromptRegistry(tmp_path).get("aliases", "v1")

    path.write_text(source.replace("output_schema: AliasDraftBatch\n", ""), encoding="utf-8")
    with pytest.raises(PromptError, match="Invalid prompt metadata"):
        PromptRegistry(tmp_path).get("aliases", "v1")


@pytest.mark.unit
def test_registry_rejects_invalid_paths_and_missing_versions(tmp_path: Path) -> None:
    registry = PromptRegistry(tmp_path)
    with pytest.raises(PromptError, match="Invalid prompt name"):
        registry.get("../outside")
    with pytest.raises(PromptError, match="Invalid prompt version"):
        registry.get("aliases", "../../outside")
    with pytest.raises(PromptError, match="No versioned prompt"):
        registry.get("aliases")


@pytest.mark.unit
def test_prompt_template_is_frozen_and_rejects_undeclared_placeholders() -> None:
    prompt = PromptTemplate(
        name="aliases",
        version="v1",
        description="Test",
        model_tier="small",
        output_schema="AliasDraftBatch",
        variables=("term",),
        body="{{term}}",
    )
    with pytest.raises(ValidationError):
        prompt.version = "v2"
    with pytest.raises(ValidationError, match="placeholders"):
        PromptTemplate.model_validate({**prompt.model_dump(), "body": "{{unexpected}}"})
