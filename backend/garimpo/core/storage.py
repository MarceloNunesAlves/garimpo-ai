"""Checkpoints em disco: o resultado de cada etapa vira um arquivo.

É isso que permite retomar de onde parou — o runner não guarda dataframe em
memória entre execuções, ele relê o checkpoint da última etapa concluída.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from garimpo.config import settings


def step_dir(run_id: str) -> Path:
    path = settings.run_dir(run_id) / "steps"
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_frame(run_id: str, position: int, agent: str, df: pd.DataFrame) -> str:
    """Grava o dataframe. Parquet quando possível, pickle quando o schema resiste."""
    base = step_dir(run_id) / f"{position:02d}_{agent}"
    try:
        target = base.with_suffix(".parquet")
        df.to_parquet(target, index=True)
    except Exception:
        target = base.with_suffix(".pkl")
        df.to_pickle(target)
    return str(target)


def load_frame(path: str | None) -> pd.DataFrame | None:
    if not path:
        return None
    file = Path(path)
    if not file.exists():
        return None
    if file.suffix == ".parquet":
        return pd.read_parquet(file)
    return pd.read_pickle(file)


def preview(df: pd.DataFrame, rows: int = 25) -> dict:
    """Amostra serializável para a UI."""
    head = df.head(rows)
    records = head.astype(object).where(head.notna(), None).to_dict("records")
    return {
        "columns": [str(c) for c in df.columns],
        "dtypes": {str(c): str(t) for c, t in df.dtypes.items()},
        "rows": [{str(k): _scalar(v) for k, v in r.items()} for r in records],
        "total_rows": int(len(df)),
        "total_columns": int(df.shape[1]),
    }


def _scalar(value):
    import numpy as np

    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
