"""Contratos da API (Pydantic v2)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --------------------------------------------------------------------------- #
# IA
# --------------------------------------------------------------------------- #
class AIConfigIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    provider: Literal["openai", "anthropic", "ollama"]
    model: str
    api_key: str | None = None
    base_url: str | None = None
    max_tokens: int = 16000
    temperature: float | None = None
    is_default: bool = False
    extra: dict[str, Any] = Field(default_factory=dict)


class AIConfigOut(ORMModel):
    id: str
    name: str
    provider: str
    model: str
    base_url: str | None
    max_tokens: int
    temperature: float | None
    is_default: bool
    extra: dict[str, Any]
    created_at: datetime
    has_api_key: bool = False


# --------------------------------------------------------------------------- #
# Fontes de dados
# --------------------------------------------------------------------------- #
class DataSourceIn(BaseModel):
    name: str | None = None
    path: str
    kind: Literal["file", "directory"] = "file"
    fmt: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)


class DataSourceOut(ORMModel):
    id: str
    name: str
    kind: str
    path: str
    fmt: str | None
    options: dict[str, Any]
    profile: dict[str, Any]
    created_at: datetime


class BrowseEntryOut(BaseModel):
    name: str
    path: str
    is_dir: bool
    size: int | None = None
    fmt: str | None = None
    modified: float | None = None


class BrowseOut(BaseModel):
    path: str
    parent: str | None
    entries: list[BrowseEntryOut]


# --------------------------------------------------------------------------- #
# Checklist / execução
# --------------------------------------------------------------------------- #
class ChecklistItemIn(BaseModel):
    agent: Literal["load", "wrangle", "clean", "feature", "eda", "viz"]
    title: str
    instructions: str = ""


class ChecklistItemOut(ORMModel):
    id: str
    position: int
    agent: str
    title: str
    instructions: str
    status: str
    origin: str
    rationale: str | None
    revision: int


class RunCreate(BaseModel):
    objective: str = Field(min_length=3)
    source_ids: list[str] = Field(min_length=1)
    ai_config_id: str | None = None
    title: str | None = None
    target_variable: str | None = None
    adaptive_checklist: bool = True


class RunSummaryOut(ORMModel):
    id: str
    title: str
    objective: str
    status: str
    checklist_revision: int
    created_at: datetime
    updated_at: datetime
    finished_at: datetime | None
    error: str | None


class StepOut(ORMModel):
    id: str
    item_id: str | None
    position: int
    agent: str
    attempt: int
    status: str
    started_at: datetime
    finished_at: datetime | None
    code: str | None
    summary: str | None
    explanation: dict[str, Any]
    error: str | None
    output_path: str | None


class RunDetailOut(RunSummaryOut):
    target_variable: str | None
    ai_config_id: str | None
    source_ids: list[str]
    adaptive_checklist: bool
    notebook_path: str | None
    items: list[ChecklistItemOut]
    steps: list[StepOut]
    sources: list[DataSourceOut] = Field(default_factory=list)
    is_running: bool = False


class EventOut(ORMModel):
    id: int
    ts: datetime
    level: str
    type: str
    agent: str | None
    message: str
    payload: dict[str, Any]
