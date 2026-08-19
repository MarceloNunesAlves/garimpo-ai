"""Modelo de dados do Garimpo.ai.

Tudo que a UI mostra sai daqui: configuração de IA, fontes de dados, checklist
(com suas revisões), etapas executadas, eventos e artefatos. É também o que
permite retomar uma execução que falhou — o estado vive no banco, não em memória.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return uuid.uuid4().hex


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


# --------------------------------------------------------------------------- #
# Configuração de IA
# --------------------------------------------------------------------------- #
class AIConfig(Base, TimestampMixin):
    """Provedor/modelo de LLM. Fica no banco para não depender de .env."""

    __tablename__ = "ai_config"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    provider: Mapped[str] = mapped_column(String(32))  # openai | anthropic | ollama
    model: Mapped[str] = mapped_column(String(120))
    api_key: Mapped[str | None] = mapped_column(Text, default=None)
    base_url: Mapped[str | None] = mapped_column(String(255), default=None)
    max_tokens: Mapped[int] = mapped_column(Integer, default=16000)
    temperature: Mapped[float | None] = mapped_column(default=None)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    extra: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


# --------------------------------------------------------------------------- #
# Fontes de dados — apenas o caminho, nunca uma cópia
# --------------------------------------------------------------------------- #
class DataSource(Base, TimestampMixin):
    __tablename__ = "data_source"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(16))  # file | directory
    path: Mapped[str] = mapped_column(Text)
    fmt: Mapped[str | None] = mapped_column(String(24), default=None)  # csv/parquet/...
    options: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # Metadados lidos sob demanda (linhas, colunas, tamanho) — cache, não cópia.
    profile: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    __table_args__ = (UniqueConstraint("path", "name", name="uq_source_path_name"),)


# --------------------------------------------------------------------------- #
# Execução
# --------------------------------------------------------------------------- #
class RunStatus:
    DRAFT = "draft"  # checklist gerado, aguardando aprovação do usuário
    RUNNING = "running"
    PAUSED = "paused"
    FAILED = "failed"
    COMPLETED = "completed"
    CANCELED = "canceled"


class Run(Base, TimestampMixin):
    __tablename__ = "run"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(200))
    objective: Mapped[str] = mapped_column(Text)
    target_variable: Mapped[str | None] = mapped_column(String(120), default=None)
    status: Mapped[str] = mapped_column(String(16), default=RunStatus.DRAFT)
    ai_config_id: Mapped[str | None] = mapped_column(
        ForeignKey("ai_config.id", ondelete="SET NULL"), default=None
    )
    source_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    checklist_revision: Mapped[int] = mapped_column(Integer, default=1)
    # Permite ao planejador reescrever o checklist entre as etapas.
    adaptive_checklist: Mapped[bool] = mapped_column(Boolean, default=True)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    notebook_path: Mapped[str | None] = mapped_column(Text, default=None)
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    ai_config: Mapped[AIConfig | None] = relationship(lazy="joined")
    items: Mapped[list["ChecklistItem"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="ChecklistItem.position",
    )
    steps: Mapped[list["RunStep"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="RunStep.started_at"
    )


class ItemStatus:
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


class ChecklistItem(Base, TimestampMixin):
    """Um item do checklist que o time de agentes deve seguir.

    O checklist é gerado antes da execução e pode ser reescrito entre as
    iterações dos agentes: itens novos entram com `origin='revision'` e o item
    guarda em `rationale` o motivo da mudança.
    """

    __tablename__ = "checklist_item"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("run.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    agent: Mapped[str] = mapped_column(String(32))  # load|clean|wrangle|feature|eda|viz
    title: Mapped[str] = mapped_column(String(200))
    instructions: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default=ItemStatus.PENDING)
    origin: Mapped[str] = mapped_column(String(16), default="planner")  # planner|revision|user
    rationale: Mapped[str | None] = mapped_column(Text, default=None)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    run: Mapped[Run] = relationship(back_populates="items")


class StepStatus:
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class RunStep(Base):
    """Execução concreta de um item do checklist (uma tentativa).

    `output_path` é o checkpoint: o parquet com o dataframe resultante. Retomar
    uma execução é recarregar o output da última etapa concluída.
    """

    __tablename__ = "run_step"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("run.id", ondelete="CASCADE"))
    item_id: Mapped[str | None] = mapped_column(
        ForeignKey("checklist_item.id", ondelete="SET NULL"), default=None
    )
    position: Mapped[int] = mapped_column(Integer, default=0)
    agent: Mapped[str] = mapped_column(String(32))
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(16), default=StepStatus.RUNNING)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    code: Mapped[str | None] = mapped_column(Text, default=None)
    summary: Mapped[str | None] = mapped_column(Text, default=None)
    # Explicação estruturada: colunas removidas e por quê, imputações, etc.
    explanation: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    output_path: Mapped[str | None] = mapped_column(Text, default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)

    run: Mapped[Run] = relationship(back_populates="steps")


class Event(Base):
    """Trilha do que está acontecendo, em tempo real (SSE) e no histórico."""

    __tablename__ = "event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("run.id", ondelete="CASCADE"), index=True
    )
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    level: Mapped[str] = mapped_column(String(16), default="info")
    type: Mapped[str] = mapped_column(String(40))
    agent: Mapped[str | None] = mapped_column(String(32), default=None)
    message: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Artifact(Base):
    __tablename__ = "artifact"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("run.id", ondelete="CASCADE"), index=True
    )
    step_id: Mapped[str | None] = mapped_column(String(32), default=None)
    kind: Mapped[str] = mapped_column(String(24))  # dataset | figure | code | notebook
    name: Mapped[str] = mapped_column(String(200))
    path: Mapped[str] = mapped_column(Text)
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
