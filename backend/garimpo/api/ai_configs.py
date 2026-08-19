from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from garimpo.core.llm import MODEL_CHOICES, PROVIDERS, check_llm
from garimpo.db.models import AIConfig, new_id
from garimpo.db.session import get_session
from garimpo.schemas import AIConfigIn, AIConfigOut

router = APIRouter(prefix="/api/ai-configs", tags=["ia"])


def _out(config: AIConfig) -> AIConfigOut:
    data = AIConfigOut.model_validate(config)
    data.has_api_key = bool(config.api_key)
    return data


@router.get("/providers")
def providers() -> dict:
    return {"providers": list(PROVIDERS), "models": MODEL_CHOICES}


@router.get("", response_model=list[AIConfigOut])
def list_configs(session: Session = Depends(get_session)):
    rows = session.scalars(select(AIConfig).order_by(AIConfig.created_at.desc())).all()
    return [_out(r) for r in rows]


@router.post("", response_model=AIConfigOut, status_code=201)
def create_config(payload: AIConfigIn, session: Session = Depends(get_session)):
    if session.scalar(select(AIConfig).where(AIConfig.name == payload.name)):
        raise HTTPException(409, "Já existe uma configuração com esse nome.")
    config = AIConfig(id=new_id(), **payload.model_dump())
    session.add(config)
    _apply_default(session, config)
    session.commit()
    return _out(config)


@router.put("/{config_id}", response_model=AIConfigOut)
def update_config(
    config_id: str, payload: AIConfigIn, session: Session = Depends(get_session)
):
    config = session.get(AIConfig, config_id)
    if config is None:
        raise HTTPException(404, "Configuração não encontrada.")
    data = payload.model_dump()
    # Campo em branco mantém a chave já salva (a UI nunca recebe a chave de volta).
    if not data.get("api_key"):
        data.pop("api_key", None)
    for key, value in data.items():
        setattr(config, key, value)
    _apply_default(session, config)
    session.commit()
    return _out(config)


@router.delete("/{config_id}", status_code=204)
def delete_config(config_id: str, session: Session = Depends(get_session)):
    config = session.get(AIConfig, config_id)
    if config is None:
        raise HTTPException(404, "Configuração não encontrada.")
    session.delete(config)
    session.commit()


@router.post("/{config_id}/test")
async def test_config(config_id: str, session: Session = Depends(get_session)):
    config = session.get(AIConfig, config_id)
    if config is None:
        raise HTTPException(404, "Configuração não encontrada.")
    return await run_in_threadpool(check_llm, config)


def _apply_default(session: Session, config: AIConfig) -> None:
    """Garante que só exista um default."""
    if not config.is_default:
        return
    for other in session.scalars(select(AIConfig)).all():
        if other.id != config.id:
            other.is_default = False
