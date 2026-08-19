"""Smoke test do fluxo completo, sem depender de LLM.

Cobre: cadastro de fonte por caminho, criação do run com checklist, execução com
checkpoint por etapa, explicabilidade e geração do notebook final.

    pytest backend/tests -q
"""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

import pandas as pd
import pytest

TMP = Path(tempfile.mkdtemp(prefix="garimpo-test-"))
os.environ["GARIMPO_HOME"] = str(TMP / "home")

from fastapi.testclient import TestClient  # noqa: E402

from garimpo.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def csv_path() -> str:
    data = pd.DataFrame(
        {
            "id": range(1, 21),
            "idade": [30, None, 45, 22, 38, None, 51, 29, 33, 40] * 2,
            "cidade": ["SP", "RJ", None, "SP", "BH", "RJ", "SP", None, "BH", "SP"] * 2,
            "quase_vazia": [None] * 18 + [1, 2],
            "constante": ["x"] * 20,
        }
    )
    path = TMP / "vendas.csv"
    data.to_csv(path, index=False)
    return str(path)


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["database"] == "sqlite"


def test_browse_lists_only_readable_files(client, csv_path):
    body = client.get("/api/sources/browse", params={"path": str(TMP)}).json()
    names = [e["name"] for e in body["entries"]]
    assert "vendas.csv" in names


def test_full_run_produces_notebook(client, csv_path):
    source = client.post(
        "/api/sources", json={"path": csv_path, "name": "vendas"}
    ).json()
    assert source["profile"]["columns"] == [
        "id",
        "idade",
        "cidade",
        "quase_vazia",
        "constante",
    ]

    run = client.post(
        "/api/runs",
        json={
            "objective": "Entender a base de vendas",
            "source_ids": [source["id"]],
        },
    ).json()
    # Sem IA configurada, cai no checklist padrão.
    assert [i["agent"] for i in run["items"]] == ["load", "clean", "eda"]

    # A etapa de limpeza precisa de LLM; o teste roda só o que é determinístico.
    run = client.put(
        f"/api/runs/{run['id']}/checklist",
        json=[
            {"agent": "load", "title": "Carregar", "instructions": ""},
            {"agent": "eda", "title": "Explorar", "instructions": "Perfil geral"},
        ],
    ).json()

    assert client.post(f"/api/runs/{run['id']}/start").status_code == 200

    detail = _wait_for(client, run["id"], {"completed", "failed"})
    assert detail["status"] == "completed", detail.get("error")

    steps = detail["steps"]
    assert [s["agent"] for s in steps] == ["load", "eda"]
    assert all(s["status"] == "done" for s in steps)

    # Checkpoint em disco por etapa (é o que permite retomar).
    for step in steps:
        assert step["output_path"] and Path(step["output_path"]).exists()

    # Amostra do dado da etapa.
    preview = client.get(
        f"/api/runs/{run['id']}/steps/{steps[0]['id']}/data"
    ).json()
    assert preview["total_rows"] == 20

    # Explicabilidade da etapa de exploração.
    eda = steps[1]["explanation"]["extra"]["eda"]
    assert eda["shape"] == [20, 5]
    assert "quase_vazia" in eda["missing"]

    # Notebook final.
    assert detail["notebook_path"] and Path(detail["notebook_path"]).exists()
    nb = client.get(f"/api/runs/{run['id']}/notebook")
    assert nb.status_code == 200
    assert b"Garimpo.ai" in nb.content

    events = client.get(f"/api/runs/{run['id']}/events").json()
    types = {e["type"] for e in events}
    assert {"run.started", "step.done", "notebook.ready", "run.completed"} <= types


def test_failure_keeps_progress_and_resume_continues(client, csv_path):
    """Requisito: falhar no meio não pode jogar fora o que já rodou."""
    source = client.post(
        "/api/sources", json={"path": csv_path, "name": "vendas_resume"}
    ).json()
    run = client.post(
        "/api/runs",
        json={"objective": "Testar retomada", "source_ids": [source["id"]]},
    ).json()

    # `clean` exige LLM e não há IA configurada: a etapa 2 falha de propósito.
    run = client.put(
        f"/api/runs/{run['id']}/checklist",
        json=[
            {"agent": "load", "title": "Carregar", "instructions": ""},
            {"agent": "clean", "title": "Limpar", "instructions": "Tratar ausentes"},
            {"agent": "eda", "title": "Explorar", "instructions": ""},
        ],
    ).json()
    client.post(f"/api/runs/{run['id']}/start")

    failed = _wait_for(client, run["id"], {"failed", "completed"})
    assert failed["status"] == "failed"

    statuses = {i["agent"]: i["status"] for i in failed["items"]}
    assert statuses["load"] == "done"  # etapa 1 preservada
    assert statuses["clean"] == "failed"
    assert statuses["eda"] == "pending"
    load_checkpoint = failed["steps"][0]["output_path"]
    assert Path(load_checkpoint).exists()

    # O usuário corrige o plano (tira a etapa que não dá para rodar) e retoma.
    client.put(
        f"/api/runs/{run['id']}/checklist",
        json=[{"agent": "eda", "title": "Explorar", "instructions": ""}],
    )
    assert client.post(f"/api/runs/{run['id']}/resume").status_code == 200

    done = _wait_for(client, run["id"], {"completed", "failed"})
    assert done["status"] == "completed", done.get("error")

    # A carga não rodou de novo: o checkpoint foi reaproveitado.
    load_steps = [s for s in done["steps"] if s["agent"] == "load"]
    assert len(load_steps) == 1
    assert load_steps[0]["output_path"] == load_checkpoint
    assert Path(done["notebook_path"]).exists()


def test_explain_detects_drops_and_imputations():
    from garimpo.core import explain

    before = pd.DataFrame(
        {
            "idade": [30, None, 40, None],
            "vazia": [None, None, None, 1],
            "cidade": ["SP", "RJ", "SP", "BH"],
        }
    )
    after = before.drop(columns=["vazia"]).copy()
    after["idade"] = after["idade"].fillna(35.0)

    diff = explain.diff_dataframes(before, after, code="df = df.drop(columns=['vazia'])")

    dropped = diff["columns_removed"][0]
    assert dropped["column"] == "vazia"
    assert "75%" in dropped["reason"] or "ausentes" in dropped["reason"]

    imputed = diff["imputations"][0]
    assert imputed["column"] == "idade"
    assert imputed["filled"] == 2
    assert imputed["value"] == 35.0
    assert "média" in imputed["strategy"] or "constante" in imputed["strategy"]


def _wait_for(client, run_id: str, statuses: set[str], timeout: float = 60.0) -> dict:
    deadline = time.time() + timeout
    detail = {}
    while time.time() < deadline:
        detail = client.get(f"/api/runs/{run_id}").json()
        if detail["status"] in statuses:
            return detail
        time.sleep(0.3)
    raise AssertionError(f"Timeout aguardando o run. Último estado: {detail}")
