"""Nạp prompt có version từ ``prompts/<name>/v<N>.md``.

Prompt đã phát hành là bất biến: khi đổi nội dung, tạo file version mới thay vì
ghi đè file cũ. Registry kiểm tra tên và version trong front matter khớp đường dẫn.
"""

import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

_NAME_PATTERN = re.compile(r"[a-z][a-z0-9_]*\Z")
_VERSION_PATTERN = re.compile(r"v[1-9][0-9]*\Z")
_PLACEHOLDER_PATTERN = re.compile(r"{{\s*([a-z][a-z0-9_]*)\s*}}")
_FRONT_MATTER_PATTERN = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n(.*)\Z", re.DOTALL)


class PromptError(ValueError):
    """Prompt file hoặc biến render không hợp lệ."""


class PromptTemplate(BaseModel):
    """Value Object của một prompt version cụ thể."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    version: str
    description: str = Field(min_length=1)
    model_tier: Literal["small", "large"]
    output_schema: str = Field(min_length=1)
    variables: tuple[str, ...]
    body: str = Field(min_length=1)

    @field_validator("name")
    @classmethod
    def _nonempty_identifier(cls, value: str) -> str:
        if not _NAME_PATTERN.fullmatch(value):
            raise ValueError("must be a lowercase identifier")
        return value

    @field_validator("version")
    @classmethod
    def _valid_version(cls, value: str) -> str:
        if not _VERSION_PATTERN.fullmatch(value):
            raise ValueError("must use v<N> with N >= 1")
        return value

    @field_validator("variables")
    @classmethod
    def _unique_variables(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)) or any(
            not _NAME_PATTERN.fullmatch(value) for value in values
        ):
            raise ValueError("variables must be unique lowercase identifiers")
        return values

    @model_validator(mode="after")
    def _body_matches_variables(self) -> "PromptTemplate":
        placeholders = set(_PLACEHOLDER_PATTERN.findall(self.body))
        if placeholders != set(self.variables):
            raise ValueError("body placeholders must match declared variables")
        return self

    def render(self, **values: str) -> str:
        """Thay ``{{ variable }}``; từ chối biến thiếu, thừa hoặc sai kiểu."""
        expected = set(self.variables)
        supplied = set(values)
        if expected != supplied:
            missing = sorted(expected - supplied)
            extra = sorted(supplied - expected)
            raise PromptError(f"Prompt variables mismatch: missing={missing}, extra={extra}")
        if any(not isinstance(value, str) for value in values.values()):
            raise PromptError("Prompt variables must be strings")
        return _PLACEHOLDER_PATTERN.sub(lambda match: values[match.group(1)], self.body)


class PromptRegistry:
    """Nạp template theo tên và version; ``latest`` chọn version số lớn nhất."""

    def __init__(self, root: Path = Path("prompts")) -> None:
        self._root = root

    def get(self, name: str, version: str = "latest") -> PromptTemplate:
        if not _NAME_PATTERN.fullmatch(name):
            raise PromptError(f"Invalid prompt name: {name!r}")
        directory = self._root / name
        if version == "latest":
            versions = [
                (int(path.stem[1:]), path.stem)
                for path in directory.glob("v*.md")
                if _VERSION_PATTERN.fullmatch(path.stem)
            ]
            if not versions:
                raise PromptError(f"No versioned prompt found: {name}")
            version = max(versions)[1]
        elif not _VERSION_PATTERN.fullmatch(version):
            raise PromptError(f"Invalid prompt version: {version!r}")

        path = directory / f"{version}.md"
        try:
            source = path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise PromptError(f"Prompt not found: {name}/{version}") from exc
        match = _FRONT_MATTER_PATTERN.fullmatch(source)
        if match is None:
            raise PromptError(f"Invalid front matter: {path}")
        try:
            metadata: Any = yaml.safe_load(match.group(1))
        except yaml.YAMLError as exc:
            raise PromptError(f"Invalid YAML front matter: {path}") from exc
        if not isinstance(metadata, dict):
            raise PromptError(f"Front matter must be a mapping: {path}")
        try:
            template = PromptTemplate.model_validate({**metadata, "body": match.group(2)})
        except ValidationError as exc:
            raise PromptError(f"Invalid prompt metadata: {path}: {exc}") from exc
        if template.name != name or template.version != version:
            raise PromptError(f"Prompt name/version does not match path: {path}")
        return template
