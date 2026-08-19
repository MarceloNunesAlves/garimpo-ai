"""Orquestrador: executa o checklist, etapa por etapa, com checkpoint em disco.

Garantias que a UI depende:

* toda etapa concluída deixa um checkpoint (`RunStep.output_path`), então uma
  falha na etapa 4 não joga fora as etapas 1–3;
* retomar (`resume`) recarrega o checkpoint da última etapa concluída e segue
  do item que falhou — nada é reexecutado à toa;
* entre uma etapa e outra o planejador pode reescrever o que ainda falta, e a
  mudança vira evento + nova revisão do checklist.
"""

from __future__ import annotations

import threading
import traceback
from datetime import datetime, timezone
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from garimpo.config import settings
from garimpo.core import explain, notebook, storage, steps
from garimpo.core.checklist import ChecklistPlanner
from garimpo.core.events import EventTypes, RunLogger, emit
from garimpo.core.llm import build_llm
from garimpo.db.models import (
    Artifact,
    ChecklistItem,
    DataSource,
    ItemStatus,
    Run,
    RunStatus,
    RunStep,
    StepStatus,
    new_id,
)
from garimpo.db.session import session_scope

_threads: dict[str, threading.Thread] = {}
_cancels: dict[str, threading.Event] = {}
_lock = threading.Lock()


def is_running(run_id: str) -> bool:
    with _lock:
        thread = _threads.get(run_id)
    return bool(thread and thread.is_alive())


def request_cancel(run_id: str) -> bool:
    with _lock:
        event = _cancels.get(run_id)
    if event:
        event.set()
        return True
    return False


def start(run_id: str) -> None:
    """Dispara (ou retoma) a execução em background."""
    if is_running(run_id):
        raise RuntimeError("Esta execução já está em andamento.")
    cancel = threading.Event()
    thread = threading.Thread(target=_execute, args=(run_id, cancel), daemon=True)
    with _lock:
        _threads[run_id] = thread
        _cancels[run_id] = cancel
    thread.start()


# --------------------------------------------------------------------------- #
def _execute(run_id: str, cancel: threading.Event) -> None:
    log = RunLogger(run_id)
    try:
        with session_scope() as session:
            run = session.get(Run, run_id)
            if run is None:
                return
            run.status = RunStatus.RUNNING
            run.error = None
            session.commit()

            resumed = any(i.status == ItemStatus.DONE for i in run.items)
            emit(
                run_id,
                EventTypes.RUN_STARTED,
                "Execução retomada de onde parou." if resumed else "Execução iniciada.",
                payload={"resumed": resumed},
            )
            _run_checklist(session, run, cancel, log)
    except Exception as exc:  # falha fora do laço de etapas
        _fail_run(run_id, exc)
    finally:
        with _lock:
            _threads.pop(run_id, None)
            _cancels.pop(run_id, None)


def _run_checklist(
    session: Session, run: Run, cancel: threading.Event, log: RunLogger
) -> None:
    run_id = run.id
    llm = _build_llm(session, run)
    planner = ChecklistPlanner(llm)
    sources = _sources_payload(session, run)

    data = _restore_checkpoint(session, run)

    while True:
        item = _next_item(session, run_id)
        if item is None:
            break
        if cancel.is_set():
            run.status = RunStatus.PAUSED
            session.commit()
            emit(run_id, EventTypes.RUN_PAUSED, "Execução pausada pelo usuário.")
            return

        agent = item.agent
        label = steps.LABELS.get(agent, agent)
        step_log = log.bind(agent)

        attempts = session.scalars(
            select(RunStep).where(RunStep.item_id == item.id)
        ).all()
        step = RunStep(
            id=new_id(),
            run_id=run_id,
            item_id=item.id,
            position=item.position,
            agent=agent,
            attempt=len(attempts) + 1,
            status=StepStatus.RUNNING,
        )
        item.status = ItemStatus.RUNNING
        session.add(step)
        session.commit()

        emit(
            run_id,
            EventTypes.STEP_STARTED,
            f"{label}: {item.title}",
            agent=agent,
            payload={
                "item_id": item.id,
                "step_id": step.id,
                "position": item.position,
                "attempt": step.attempt,
                "instructions": item.instructions,
            },
        )

        before = data.copy(deep=True) if isinstance(data, pd.DataFrame) else None

        try:
            ctx = steps.StepContext(
                run_id=run_id,
                objective=run.objective,
                instructions=item.instructions,
                target_variable=run.target_variable,
                llm=llm,
                sources=sources,
                log=lambda t, m, a=agent: emit(run_id, t, m, agent=a),
                max_retries=settings.max_retries_per_step,
            )
            result = steps.REGISTRY[agent](ctx, data)
        except Exception as exc:
            _fail_step(session, run, item, step, exc)
            return

        if isinstance(result.dataframe, pd.DataFrame):
            data = result.dataframe
            step.output_path = storage.save_frame(run_id, item.position, agent, data)

        diff = explain.diff_dataframes(before, result.dataframe, result.code)
        narrative = explain.narrate(
            llm,
            title=item.title,
            agent=agent,
            objective=run.objective,
            diff=diff,
            code=result.code,
        )
        step.code = result.code
        step.summary = result.summary
        step.explanation = {
            "headline": explain.headline(diff),
            "narrative": narrative,
            "diff": diff,
            "extra": result.extra,
            "call": result.call,
            "imports": result.imports,
        }
        step.status = StepStatus.DONE
        step.finished_at = datetime.now(timezone.utc)
        item.status = ItemStatus.DONE
        session.commit()

        _register_artifacts(session, run_id, step, result)

        emit(
            run_id,
            EventTypes.STEP_EXPLAINED,
            narrative or explain.headline(diff),
            agent=agent,
            payload={"step_id": step.id, "diff": diff},
        )
        emit(
            run_id,
            EventTypes.STEP_DONE,
            f"{label} concluída — {explain.headline(diff)}",
            agent=agent,
            payload={
                "step_id": step.id,
                "item_id": item.id,
                "shape": list(data.shape) if isinstance(data, pd.DataFrame) else None,
            },
        )

        if run.adaptive_checklist:
            _revise_checklist(session, run, planner, item, step, data)

    _finish_run(session, run)


# --------------------------------------------------------------------------- #
def _next_item(session: Session, run_id: str) -> ChecklistItem | None:
    return session.scalars(
        select(ChecklistItem)
        .where(
            ChecklistItem.run_id == run_id,
            ChecklistItem.status.in_([ItemStatus.PENDING, ItemStatus.RUNNING, ItemStatus.FAILED]),
        )
        .order_by(ChecklistItem.position)
        .limit(1)
    ).first()


def _restore_checkpoint(session: Session, run: Run) -> pd.DataFrame | None:
    """Recarrega o dataframe da última etapa concluída (retomada)."""
    last = session.scalars(
        select(RunStep)
        .where(RunStep.run_id == run.id, RunStep.status == StepStatus.DONE)
        .order_by(RunStep.position.desc(), RunStep.started_at.desc())
        .limit(1)
    ).first()
    if last is None or not last.output_path:
        return None
    frame = storage.load_frame(last.output_path)
    if frame is not None:
        emit(
            run.id,
            EventTypes.STEP_PROGRESS,
            f"Checkpoint restaurado da etapa {last.position + 1} "
            f"({frame.shape[0]} linhas x {frame.shape[1]} colunas).",
            payload={"step_id": last.id},
        )
    return frame


def _revise_checklist(
    session: Session,
    run: Run,
    planner: ChecklistPlanner,
    done_item: ChecklistItem,
    step: RunStep,
    data: pd.DataFrame | None,
) -> None:
    pending = session.scalars(
        select(ChecklistItem)
        .where(ChecklistItem.run_id == run.id, ChecklistItem.status == ItemStatus.PENDING)
        .order_by(ChecklistItem.position)
    ).all()
    if not pending:
        return

    payload = [
        {"agent": i.agent, "title": i.title, "instructions": i.instructions}
        for i in pending
    ]
    try:
        revision = planner.revise(
            objective=run.objective,
            done_title=done_item.title,
            done_agent=done_item.agent,
            summary=step.summary or "",
            facts=(step.explanation or {}).get("diff", {}),
            shape=tuple(data.shape) if isinstance(data, pd.DataFrame) else (0, 0),
            columns=[str(c) for c in data.columns] if isinstance(data, pd.DataFrame) else [],
            pending=payload,
        )
    except Exception as exc:  # revisão é best-effort: o plano original segue valendo
        emit(
            run.id,
            EventTypes.CHECKLIST_REVISED,
            f"Não foi possível revisar o checklist ({type(exc).__name__}); "
            "seguindo com o plano original.",
            level="warning",
        )
        return

    if not revision.get("changed") or revision["items"] == payload:
        return

    run.checklist_revision += 1
    for item in pending:
        session.delete(item)
    session.flush()

    start_position = done_item.position + 1
    for offset, entry in enumerate(revision["items"]):
        session.add(
            ChecklistItem(
                id=new_id(),
                run_id=run.id,
                position=start_position + offset,
                agent=entry["agent"],
                title=entry["title"],
                instructions=entry["instructions"],
                origin="revision",
                rationale=revision.get("rationale"),
                revision=run.checklist_revision,
            )
        )
    session.commit()

    emit(
        run.id,
        EventTypes.CHECKLIST_REVISED,
        revision.get("rationale") or "Checklist ajustado após a etapa anterior.",
        payload={
            "revision": run.checklist_revision,
            "before": payload,
            "after": revision["items"],
        },
    )


def _register_artifacts(
    session: Session, run_id: str, step: RunStep, result: steps.StepResult
) -> None:
    if step.output_path:
        session.add(
            Artifact(
                id=new_id(),
                run_id=run_id,
                step_id=step.id,
                kind="dataset",
                name=f"Etapa {step.position + 1} — {steps.LABELS.get(step.agent, step.agent)}",
                path=step.output_path,
                meta={"agent": step.agent},
            )
        )
    session.commit()


def _finish_run(session: Session, run: Run) -> None:
    try:
        path = notebook.build_notebook(session, run)
        run.notebook_path = str(path)
        session.add(
            Artifact(
                id=new_id(),
                run_id=run.id,
                kind="notebook",
                name="Notebook reprodutível",
                path=str(path),
                meta={},
            )
        )
        emit(
            run.id,
            EventTypes.NOTEBOOK_READY,
            "Notebook reprodutível gerado.",
            payload={"path": str(path)},
        )
    except Exception as exc:
        emit(
            run.id,
            EventTypes.RUN_FAILED,
            f"Etapas concluídas, mas o notebook falhou: {type(exc).__name__}: {exc}",
            level="warning",
        )

    run.status = RunStatus.COMPLETED
    run.finished_at = datetime.now(timezone.utc)
    session.commit()
    emit(run.id, EventTypes.RUN_COMPLETED, "Garimpo concluído.")


def _fail_step(
    session: Session, run: Run, item: ChecklistItem, step: RunStep, exc: Exception
) -> None:
    detail = f"{type(exc).__name__}: {exc}"
    step.status = StepStatus.FAILED
    step.error = f"{detail}\n\n{traceback.format_exc()}"
    step.finished_at = datetime.now(timezone.utc)
    item.status = ItemStatus.FAILED
    run.status = RunStatus.FAILED
    run.error = detail
    session.commit()
    emit(
        run.id,
        EventTypes.STEP_FAILED,
        f"Falha em '{item.title}': {detail}",
        agent=item.agent,
        level="error",
        payload={"step_id": step.id, "item_id": item.id},
    )
    emit(
        run.id,
        EventTypes.RUN_FAILED,
        "Execução interrompida. As etapas concluídas foram preservadas — "
        "corrija e use 'Retomar' para continuar do ponto da falha.",
        level="error",
    )


def _fail_run(run_id: str, exc: Exception) -> None:
    detail = f"{type(exc).__name__}: {exc}"
    with session_scope() as session:
        run = session.get(Run, run_id)
        if run is not None:
            run.status = RunStatus.FAILED
            run.error = detail
    emit(run_id, EventTypes.RUN_FAILED, detail, level="error")


def _build_llm(session: Session, run: Run) -> Any:
    config = run.ai_config
    if config is None:
        return None
    try:
        return build_llm(config)
    except Exception as exc:
        emit(
            run.id,
            EventTypes.RUN_FAILED,
            f"Configuração de IA inválida: {type(exc).__name__}: {exc}",
            level="error",
        )
        raise


def _sources_payload(session: Session, run: Run) -> list[dict[str, Any]]:
    if not run.source_ids:
        return []
    rows = session.scalars(
        select(DataSource).where(DataSource.id.in_(run.source_ids))
    ).all()
    by_id = {r.id: r for r in rows}
    ordered = [by_id[sid] for sid in run.source_ids if sid in by_id]
    return [
        {
            "id": s.id,
            "name": s.name,
            "path": s.path,
            "kind": s.kind,
            "fmt": s.fmt,
            "options": s.options or {},
        }
        for s in ordered
    ]
