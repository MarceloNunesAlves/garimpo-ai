"""Fontes de dados por caminho.

O Garimpo nunca copia o arquivo do usuário: guarda o path e lê sob demanda.
Isso mantém o consumo de disco praticamente zero e evita duplicação.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from garimpo.config import settings

TABULAR_SUFFIXES = {
    ".csv": "csv",
    ".tsv": "tsv",
    ".txt": "csv",
    ".parquet": "parquet",
    ".pq": "parquet",
    ".json": "json",
    ".jsonl": "jsonl",
    ".ndjson": "jsonl",
    ".xlsx": "excel",
    ".xls": "excel",
}


class PathNotAllowed(PermissionError):
    pass


def resolve_path(raw: str) -> Path:
    """Normaliza e valida o caminho contra `GARIMPO_ALLOWED_ROOTS`."""
    path = Path(raw).expanduser().resolve()
    roots = settings.allowed_root_paths()
    if roots and not any(path == r or r in path.parents for r in roots):
        raise PathNotAllowed(
            f"Caminho fora dos diretórios permitidos: {path}. "
            f"Permitidos: {', '.join(str(r) for r in roots)}"
        )
    return path


def detect_format(path: Path) -> str | None:
    return TABULAR_SUFFIXES.get(path.suffix.lower())


@dataclass
class BrowseEntry:
    name: str
    path: str
    is_dir: bool
    size: int | None
    fmt: str | None
    modified: float | None


def browse(raw_path: str | None = None, show_hidden: bool = False) -> dict[str, Any]:
    """Lista um diretório para o seletor de caminhos da UI."""
    target = resolve_path(raw_path) if raw_path else Path.home()
    if not target.exists():
        raise FileNotFoundError(f"Caminho inexistente: {target}")
    if target.is_file():
        target = target.parent

    entries: list[BrowseEntry] = []
    for child in sorted(
        target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())
    ):
        if not show_hidden and child.name.startswith("."):
            continue
        try:
            stat = child.stat()
        except OSError:
            continue
        is_dir = child.is_dir()
        fmt = None if is_dir else detect_format(child)
        if not is_dir and fmt is None:
            continue  # só mostra o que dá para ler
        entries.append(
            BrowseEntry(
                name=child.name,
                path=str(child),
                is_dir=is_dir,
                size=None if is_dir else stat.st_size,
                fmt=fmt,
                modified=stat.st_mtime,
            )
        )

    parent = str(target.parent) if target.parent != target else None
    return {
        "path": str(target),
        "parent": parent,
        "entries": [e.__dict__ for e in entries],
    }


def list_tabular_files(path: Path, recursive: bool = False) -> list[Path]:
    if path.is_file():
        return [path]
    pattern = "**/*" if recursive else "*"
    return sorted(
        p for p in path.glob(pattern) if p.is_file() and detect_format(p) is not None
    )


def _read_one(path: Path, fmt: str | None, options: dict[str, Any], nrows: int | None):
    fmt = fmt or detect_format(path)
    opts = dict(options or {})
    if fmt == "csv":
        return pd.read_csv(path, nrows=nrows, sep=opts.get("sep", ","), **_clean(opts))
    if fmt == "tsv":
        return pd.read_csv(path, nrows=nrows, sep=opts.get("sep", "\t"), **_clean(opts))
    if fmt == "parquet":
        df = pd.read_parquet(path)
        return df.head(nrows) if nrows else df
    if fmt == "json":
        df = pd.read_json(path)
        return df.head(nrows) if nrows else df
    if fmt == "jsonl":
        return pd.read_json(path, lines=True, nrows=nrows)
    if fmt == "excel":
        return pd.read_excel(path, nrows=nrows, sheet_name=opts.get("sheet_name", 0))
    raise ValueError(f"Formato não suportado para {path.name}")


def _clean(opts: dict[str, Any]) -> dict[str, Any]:
    """Repassa apenas opções conhecidas do pandas."""
    allowed = {"encoding", "decimal", "thousands", "header", "na_values", "dtype"}
    return {k: v for k, v in opts.items() if k in allowed}


def load_dataframe(
    path_str: str,
    kind: str = "file",
    fmt: str | None = None,
    options: dict[str, Any] | None = None,
    nrows: int | None = None,
) -> pd.DataFrame:
    """Carrega uma fonte (arquivo ou diretório) em um DataFrame.

    Diretórios são concatenados; a coluna `__source_file__` registra a origem
    de cada linha para que a explicação e o notebook fiquem rastreáveis.
    """
    path = resolve_path(path_str)
    options = options or {}
    limit = nrows or (settings.max_rows_per_source or None)

    if kind == "directory" or path.is_dir():
        files = list_tabular_files(path, recursive=bool(options.get("recursive")))
        if not files:
            raise FileNotFoundError(f"Nenhum arquivo tabular em {path}")
        frames = []
        for f in files:
            part = _read_one(f, fmt, options, limit)
            part["__source_file__"] = f.name
            frames.append(part)
        return pd.concat(frames, ignore_index=True)

    return _read_one(path, fmt, options, limit)


def profile_source(
    path_str: str, kind: str, fmt: str | None, options: dict[str, Any] | None
) -> dict[str, Any]:
    """Amostra leve para exibir na UI (não carrega o arquivo inteiro)."""
    path = resolve_path(path_str)
    try:
        sample = load_dataframe(path_str, kind, fmt, options, nrows=200)
    except Exception as exc:  # a UI mostra o erro em vez de quebrar
        return {"error": str(exc)}

    files = list_tabular_files(path, recursive=bool((options or {}).get("recursive")))
    return {
        "columns": [str(c) for c in sample.columns],
        "dtypes": {str(c): str(t) for c, t in sample.dtypes.items()},
        "sample_rows": int(len(sample)),
        "files": len(files),
        "bytes": sum(f.stat().st_size for f in files if f.exists()),
        "preview": sample.head(10).astype(object).where(sample.head(10).notna(), None).to_dict("records"),
    }


def load_sources(sources: list[dict[str, Any]]) -> dict[str, pd.DataFrame]:
    """Carrega todas as fontes de um run: {nome: DataFrame}."""
    out: dict[str, pd.DataFrame] = {}
    for src in sources:
        df = load_dataframe(
            src["path"], src.get("kind", "file"), src.get("fmt"), src.get("options")
        )
        name = src.get("name") or Path(src["path"]).stem
        base, i = name, 2
        while name in out:
            name, i = f"{base}_{i}", i + 1
        out[name] = df
    return out
