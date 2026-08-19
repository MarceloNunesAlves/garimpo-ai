from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from garimpo.core import datasources
from garimpo.db.models import DataSource, new_id
from garimpo.db.session import get_session
from garimpo.schemas import BrowseOut, DataSourceIn, DataSourceOut

router = APIRouter(prefix="/api/sources", tags=["fontes"])


@router.get("/browse", response_model=BrowseOut)
async def browse(
    path: str | None = Query(default=None),
    show_hidden: bool = Query(default=False),
):
    """Navegador de arquivos do servidor — a seleção guarda só o caminho."""
    try:
        return await run_in_threadpool(datasources.browse, path, show_hidden)
    except datasources.PathNotAllowed as exc:
        raise HTTPException(403, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(403, f"Sem permissão de leitura: {exc}") from exc


@router.get("", response_model=list[DataSourceOut])
def list_sources(session: Session = Depends(get_session)):
    return session.scalars(select(DataSource).order_by(DataSource.created_at.desc())).all()


@router.post("", response_model=DataSourceOut, status_code=201)
async def create_source(payload: DataSourceIn, session: Session = Depends(get_session)):
    try:
        resolved = datasources.resolve_path(payload.path)
    except datasources.PathNotAllowed as exc:
        raise HTTPException(403, str(exc)) from exc
    if not resolved.exists():
        raise HTTPException(404, f"Caminho inexistente: {resolved}")

    kind = "directory" if resolved.is_dir() else "file"
    fmt = payload.fmt or (None if kind == "directory" else datasources.detect_format(resolved))
    if kind == "file" and fmt is None:
        raise HTTPException(400, f"Formato não suportado: {resolved.suffix}")

    profile = await run_in_threadpool(
        datasources.profile_source, str(resolved), kind, fmt, payload.options
    )
    source = DataSource(
        id=new_id(),
        name=payload.name or resolved.name or Path(payload.path).name,
        kind=kind,
        path=str(resolved),
        fmt=fmt,
        options=payload.options,
        profile=profile,
    )
    session.add(source)
    session.commit()
    return source


@router.post("/preview")
async def preview(payload: DataSourceIn):
    """Espia o conteúdo antes de salvar a fonte."""
    try:
        resolved = datasources.resolve_path(payload.path)
    except datasources.PathNotAllowed as exc:
        raise HTTPException(403, str(exc)) from exc
    if not resolved.exists():
        raise HTTPException(404, f"Caminho inexistente: {resolved}")
    kind = "directory" if resolved.is_dir() else "file"
    return await run_in_threadpool(
        datasources.profile_source, str(resolved), kind, payload.fmt, payload.options
    )


@router.delete("/{source_id}", status_code=204)
def delete_source(source_id: str, session: Session = Depends(get_session)):
    source = session.get(DataSource, source_id)
    if source is None:
        raise HTTPException(404, "Fonte não encontrada.")
    # Remove apenas o registro: o arquivo do usuário nunca foi copiado nem é tocado.
    session.delete(source)
    session.commit()
