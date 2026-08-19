from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from garimpo.core import runner, storage
from garimpo.core.checklist import ChecklistPlanner
from garimpo.core.events import EventTypes, emit, wait_for_event
from garimpo.core.llm import build_llm
from garimpo.db.models import (
    AIConfig,
    Artifact,
    ChecklistItem,
    DataSource,
    Event,
    ItemStatus,
    Run,
    RunStatus,
    RunStep,
    new_id,
)
from garimpo.db.session import SessionLocal, get_session
from garimpo.schemas import (
    ChecklistItemIn,
    DataSourceOut,
    EventOut,
    RunCreate,
    RunDetailOut,
    RunSummaryOut,
)

router = APIRouter(prefix="/api/runs", tags=["execuções"])

RESUMABLE = {RunStatus.FAILED, RunStatus.PAUSED, RunStatus.DRAFT}


# --------------------------------------------------------------------------- #
# criação: gera o checklist ANTES de qualquer agente rodar
# --------------------------------------------------------------------------- #
@router.post("", response_model=RunDetailOut, status_code=201)
async def create_run(payload: RunCreate, session: Session = Depends(get_session)):
    sources = _load_sources(session, payload.source_ids)
    config = _pick_config(session, payload.ai_config_id)

    llm = None
    if config is not None:
        try:
            llm = await run_in_threadpool(build_llm, config)
        except Exception as exc:
            raise HTTPException(400, f"Configuração de IA inválida: {exc}") from exc

    schema = {
        s.name: {
            "kind": s.kind,
            "path": s.path,
            "columns": (s.profile or {}).get("columns", []),
            "dtypes": (s.profile or {}).get("dtypes", {}),
        }
        for s in sources
    }
    planner = ChecklistPlanner(llm)
    plan = await run_in_threadpool(
        planner.create,
        payload.objective,
        [{"name": s.name, "path": s.path, "kind": s.kind, "fmt": s.fmt} for s in sources],
        schema,
    )

    run = Run(
        id=new_id(),
        title=payload.title or plan["title"],
        objective=payload.objective,
        target_variable=payload.target_variable or plan.get("target_variable"),
        status=RunStatus.DRAFT,
        ai_config_id=config.id if config else None,
        source_ids=[s.id for s in sources],
        adaptive_checklist=payload.adaptive_checklist,
    )
    session.add(run)
    for position, item in enumerate(plan["items"]):
        session.add(
            ChecklistItem(
                id=new_id(),
                run_id=run.id,
                position=position,
                agent=item["agent"],
                title=item["title"],
                instructions=item["instructions"],
                origin="planner",
            )
        )
    session.commit()
    session.refresh(run)

    emit(
        run.id,
        EventTypes.CHECKLIST_CREATED,
        "Checklist criado. Revise, ajuste se quiser e inicie o garimpo.",
        payload={"items": plan["items"], "notes": plan.get("notes", [])},
    )
    return _detail(session, run)


@router.get("", response_model=list[RunSummaryOut])
def list_runs(session: Session = Depends(get_session), limit: int = Query(50, le=200)):
    return session.scalars(
        select(Run).order_by(Run.created_at.desc()).limit(limit)
    ).all()


@router.get("/{run_id}", response_model=RunDetailOut)
def get_run(run_id: str, session: Session = Depends(get_session)):
    return _detail(session, _require(session, run_id))


@router.delete("/{run_id}", status_code=204)
def delete_run(run_id: str, session: Session = Depends(get_session)):
    run = _require(session, run_id)
    if runner.is_running(run_id):
        raise HTTPException(409, "Pare a execução antes de excluir.")
    session.delete(run)
    session.commit()


# --------------------------------------------------------------------------- #
# checklist
# --------------------------------------------------------------------------- #
@router.put("/{run_id}/checklist", response_model=RunDetailOut)
def replace_checklist(
    run_id: str, items: list[ChecklistItemIn], session: Session = Depends(get_session)
):
    """Substitui os itens ainda não executados (edição manual do usuário)."""
    run = _require(session, run_id)
    if runner.is_running(run_id):
        raise HTTPException(409, "Não é possível editar o checklist durante a execução.")
    if not items:
        raise HTTPException(400, "O checklist precisa de pelo menos um item.")

    done = [i for i in run.items if i.status == ItemStatus.DONE]
    for item in run.items:
        if item.status != ItemStatus.DONE:
            session.delete(item)
    session.flush()

    offset = max((i.position for i in done), default=-1) + 1
    for index, entry in enumerate(items):
        session.add(
            ChecklistItem(
                id=new_id(),
                run_id=run.id,
                position=offset + index,
                agent=entry.agent,
                title=entry.title,
                instructions=entry.instructions,
                origin="user",
                revision=run.checklist_revision,
            )
        )
    session.commit()
    session.refresh(run)
    emit(run.id, EventTypes.CHECKLIST_REVISED, "Checklist ajustado manualmente.")
    return _detail(session, run)


# --------------------------------------------------------------------------- #
# execução
# --------------------------------------------------------------------------- #
@router.post("/{run_id}/start", response_model=RunSummaryOut)
def start_run(run_id: str, session: Session = Depends(get_session)):
    run = _require(session, run_id)
    if runner.is_running(run_id):
        raise HTTPException(409, "Esta execução já está em andamento.")
    if run.status == RunStatus.COMPLETED:
        raise HTTPException(409, "Execução já concluída. Crie um novo garimpo.")
    if not any(i.status != ItemStatus.DONE for i in run.items):
        raise HTTPException(400, "Não há itens pendentes no checklist.")

    # Itens que falharam voltam para pendente: retomar significa tentar de novo.
    for item in run.items:
        if item.status in (ItemStatus.FAILED, ItemStatus.RUNNING):
            item.status = ItemStatus.PENDING
    run.status = RunStatus.RUNNING
    run.error = None
    session.commit()

    runner.start(run_id)
    return RunSummaryOut.model_validate(run)


@router.post("/{run_id}/resume", response_model=RunSummaryOut)
def resume_run(run_id: str, session: Session = Depends(get_session)):
    run = _require(session, run_id)
    if run.status not in RESUMABLE:
        raise HTTPException(409, f"Não é possível retomar no status '{run.status}'.")
    return start_run(run_id, session)


@router.post("/{run_id}/cancel", response_model=RunSummaryOut)
def cancel_run(run_id: str, session: Session = Depends(get_session)):
    run = _require(session, run_id)
    if not runner.request_cancel(run_id):
        run.status = RunStatus.PAUSED
        session.commit()
    emit(run_id, EventTypes.RUN_PAUSED, "Pausa solicitada — a etapa atual será concluída.")
    return RunSummaryOut.model_validate(run)


# --------------------------------------------------------------------------- #
# leitura de resultados
# --------------------------------------------------------------------------- #
@router.get("/{run_id}/events", response_model=list[EventOut])
def list_events(
    run_id: str, after: int = Query(0), session: Session = Depends(get_session)
):
    _require(session, run_id)
    return session.scalars(
        select(Event).where(Event.run_id == run_id, Event.id > after).order_by(Event.id)
    ).all()


@router.get("/{run_id}/stream")
async def stream_events(run_id: str, request: Request, after: int = Query(0)):
    """SSE: a linha do tempo ao vivo da UI."""
    with SessionLocal() as session:
        _require(session, run_id)

    async def generator():
        last_id = after
        while True:
            if await request.is_disconnected():
                break
            rows, status = await run_in_threadpool(_poll, run_id, last_id)
            for row in rows:
                last_id = max(last_id, row["id"])
                yield f"event: {row['type']}\ndata: {json.dumps(row, default=str)}\n\n"
            if status in (RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.PAUSED) and not rows:
                yield f"event: idle\ndata: {json.dumps({'status': status})}\n\n"
            await asyncio.sleep(0.4)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _poll(run_id: str, last_id: int) -> tuple[list[dict[str, Any]], str]:
    wait_for_event(0.3)
    with SessionLocal() as session:
        rows = session.scalars(
            select(Event)
            .where(Event.run_id == run_id, Event.id > last_id)
            .order_by(Event.id)
            .limit(200)
        ).all()
        run = session.get(Run, run_id)
        return (
            [
                {
                    "id": r.id,
                    "ts": r.ts.isoformat(),
                    "level": r.level,
                    "type": r.type,
                    "agent": r.agent,
                    "message": r.message,
                    "payload": r.payload,
                }
                for r in rows
            ],
            run.status if run else RunStatus.FAILED,
        )


@router.get("/{run_id}/steps/{step_id}/data")
async def step_data(
    run_id: str,
    step_id: str,
    rows: int = Query(25, le=500),
    session: Session = Depends(get_session),
):
    """Amostra do dataframe salvo no checkpoint da etapa."""
    step = session.get(RunStep, step_id)
    if step is None or step.run_id != run_id:
        raise HTTPException(404, "Etapa não encontrada.")
    if not step.output_path:
        raise HTTPException(404, "Esta etapa não gerou dados.")

    def _read():
        frame = storage.load_frame(step.output_path)
        if frame is None:
            raise HTTPException(410, "Checkpoint não está mais em disco.")
        return storage.preview(frame, rows)

    return await run_in_threadpool(_read)


@router.get("/{run_id}/notebook")
def download_notebook(run_id: str, session: Session = Depends(get_session)):
    run = _require(session, run_id)
    if not run.notebook_path or not Path(run.notebook_path).exists():
        raise HTTPException(404, "Notebook ainda não foi gerado.")
    return FileResponse(
        run.notebook_path,
        media_type="application/x-ipynb+json",
        filename=Path(run.notebook_path).name,
    )


@router.get("/{run_id}/artifacts")
def list_artifacts(run_id: str, session: Session = Depends(get_session)):
    _require(session, run_id)
    rows = session.scalars(
        select(Artifact).where(Artifact.run_id == run_id).order_by(Artifact.created_at)
    ).all()
    return [
        {
            "id": a.id,
            "kind": a.kind,
            "name": a.name,
            "path": a.path,
            "exists": Path(a.path).exists(),
            "meta": a.meta,
        }
        for a in rows
    ]


# --------------------------------------------------------------------------- #
def _require(session: Session, run_id: str) -> Run:
    run = session.get(Run, run_id)
    if run is None:
        raise HTTPException(404, "Execução não encontrada.")
    return run


def _load_sources(session: Session, ids: list[str]) -> list[DataSource]:
    rows = session.scalars(select(DataSource).where(DataSource.id.in_(ids))).all()
    by_id = {r.id: r for r in rows}
    missing = [i for i in ids if i not in by_id]
    if missing:
        raise HTTPException(404, f"Fonte(s) não encontrada(s): {', '.join(missing)}")
    return [by_id[i] for i in ids]


def _pick_config(session: Session, config_id: str | None) -> AIConfig | None:
    if config_id:
        config = session.get(AIConfig, config_id)
        if config is None:
            raise HTTPException(404, "Configuração de IA não encontrada.")
        return config
    return session.scalar(select(AIConfig).where(AIConfig.is_default.is_(True)))


def _detail(session: Session, run: Run) -> RunDetailOut:
    session.refresh(run)
    data = RunDetailOut.model_validate(run)
    data.is_running = runner.is_running(run.id)
    data.sources = [
        DataSourceOut.model_validate(s)
        for s in session.scalars(
            select(DataSource).where(DataSource.id.in_(run.source_ids or []))
        ).all()
    ]
    return data
