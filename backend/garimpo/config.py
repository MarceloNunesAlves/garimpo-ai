"""
Configurações do Garimpo.ai.

A única coisa realmente obrigatória é o diretório de trabalho: o banco SQLite é
criado ali no start se nenhum `GARIMPO_DATABASE_URL` for informado. Para usar
Postgres basta exportar a URL:

    export GARIMPO_DATABASE_URL=postgresql+psycopg://user:pass@host:5432/garimpo
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_home() -> Path:
    return Path(os.environ.get("GARIMPO_HOME", Path.home() / ".garimpo-ai")).expanduser()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="GARIMPO_", env_file=".env", extra="ignore"
    )

    # Diretório onde ficam banco SQLite, checkpoints das etapas e notebooks.
    # Nenhum dado de origem é copiado para cá — só resultados intermediários.
    home: Path = Field(default_factory=_default_home)

    # Vazio => SQLite em {home}/garimpo.db, criado automaticamente no start.
    database_url: str = ""

    # Diretórios que o navegador de arquivos da UI pode enxergar.
    # Vazio => qualquer caminho legível pelo processo (modo desktop/local).
    allowed_roots: str = ""

    cors_origins: str = "http://localhost:4200,http://127.0.0.1:4200"

    # Limite de linhas lidas por fonte de dados (0 = sem limite).
    max_rows_per_source: int = 0

    # Tentativas de auto-correção de código por etapa de agente.
    max_retries_per_step: int = 3

    @property
    def workspace(self) -> Path:
        return self.home / "workspace"

    @property
    def runs_dir(self) -> Path:
        return self.workspace / "runs"

    @property
    def sqlalchemy_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{self.home / 'garimpo.db'}"

    @property
    def is_sqlite(self) -> bool:
        return self.sqlalchemy_url.startswith("sqlite")

    def allowed_root_paths(self) -> list[Path]:
        roots = [r.strip() for r in self.allowed_roots.split(",") if r.strip()]
        return [Path(r).expanduser().resolve() for r in roots]

    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def run_dir(self, run_id: str) -> Path:
        return self.runs_dir / run_id

    def ensure_dirs(self) -> None:
        self.home.mkdir(parents=True, exist_ok=True)
        self.runs_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
