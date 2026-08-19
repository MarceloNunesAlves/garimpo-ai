"""Explicabilidade: o que o agente fez com os dados e por quê.

A explicação é montada em duas camadas:

1. **Fatos** — um diff determinístico entre o dataframe antes e depois. Colunas
   removidas, colunas criadas, mudanças de tipo, quais células vazias foram
   preenchidas e com qual valor, quantas linhas sumiram. Nada disso depende do
   LLM, então não tem como "alucinar".
2. **Narrativa** — um parágrafo curto que o LLM escreve *a partir* dos fatos e
   do código gerado, para o usuário que não quer ler tabela.
"""

from __future__ import annotations

import re
from typing import Any

import numpy as np
import pandas as pd

HIGH_MISSING = 0.4  # mesmo limite que o agente de limpeza usa por padrão


def _py(value: Any) -> Any:
    """Converte tipos numpy/pandas para algo serializável em JSON."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return round(float(value), 6)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if isinstance(value, (np.ndarray, list, tuple)):
        return [_py(v) for v in value]
    return value


def _column_stats(series: pd.Series) -> dict[str, Any]:
    total = len(series)
    missing = int(series.isna().sum())
    stats: dict[str, Any] = {
        "dtype": str(series.dtype),
        "missing": missing,
        "missing_pct": round(missing / total, 4) if total else 0.0,
        "n_unique": int(series.nunique(dropna=True)),
    }
    if pd.api.types.is_numeric_dtype(series) and series.notna().any():
        stats.update(
            mean=_py(series.mean()),
            median=_py(series.median()),
            std=_py(series.std()),
            min=_py(series.min()),
            max=_py(series.max()),
        )
    else:
        mode = series.mode(dropna=True)
        stats["mode"] = _py(mode.iloc[0]) if not mode.empty else None
    return stats


def _drop_reason(name: str, stats: dict[str, Any], rows: int, code: str) -> str:
    """Motivo mais provável da remoção, na ordem em que os agentes decidem."""
    if stats["missing_pct"] >= HIGH_MISSING:
        return (
            f"{stats['missing_pct']:.0%} dos valores estavam ausentes "
            f"(acima do limite de {HIGH_MISSING:.0%})"
        )
    if stats["n_unique"] <= 1:
        return "coluna constante — o mesmo valor em todas as linhas, sem poder explicativo"
    if rows and stats["n_unique"] == rows and stats["missing"] == 0:
        return "valor único por linha (identificador), não generaliza para o modelo"
    if re.search(rf"\b(drop|remove).{{0,80}}{re.escape(str(name))}", code or "", re.I | re.S):
        return "removida explicitamente pelo código gerado pelo agente"
    return "removida pelo agente durante a transformação (ver código da etapa)"


def _guess_fill_strategy(
    before: pd.Series, filled_values: pd.Series
) -> tuple[str, Any]:
    """Compara os valores usados no preenchimento com as estatísticas originais."""
    uniques = filled_values.dropna().unique()
    if len(uniques) == 0:
        return "desconhecida", None
    if len(uniques) == 1:
        value = _py(uniques[0])
        if pd.api.types.is_numeric_dtype(before) and before.notna().any():
            for label, ref in (
                ("média", before.mean()),
                ("mediana", before.median()),
                ("zero", 0),
            ):
                if ref is not None and np.isclose(
                    float(uniques[0]), float(ref), rtol=1e-3, atol=1e-6
                ):
                    return label, value
        else:
            mode = before.mode(dropna=True)
            if not mode.empty and uniques[0] == mode.iloc[0]:
                return "moda (valor mais frequente)", value
        return "valor constante", value
    return "valor derivado por linha (interpolação/ffill/grupo)", _py(uniques[0])


def diff_dataframes(
    before: pd.DataFrame | None,
    after: pd.DataFrame | None,
    code: str = "",
) -> dict[str, Any]:
    """Diff determinístico entre o dado que entrou e o que saiu da etapa."""
    if after is None:
        return {}
    if before is None:
        # Etapa de carga: não há "antes", então listar tudo como coluna criada
        # só faria barulho. O que interessa é o formato e os tipos que entraram.
        return {
            "shape_before": None,
            "shape_after": [int(after.shape[0]), int(after.shape[1])],
            "columns_removed": [],
            "columns_added": [],
            "columns_changed": [],
            "imputations": [],
            "rows": {"after": int(len(after))},
            "loaded_columns": {str(c): str(after[c].dtype) for c in after.columns},
            "notes": ["Etapa de carga: não há dataframe anterior para comparar."],
        }

    before_cols = list(before.columns)
    after_cols = list(after.columns)
    removed = [c for c in before_cols if c not in after_cols]
    added = [c for c in after_cols if c not in before_cols]
    kept = [c for c in before_cols if c in after_cols]

    rows_before, rows_after = int(len(before)), int(len(after))

    columns_removed = []
    for col in removed:
        stats = _column_stats(before[col])
        columns_removed.append(
            {
                "column": str(col),
                "reason": _drop_reason(col, stats, rows_before, code),
                **stats,
            }
        )

    columns_added = []
    for col in added:
        stats = _column_stats(after[col])
        sample = after[col].dropna().head(3).tolist()
        # Heurística de origem: nome novo que contém o nome de uma coluna antiga.
        parents = [
            str(c)
            for c in before_cols
            if len(str(c)) > 2 and str(c).lower() in str(col).lower()
        ]
        columns_added.append(
            {
                "column": str(col),
                "derived_from": parents,
                "sample_values": [_py(v) for v in sample],
                **stats,
            }
        )

    columns_changed = []
    imputations = []
    common_index = before.index.intersection(after.index)
    aligned = len(common_index) > 0

    for col in kept:
        b, a = before[col], after[col]
        before_stats, after_stats = _column_stats(b), _column_stats(a)

        if before_stats["dtype"] != after_stats["dtype"]:
            columns_changed.append(
                {
                    "column": str(col),
                    "change": "tipo",
                    "from": before_stats["dtype"],
                    "to": after_stats["dtype"],
                    "reason": "conversão de tipo para permitir operações numéricas/temporais",
                }
            )

        # Imputação: células que estavam vazias e passaram a ter valor.
        if before_stats["missing"] == 0:
            continue

        if aligned:
            b_idx, a_idx = b.loc[common_index], a.loc[common_index]
            mask = b_idx.isna() & a_idx.notna()
            filled_count = int(mask.sum())
            filled_values = a_idx[mask]
        else:
            # Índices reconstruídos: cai para a diferença de contagem de nulos.
            filled_count = max(before_stats["missing"] - after_stats["missing"], 0)
            filled_values = a.dropna()

        if filled_count <= 0:
            continue

        strategy, value = _guess_fill_strategy(b, filled_values)
        imputations.append(
            {
                "column": str(col),
                "filled": filled_count,
                "filled_pct": round(filled_count / rows_before, 4) if rows_before else 0,
                "strategy": strategy,
                "value": value,
                "exact": aligned,
                "reason": (
                    f"{filled_count} valores ausentes preenchidos usando {strategy}"
                    + (f" (= {value})" if value is not None else "")
                    + f"; a coluna tinha {before_stats['missing_pct']:.1%} de vazios, "
                    "abaixo do limite de descarte, então foi mantida e imputada"
                ),
                "stats_before": before_stats,
            }
        )

    rows_info: dict[str, Any] = {
        "before": rows_before,
        "after": rows_after,
        "removed": max(rows_before - rows_after, 0),
        "added": max(rows_after - rows_before, 0),
    }
    if rows_info["removed"]:
        rows_info["removed_pct"] = round(rows_info["removed"] / rows_before, 4)
        reasons = []
        try:
            dups = int(before.duplicated().sum())
            if dups:
                reasons.append(f"{dups} linhas duplicadas no dado de entrada")
        except TypeError:
            pass  # colunas não-hasháveis
        if re.search(r"dropna|drop_duplicates|outlier|quantile|iqr", code or "", re.I):
            hits = sorted(
                set(
                    m.lower()
                    for m in re.findall(
                        r"dropna|drop_duplicates|outlier|quantile|iqr", code or "", re.I
                    )
                )
            )
            reasons.append(f"o código aplica: {', '.join(hits)}")
        rows_info["reasons"] = reasons

    return {
        "shape_before": [rows_before, len(before_cols)],
        "shape_after": [rows_after, len(after_cols)],
        "columns_removed": columns_removed,
        "columns_added": columns_added,
        "columns_changed": columns_changed,
        "imputations": imputations,
        "rows": rows_info,
        "index_aligned": aligned,
    }


def headline(diff: dict[str, Any]) -> str:
    """Resumo de uma linha para o topo do cartão na UI."""
    if not diff:
        return "Sem alterações registradas."
    if diff.get("loaded_columns") is not None:
        shape = diff.get("shape_after") or [0, 0]
        return f"{shape[0]} linhas e {shape[1]} colunas carregadas das fontes."
    parts = []
    removed = len(diff.get("columns_removed") or [])
    added = len(diff.get("columns_added") or [])
    imputed = len(diff.get("imputations") or [])
    rows_removed = (diff.get("rows") or {}).get("removed") or 0
    if removed:
        parts.append(f"{removed} coluna(s) removida(s)")
    if added:
        parts.append(f"{added} coluna(s) criada(s)")
    if imputed:
        parts.append(f"{imputed} coluna(s) imputada(s)")
    if rows_removed:
        parts.append(f"{rows_removed} linha(s) descartada(s)")
    return "; ".join(parts) if parts else "Estrutura preservada."


NARRATIVE_PROMPT = """Você é o narrador do Garimpo.ai. Explique, para uma pessoa de negócio,
o que este agente de dados acabou de fazer.

Etapa: {title} (agente: {agent})
Objetivo do projeto: {objective}

Fatos medidos no dataframe (não invente nada além disto):
{facts}

Trecho do código gerado pelo agente:
```python
{code}
```

Escreva em português do Brasil, 2 a 4 frases, sem markdown, sem bullet points.
Cite números concretos dos fatos. Se colunas foram removidas ou preenchidas,
diga explicitamente quais e por quê. Não invente motivos que os fatos não sustentem."""


def narrate(llm, *, title: str, agent: str, objective: str, diff: dict, code: str) -> str:
    """Narrativa opcional. Falha em silêncio: os fatos já bastam para a UI."""
    if llm is None or not diff:
        return ""
    import json

    try:
        facts = json.dumps(diff, ensure_ascii=False, indent=2, default=str)[:6000]
        resp = llm.invoke(
            NARRATIVE_PROMPT.format(
                title=title,
                agent=agent,
                objective=objective or "(não informado)",
                facts=facts,
                code=(code or "(sem código)")[:4000],
            )
        )
        text = getattr(resp, "content", resp)
        if isinstance(text, list):
            text = " ".join(b.get("text", "") for b in text if isinstance(b, dict))
        return str(text).strip()
    except Exception:
        return ""
