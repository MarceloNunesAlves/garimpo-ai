"""Adaptadores dos agentes de `garimpo.agents` para o formato do Garimpo.

Cada etapa devolve um `StepResult` uniforme: o dataframe resultante, o código
que produziu esse resultado (é ele que vai para o notebook final) e um resumo.
O runner não precisa saber qual agente rodou.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from garimpo.core import datasources


@dataclass
class StepContext:
    run_id: str
    objective: str
    instructions: str
    target_variable: str | None
    llm: Any
    sources: list[dict[str, Any]]
    log: Callable[[str, str], None]
    max_retries: int = 3


@dataclass
class StepResult:
    dataframe: pd.DataFrame | None = None
    code: str = ""
    call: str = ""  # linha que aplica o código no notebook
    summary: str = ""
    imports: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


class MissingDependency(RuntimeError):
    pass


def _agents():
    # Import tardio: langgraph/langchain só entram em cena quando uma etapa de
    # agente roda de fato — a API sobe sem eles.
    try:
        import garimpo.agents as agents  # noqa: WPS433
    except ImportError as exc:  # pragma: no cover - depende do ambiente
        raise MissingDependency(
            "Faltam dependências dos agentes de código "
            f"({exc}). Rode: pip install -r backend/requirements.txt"
        ) from exc
    return agents


def _require_llm(ctx: StepContext) -> Any:
    if ctx.llm is None:
        raise RuntimeError(
            "Esta etapa precisa de um modelo de IA. Configure um provedor em Configurações › IA."
        )
    return ctx.llm


# --------------------------------------------------------------------------- #
# load
# --------------------------------------------------------------------------- #
def step_load(ctx: StepContext, data: pd.DataFrame | None) -> StepResult:
    frames = datasources.load_sources(ctx.sources)
    names = list(frames)
    if not frames:
        raise RuntimeError("Nenhuma fonte de dados selecionada para este garimpo.")

    if len(frames) == 1:
        df = frames[names[0]]
    else:
        # Múltiplas fontes: concatena marcando a origem. O agente de wrangling
        # faz o join de verdade quando o checklist pedir.
        df = pd.concat(
            [f.assign(__dataset__=name) for name, f in frames.items()],
            ignore_index=True,
        )

    lines = ["import pandas as pd", "", "frames = {}"]
    for src in ctx.sources:
        name = src.get("name") or src["path"]
        if src.get("kind") == "directory":
            lines.append(
                f"frames[{name!r}] = load_directory({src['path']!r})  # ver helper abaixo"
            )
        else:
            lines.append(f"frames[{name!r}] = {_reader_call(src)}")
    lines.append("")
    if len(frames) == 1:
        lines.append(f"df = frames[{names[0]!r}]")
    else:
        lines.append(
            "df = pd.concat([f.assign(__dataset__=n) for n, f in frames.items()], ignore_index=True)"
        )

    summary = "; ".join(f"{n}: {f.shape[0]}x{f.shape[1]}" for n, f in frames.items())
    return StepResult(
        dataframe=df,
        code="\n".join(lines),
        summary=f"Fontes carregadas ({summary}). Dataframe consolidado: "
        f"{df.shape[0]} linhas x {df.shape[1]} colunas.",
        imports=["import pandas as pd"],
        extra={"datasets": {n: list(map(str, f.columns)) for n, f in frames.items()}},
    )


def _reader_call(src: dict[str, Any]) -> str:
    fmt = src.get("fmt") or datasources.detect_format(Path(src["path"]))
    path = src["path"]
    readers = {
        "csv": f"pd.read_csv({path!r})",
        "tsv": f"pd.read_csv({path!r}, sep='\\t')",
        "parquet": f"pd.read_parquet({path!r})",
        "json": f"pd.read_json({path!r})",
        "jsonl": f"pd.read_json({path!r}, lines=True)",
        "excel": f"pd.read_excel({path!r})",
    }
    return readers.get(fmt or "csv", f"pd.read_csv({path!r})")


# --------------------------------------------------------------------------- #
# agentes de código (clean / wrangle / feature / viz)
# --------------------------------------------------------------------------- #
def _run_code_agent(
    ctx: StepContext,
    data: pd.DataFrame,
    *,
    agent_cls_name: str,
    function_name: str,
    getter: str,
    code_getter: str,
    invoke_kwargs: dict[str, Any] | None = None,
) -> StepResult:
    llm = _require_llm(ctx)
    agents = _agents()
    agent_cls = getattr(agents, agent_cls_name)

    agent = agent_cls(
        model=llm,
        n_samples=30,
        log=False,
        function_name=function_name,
        human_in_the_loop=False,
        bypass_explain_code=True,
    )
    ctx.log("step.progress", f"{agent_cls_name}: analisando o dataframe e gerando código…")
    agent.invoke_agent(
        data_raw=data,
        user_instructions=ctx.instructions or ctx.objective,
        max_retries=ctx.max_retries,
        retry_count=0,
        **(invoke_kwargs or {}),
    )

    result = getattr(agent, getter)()
    code = getattr(agent, code_getter)() or ""
    recommended = _safe(agent, "get_recommended_cleaning_steps") or _safe(
        agent, "get_recommended_wrangling_steps"
    ) or _safe(agent, "get_recommended_feature_engineering_steps") or _safe(
        agent, "get_recommended_visualization_steps"
    )
    workflow = _safe(agent, "get_workflow_summary") or ""

    return StepResult(
        dataframe=result if isinstance(result, pd.DataFrame) else None,
        code=code,
        call=f"df = {function_name}(df)",
        summary=(workflow or recommended or "").strip(),
        imports=["import pandas as pd"],
        extra={
            "recommended_steps": recommended,
            "plotly_figure": result if not isinstance(result, pd.DataFrame) else None,
        },
    )


def _safe(agent, method: str):
    fn = getattr(agent, method, None)
    if fn is None:
        return None
    try:
        value = fn()
    except Exception:
        return None
    return value if isinstance(value, str) else None


def step_clean(ctx: StepContext, data: pd.DataFrame) -> StepResult:
    return _run_code_agent(
        ctx,
        data,
        agent_cls_name="DataCleaningAgent",
        function_name="data_cleaner",
        getter="get_data_cleaned",
        code_getter="get_data_cleaner_function",
    )


def step_wrangle(ctx: StepContext, data: pd.DataFrame) -> StepResult:
    return _run_code_agent(
        ctx,
        data,
        agent_cls_name="DataWranglingAgent",
        function_name="data_wrangler",
        getter="get_data_wrangled",
        code_getter="get_data_wrangler_function",
    )


def step_feature(ctx: StepContext, data: pd.DataFrame) -> StepResult:
    return _run_code_agent(
        ctx,
        data,
        agent_cls_name="FeatureEngineeringAgent",
        function_name="feature_engineer",
        getter="get_data_engineered",
        code_getter="get_feature_engineer_function",
        invoke_kwargs={"target_variable": ctx.target_variable},
    )


def step_viz(ctx: StepContext, data: pd.DataFrame) -> StepResult:
    result = _run_code_agent(
        ctx,
        data,
        agent_cls_name="DataVisualizationAgent",
        function_name="data_visualization",
        getter="get_plotly_graph",
        code_getter="get_data_visualization_function",
    )
    # Visualização não altera os dados: o dataframe segue igual para a próxima etapa.
    figure = result.extra.get("plotly_figure")
    result.dataframe = data
    result.call = "fig = data_visualization(df)\nfig.show()"
    result.imports = ["import pandas as pd", "import plotly.express as px"]
    result.extra = {
        "recommended_steps": result.extra.get("recommended_steps"),
        "figure": _figure_to_dict(figure),
    }
    if not result.summary:
        result.summary = "Gráfico gerado a partir do dataframe atual."
    return result


def _figure_to_dict(figure: Any) -> dict[str, Any] | None:
    if figure is None:
        return None
    if isinstance(figure, dict):
        return figure
    try:  # objeto plotly.graph_objects.Figure
        import json

        import plotly.io as pio

        return json.loads(pio.to_json(figure))
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# eda — determinístico, sem custo de LLM
# --------------------------------------------------------------------------- #
def step_eda(ctx: StepContext, data: pd.DataFrame) -> StepResult:
    numeric = data.select_dtypes("number")
    missing = data.isna().sum()
    missing_pct = (missing / max(len(data), 1)).round(4)

    report: dict[str, Any] = {
        "shape": [int(data.shape[0]), int(data.shape[1])],
        "dtypes": {str(c): str(t) for c, t in data.dtypes.items()},
        "missing": {
            str(c): {"count": int(missing[c]), "pct": float(missing_pct[c])}
            for c in data.columns
            if missing[c] > 0
        },
        "describe": _jsonable(numeric.describe().round(4).to_dict()) if len(numeric.columns) else {},
        "cardinality": {
            str(c): int(data[c].nunique(dropna=True)) for c in data.columns
        },
    }
    if len(numeric.columns) >= 2:
        corr = numeric.corr(numeric_only=True).round(3)
        pairs = []
        cols = list(corr.columns)
        for i, a in enumerate(cols):
            for b in cols[i + 1 :]:
                value = corr.loc[a, b]
                if pd.notna(value) and abs(value) >= 0.5:
                    pairs.append({"a": str(a), "b": str(b), "corr": float(value)})
        report["top_correlations"] = sorted(
            pairs, key=lambda p: abs(p["corr"]), reverse=True
        )[:15]

    if ctx.target_variable and ctx.target_variable in data.columns:
        target = data[ctx.target_variable]
        report["target"] = {
            "name": ctx.target_variable,
            "dtype": str(target.dtype),
            "missing": int(target.isna().sum()),
            "distribution": _jsonable(
                target.value_counts(dropna=False).head(15).to_dict()
            )
            if target.nunique(dropna=True) <= 30
            else _jsonable(target.describe().round(4).to_dict()),
        }

    highlights = [f"{report['shape'][0]} linhas e {report['shape'][1]} colunas."]
    if report["missing"]:
        worst = max(report["missing"].items(), key=lambda kv: kv[1]["pct"])
        highlights.append(
            f"{len(report['missing'])} colunas com ausentes; a pior é "
            f"'{worst[0]}' com {worst[1]['pct']:.1%}."
        )
    else:
        highlights.append("Nenhum valor ausente.")
    if report.get("top_correlations"):
        top = report["top_correlations"][0]
        highlights.append(
            f"Correlação mais forte: {top['a']} × {top['b']} = {top['corr']}."
        )

    code = (
        "# Análise exploratória\n"
        "df.info()\n"
        "display(df.describe(include='all').T)\n"
        "display(df.isna().mean().sort_values(ascending=False).head(20))\n"
        "num = df.select_dtypes('number')\n"
        "if num.shape[1] >= 2:\n"
        "    display(num.corr().round(3))"
    )
    return StepResult(
        dataframe=data,
        code=code,
        call="",
        summary=" ".join(highlights),
        imports=["import pandas as pd"],
        extra={"eda": report},
    )


def _jsonable(obj: Any) -> Any:
    import numpy as np

    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        value = float(obj)
        return None if pd.isna(value) else value
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    if obj is not None and pd.isna(obj) is True:
        return None
    return obj


REGISTRY: dict[str, Callable[[StepContext, pd.DataFrame | None], StepResult]] = {
    "load": step_load,
    "clean": step_clean,
    "wrangle": step_wrangle,
    "feature": step_feature,
    "eda": step_eda,
    "viz": step_viz,
}

LABELS = {
    "load": "Carga de dados",
    "clean": "Limpeza",
    "wrangle": "Transformação",
    "feature": "Engenharia de atributos",
    "eda": "Exploração",
    "viz": "Visualização",
}
