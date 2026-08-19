"""Trilha de eventos: o que a UI mostra em tempo real.

Eventos são gravados no banco (histórico + retomada) e lidos pelo endpoint SSE
por incremento de id. Simples e resistente a reinício do backend: recarregar a
página reconstrói toda a linha do tempo.
"""

from __future__ import annotations

import threading
from typing import Any

from garimpo.db.models import Event
from garimpo.db.session import session_scope

# Acordar o SSE mais rápido que o intervalo de polling.
_new_event = threading.Event()


class EventTypes:
    RUN_CREATED = "run.created"
    RUN_STARTED = "run.started"
    RUN_PAUSED = "run.paused"
    RUN_FAILED = "run.failed"
    RUN_COMPLETED = "run.completed"
    CHECKLIST_CREATED = "checklist.created"
    CHECKLIST_REVISED = "checklist.revised"
    STEP_STARTED = "step.started"
    STEP_PROGRESS = "step.progress"
    STEP_EXPLAINED = "step.explained"
    STEP_DONE = "step.done"
    STEP_FAILED = "step.failed"
    NOTEBOOK_READY = "notebook.ready"


def emit(
    run_id: str,
    type: str,
    message: str,
    *,
    agent: str | None = None,
    level: str = "info",
    payload: dict[str, Any] | None = None,
) -> None:
    with session_scope() as session:
        session.add(
            Event(
                run_id=run_id,
                type=type,
                message=message,
                agent=agent,
                level=level,
                payload=payload or {},
            )
        )
    _new_event.set()


def wait_for_event(timeout: float = 1.0) -> None:
    """Bloqueia até um novo evento ou o timeout (usado pelo loop do SSE)."""
    _new_event.wait(timeout)
    _new_event.clear()


class RunLogger:
    """Açúcar sintático para o runner: `log.step_started(...)`."""

    def __init__(self, run_id: str, agent: str | None = None):
        self.run_id = run_id
        self.agent = agent

    def bind(self, agent: str) -> "RunLogger":
        return RunLogger(self.run_id, agent)

    def info(self, type: str, message: str, **payload: Any) -> None:
        emit(self.run_id, type, message, agent=self.agent, payload=payload or {})

    def warn(self, type: str, message: str, **payload: Any) -> None:
        emit(
            self.run_id,
            type,
            message,
            agent=self.agent,
            level="warning",
            payload=payload or {},
        )

    def error(self, type: str, message: str, **payload: Any) -> None:
        emit(
            self.run_id,
            type,
            message,
            agent=self.agent,
            level="error",
            payload=payload or {},
        )
