"""Garimpo.ai — API.

Sobe com `uvicorn garimpo.main:app --reload`. No start: cria o diretório de
trabalho, o banco (SQLite se nada for configurado) e as tabelas.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from garimpo.api import ai_configs, runs, sources
from garimpo.config import settings
from garimpo.db.session import init_db

DESCRIPTION = """
Garimpo.ai orquestra um time de agentes de dados com o processo visível:
checklist antes de executar, explicação do que cada agente fez, checkpoint por
etapa e um notebook reprodutível no final.
"""


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Garimpo.ai",
    description=DESCRIPTION,
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ai_configs.router)
app.include_router(sources.router)
app.include_router(runs.router)


@app.get("/api/health", tags=["sistema"])
def health() -> dict:
    return {
        "status": "ok",
        "database": "sqlite" if settings.is_sqlite else "postgres",
        "home": str(settings.home),
        "allowed_roots": [str(p) for p in settings.allowed_root_paths()] or ["*"],
    }
