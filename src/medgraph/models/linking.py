"""Hợp đồng dữ liệu trung gian của linker."""

from pydantic import BaseModel, ConfigDict, Field

from medgraph.models.schemas import Entity, EntityType


class CatalogEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    type: EntityType
    name_vi: str
    aliases_vi: tuple[str, ...] = ()


class ParentLink(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    hops: int = Field(ge=1, le=2)
    negated: bool


class LinkedMention(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    entity: Entity
    method: str | None = None
    parents: tuple[ParentLink, ...] = ()
    clarification: str | None = None
