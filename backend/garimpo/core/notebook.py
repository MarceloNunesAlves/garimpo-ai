"""Geração do notebook reprodutível.

O notebook é a entrega final: o usuário abre no Jupyter, roda de cima a baixo e
chega no mesmo resultado — lendo os arquivos originais direto do caminho, sem
depender do Garimpo. Cada etapa vira markdown (o que foi feito e por quê) mais
o código que o agente gerou.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import nbformat as nbf
from sqlalchemy import select
from sqlalchemy.orm import Session

from garimpo.config import settings
from garimpo.core.steps import LABELS
from garimpo.db.models import ChecklistItem, Run, RunStep, StepStatus

HELPERS = '''
def load_directory(path, recursive=False):
    """Lê todos os arquivos tabulares de um diretório e concatena."""
    import pandas as pd
    from pathlib import Path

    readers = {
        ".csv": pd.read_csv,
        ".tsv": lambda p: pd.read_csv(p, sep="\\t"),
        ".parquet": pd.read_parquet,
        ".json": pd.read_json,
        ".jsonl": lambda p: pd.read_json(p, lines=True),
        ".xlsx": pd.read_excel,
        ".xls": pd.read_excel,
    }
    root = Path(path)
    files = sorted(root.rglob("*") if recursive else root.glob("*"))
    frames = []
    for f in files:
        reader = readers.get(f.suffix.lower())
        if f.is_file() and reader is not None:
            part = reader(f)
            part["__source_file__"] = f.name
            frames.append(part)
    if not frames:
        raise FileNotFoundError(f"Nenhum arquivo tabular em {path}")
    return pd.concat(frames, ignore_index=True)
'''


def build_notebook(session: Session, run: Run) -> Path:
    nb = nbf.v4.new_notebook()
    cells: list[Any] = []

    steps_done = session.scalars(
        select(RunStep)
        .where(RunStep.run_id == run.id, RunStep.status == StepStatus.DONE)
        .order_by(RunStep.position, RunStep.started_at)
    ).all()
    # Uma etapa pode ter mais de uma tentativa: fica a última concluída.
    by_position: dict[int, RunStep] = {}
    for step in steps_done:
        by_position[step.position] = step
    ordered = [by_position[k] for k in sorted(by_position)]

    items = session.scalars(
        select(ChecklistItem)
        .where(ChecklistItem.run_id == run.id)
        .order_by(ChecklistItem.position)
    ).all()

    cells.append(nbf.v4.new_markdown_cell(_header(run, items)))
    cells.append(nbf.v4.new_code_cell(_setup_code(ordered)))

    for step in ordered:
        item = next((i for i in items if i.id == step.item_id), None)
        title = item.title if item else LABELS.get(step.agent, step.agent)
        cells.append(nbf.v4.new_markdown_cell(_step_markdown(step, title, item)))
        if step.code:
            cells.append(nbf.v4.new_code_cell(step.code.strip()))
        call = (step.explanation or {}).get("call")
        if call:
            cells.append(nbf.v4.new_code_cell(f"{call}\ndf.head()"))

    cells.append(nbf.v4.new_markdown_cell(_footer(run)))
    cells.append(
        nbf.v4.new_code_cell(
            "df.info()\n"
            "print(f'Resultado final: {df.shape[0]} linhas x {df.shape[1]} colunas')\n"
            "df.head(20)"
        )
    )

    nb["cells"] = cells
    nb["metadata"] = {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        },
        "language_info": {"name": "python"},
        "garimpo": {
            "run_id": run.id,
            "objective": run.objective,
            "checklist_revision": run.checklist_revision,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    }

    target = settings.run_dir(run.id)
    target.mkdir(parents=True, exist_ok=True)
    path = target / f"garimpo_{_slug(run.title)}.ipynb"
    with path.open("w", encoding="utf-8") as fh:
        nbf.write(nb, fh)
    return path


# --------------------------------------------------------------------------- #
def _header(run: Run, items: list[ChecklistItem]) -> str:
    lines = [
        f"# {run.title}",
        "",
        f"> Gerado pelo **Garimpo.ai** em {datetime.now().strftime('%d/%m/%Y %H:%M')}.",
        "",
        "## Objetivo",
        "",
        run.objective or "_(não informado)_",
        "",
        f"## Checklist executado (revisão {run.checklist_revision})",
        "",
        "| # | Etapa | Agente | Status | Origem |",
        "| - | ----- | ------ | ------ | ------ |",
    ]
    for item in items:
        origin = {
            "planner": "plano inicial",
            "revision": "revisado durante a execução",
            "user": "definido pelo usuário",
        }.get(item.origin, item.origin)
        lines.append(
            f"| {item.position + 1} | {item.title} | `{item.agent}` | {item.status} | {origin} |"
        )

    revised = [i for i in items if i.origin == "revision" and i.rationale]
    if revised:
        lines += ["", "**Ajustes feitos no meio do caminho:**", ""]
        seen = set()
        for item in revised:
            if item.rationale in seen:
                continue
            seen.add(item.rationale)
            lines.append(f"- {item.rationale}")

    if run.target_variable:
        lines += ["", f"**Variável-alvo:** `{run.target_variable}`"]

    lines += [
        "",
        "---",
        "",
        "Os dados são lidos direto do caminho original — nada foi copiado.",
    ]
    return "\n".join(lines)


def _setup_code(steps: list[RunStep]) -> str:
    imports: list[str] = []
    for step in steps:
        for line in (step.explanation or {}).get("imports", []) or []:
            if line not in imports:
                imports.append(line)
    if "import pandas as pd" not in imports:
        imports.insert(0, "import pandas as pd")
    body = "\n".join(imports)
    return f"{body}\n\npd.set_option('display.max_columns', 200)\n\n{HELPERS.strip()}"


def _step_markdown(step: RunStep, title: str, item: ChecklistItem | None) -> str:
    explanation = step.explanation or {}
    diff = explanation.get("diff") or {}
    label = LABELS.get(step.agent, step.agent)

    lines = [f"## {step.position + 1}. {title}", "", f"**Agente:** `{step.agent}` ({label})"]
    if item and item.instructions:
        lines += ["", f"**Instrução dada ao agente:** {item.instructions}"]
    if explanation.get("narrative"):
        lines += ["", explanation["narrative"]]
    elif step.summary:
        lines += ["", step.summary.strip()]

    removed = diff.get("columns_removed") or []
    if removed:
        lines += [
            "",
            "**Colunas removidas e o motivo:**",
            "",
            "| Coluna | Ausentes | Valores distintos | Motivo |",
            "| ------ | -------- | ----------------- | ------ |",
        ]
        for col in removed:
            lines.append(
                f"| `{col['column']}` | {col.get('missing_pct', 0):.1%} | "
                f"{col.get('n_unique', '-')} | {col.get('reason', '-')} |"
            )

    imputations = diff.get("imputations") or []
    if imputations:
        lines += [
            "",
            "**Preenchimento de valores ausentes:**",
            "",
            "| Coluna | Células preenchidas | Estratégia | Valor |",
            "| ------ | ------------------- | ---------- | ----- |",
        ]
        for imp in imputations:
            lines.append(
                f"| `{imp['column']}` | {imp['filled']} ({imp.get('filled_pct', 0):.1%}) | "
                f"{imp.get('strategy', '-')} | `{imp.get('value')}` |"
            )

    loaded = diff.get("loaded_columns") or {}
    if loaded:
        lines += [
            "",
            f"**Colunas carregadas ({len(loaded)}):** "
            + ", ".join(f"`{name}` ({dtype})" for name, dtype in list(loaded.items())[:40]),
        ]

    added = diff.get("columns_added") or []
    if added:
        lines += ["", "**Colunas criadas:** " + ", ".join(f"`{c['column']}`" for c in added)]

    rows = diff.get("rows") or {}
    if rows.get("removed"):
        reasons = "; ".join(rows.get("reasons") or []) or "ver código da etapa"
        lines += [
            "",
            f"**Linhas descartadas:** {rows['removed']} de {rows.get('before')} "
            f"({rows.get('removed_pct', 0):.1%}) — {reasons}",
        ]

    eda = (explanation.get("extra") or {}).get("eda")
    if eda:
        lines += ["", f"**Perfil:** {eda['shape'][0]} linhas x {eda['shape'][1]} colunas."]
        top = eda.get("top_correlations") or []
        if top:
            lines.append("")
            lines.append("Correlações mais fortes: " + ", ".join(
                f"`{c['a']}`×`{c['b']}` = {c['corr']}" for c in top[:5]
            ))

    return "\n".join(lines)


def _footer(run: Run) -> str:
    return "\n".join(
        [
            "---",
            "",
            "## Resultado",
            "",
            "As células acima reproduzem, na ordem, o que o time de agentes fez. "
            "Para rodar com dados novos, troque os caminhos na célula de carga e "
            "execute o notebook inteiro.",
            "",
            f"Run: `{run.id}`",
        ]
    )


def _slug(text: str) -> str:
    import re
    import unicodedata

    normalized = unicodedata.normalize("NFKD", text or "run")
    ascii_text = normalized.encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", ascii_text).strip("_").lower()
    return slug[:60] or "run"
