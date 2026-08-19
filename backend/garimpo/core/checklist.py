"""O checklist que o time de agentes precisa seguir.

Regras do produto:

* o checklist é montado **antes** de qualquer agente rodar e fica visível (e
  editável) para o usuário;
* entre uma etapa e outra o planejador pode reescrever o que ainda não rodou —
  ex.: a limpeza descobriu que 3 colunas eram datas, então entra uma etapa de
  wrangling que não existia no plano original;
* toda mudança guarda o motivo e sobe a revisão, então dá para auditar depois.
"""

from __future__ import annotations

import json
import re
from typing import Any

AGENTS = {
    "load": "Carregar e consolidar as fontes de dados selecionadas",
    "wrangle": "Reestruturar/juntar/pivotar os dados",
    "clean": "Tratar ausentes, tipos, duplicatas e outliers",
    "feature": "Criar variáveis derivadas para análise/modelagem",
    "eda": "Análise exploratória: distribuições, ausentes, correlações",
    "viz": "Gerar um gráfico que responda a uma pergunta específica",
}

PLANNER_SYSTEM = """Você é o planejador do Garimpo.ai. Antes de qualquer agente tocar nos dados,
você escreve o checklist que o time deve seguir.

Agentes disponíveis (use exatamente estes ids):
{agents}

Regras:
- Responda SOMENTE com JSON válido, sem cercas de código.
- Schema: {{"title": str, "target_variable": str|null, "items": [{{"agent": str, "title": str, "instructions": str}}], "notes": [str]}}
- O primeiro item é sempre `load`.
- `title` de cada item é curto e em português, legível por quem não é técnico.
- `instructions` é a ordem concreta dada ao agente (o que fazer, em qual coluna, com qual critério).
- Prefira o plano mínimo que atinge o objetivo. Não inclua `feature` nem modelagem se o usuário só quer entender os dados.
- Só inclua `viz` quando houver uma pergunta visual clara; uma instrução por gráfico.
- `target_variable` só quando o usuário indicar uma variável-alvo.
- Entre 3 e 7 itens."""

PLANNER_HUMAN = """Objetivo do usuário:
{objective}

Fontes de dados selecionadas:
{sources}

Amostra das colunas disponíveis:
{schema}

Retorne apenas o JSON."""

REVISE_SYSTEM = """Você é o planejador do Garimpo.ai revisando o checklist no meio da execução.

Você recebe: o objetivo, a etapa que acabou de rodar (com os fatos medidos no dataframe)
e os itens que ainda não rodaram. Decida se o restante do plano continua adequado.

Regras:
- Responda SOMENTE com JSON válido, sem cercas de código.
- Schema: {{"changed": bool, "rationale": str, "items": [{{"agent": str, "title": str, "instructions": str}}]}}
- `items` é a lista COMPLETA do que ainda deve rodar, na ordem. Se nada muda, repita os itens recebidos e use changed=false.
- Só mude o plano se os fatos justificarem: coluna que sumiu, tipo inesperado, dado sujo demais, objetivo já atendido.
- Você pode remover itens que perderam sentido (ex.: gráfico de uma coluna que foi descartada).
- `rationale` explica a mudança em uma frase, em português, citando o fato que motivou.
- Agentes válidos: {agents}"""

REVISE_HUMAN = """Objetivo: {objective}

Etapa concluída: {done_title} (agente: {done_agent})
Resumo: {summary}
Fatos medidos:
{facts}

Estado atual do dataframe: {shape} linhas x colunas: {columns}

Itens ainda pendentes:
{pending}

Retorne apenas o JSON."""


def _parse_json(text: str) -> dict:
    if not text:
        return {}
    if isinstance(text, list):  # blocos de conteúdo do Anthropic
        text = " ".join(b.get("text", "") for b in text if isinstance(b, dict))
    text = str(text).strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            return {}
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}


def _normalize_items(raw: Any) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    if not isinstance(raw, list):
        return items
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        agent = str(entry.get("agent", "")).strip().lower()
        if agent not in AGENTS:
            continue
        items.append(
            {
                "agent": agent,
                "title": str(entry.get("title") or AGENTS[agent]).strip()[:200],
                "instructions": str(entry.get("instructions") or "").strip(),
            }
        )
    return items


def default_checklist(objective: str) -> list[dict[str, str]]:
    """Plano usado quando não há LLM configurado ou o planejador falha."""
    return [
        {
            "agent": "load",
            "title": "Carregar as fontes selecionadas",
            "instructions": "Ler todos os caminhos informados e consolidar em um dataframe.",
        },
        {
            "agent": "clean",
            "title": "Limpar os dados",
            "instructions": (
                "Remover colunas com mais de 40% de ausentes, imputar numéricas pela "
                "mediana e categóricas pela moda, corrigir tipos e remover duplicatas."
            ),
        },
        {
            "agent": "eda",
            "title": "Explorar os dados tratados",
            "instructions": f"Descrever distribuições e correlações à luz do objetivo: {objective}",
        },
    ]


class ChecklistPlanner:
    def __init__(self, llm=None):
        self.llm = llm

    # -- criação ---------------------------------------------------------- #
    def create(
        self, objective: str, sources: list[dict[str, Any]], schema: dict[str, Any]
    ) -> dict[str, Any]:
        if self.llm is None:
            return {
                "title": (objective or "Novo garimpo")[:80],
                "target_variable": None,
                "items": default_checklist(objective),
                "notes": ["Checklist padrão: nenhuma configuração de IA ativa."],
            }

        prompt = [
            ("system", PLANNER_SYSTEM.format(agents=_agent_help())),
            (
                "human",
                PLANNER_HUMAN.format(
                    objective=objective or "(não informado)",
                    sources=json.dumps(sources, ensure_ascii=False, default=str)[:2000],
                    schema=json.dumps(schema, ensure_ascii=False, default=str)[:3000],
                ),
            ),
        ]
        data = _parse_json(_invoke(self.llm, prompt))
        items = _normalize_items(data.get("items"))
        if not items:
            items = default_checklist(objective)
        if items[0]["agent"] != "load":
            items.insert(0, default_checklist(objective)[0])

        target = data.get("target_variable")
        return {
            "title": str(data.get("title") or objective or "Novo garimpo")[:200],
            "target_variable": str(target).strip() if target else None,
            "items": items,
            "notes": [str(n) for n in (data.get("notes") or []) if str(n).strip()],
        }

    # -- revisão entre agentes -------------------------------------------- #
    def revise(
        self,
        *,
        objective: str,
        done_title: str,
        done_agent: str,
        summary: str,
        facts: dict[str, Any],
        shape: tuple[int, int],
        columns: list[str],
        pending: list[dict[str, str]],
    ) -> dict[str, Any]:
        """Devolve {'changed': bool, 'rationale': str, 'items': [...]}"""
        if self.llm is None or not pending:
            return {"changed": False, "rationale": "", "items": pending}

        prompt = [
            ("system", REVISE_SYSTEM.format(agents=", ".join(AGENTS))),
            (
                "human",
                REVISE_HUMAN.format(
                    objective=objective or "(não informado)",
                    done_title=done_title,
                    done_agent=done_agent,
                    summary=(summary or "")[:1500],
                    facts=json.dumps(facts, ensure_ascii=False, default=str)[:4000],
                    shape=f"{shape[0]}x{shape[1]}",
                    columns=", ".join(map(str, columns[:60])),
                    pending=json.dumps(pending, ensure_ascii=False)[:3000],
                ),
            ),
        ]
        data = _parse_json(_invoke(self.llm, prompt))
        items = _normalize_items(data.get("items"))
        if not items and not data:
            return {"changed": False, "rationale": "", "items": pending}

        changed = bool(data.get("changed")) or items != pending
        return {
            "changed": changed,
            "rationale": str(data.get("rationale") or "").strip(),
            "items": items if items else pending,
        }


def _agent_help() -> str:
    return "\n".join(f"- {key}: {desc}" for key, desc in AGENTS.items())


def _invoke(llm, prompt) -> str:
    # As mensagens já chegam formatadas; passar por ChatPromptTemplate faria o
    # LangChain interpretá-las como f-string de novo e quebrar em qualquer chave
    # (o JSON do schema, os fatos medidos, nomes de coluna com `{`).
    from langchain_core.messages import HumanMessage, SystemMessage

    roles = {"system": SystemMessage, "human": HumanMessage}
    resp = llm.invoke([roles[role](content=text) for role, text in prompt])
    content = getattr(resp, "content", resp)
    if isinstance(content, list):
        content = " ".join(b.get("text", "") for b in content if isinstance(b, dict))
    return str(content)
