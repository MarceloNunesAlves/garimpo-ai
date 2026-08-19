# Garimpo.ai ⛏️

> Um time de agentes de dados que trabalha **à vista**: checklist antes de começar,
> explicação do que cada agente fez com as suas colunas, checkpoint a cada etapa e um
> notebook reprodutível no final.

O Garimpo.ai roda um time de agentes de código (limpeza, wrangling, feature engineering,
visualização) em `backend/garimpo/agents/`, orquestrado por um checklist que você revisa
antes de começar. O foco é a experiência: uma interface Angular para quem quer
**entender o que aconteceu com os próprios dados**, não só receber o resultado final.

---

## O que ele faz diferente

| | Como funciona |
| --- | --- |
| **Checklist primeiro** | Antes de qualquer agente rodar, um planejador monta o roteiro a partir do seu objetivo e do schema das fontes. Você revisa, edita e só então inicia. |
| **Checklist vivo** | Entre uma etapa e outra o planejador reavalia o que falta e pode reescrever as próximas — cada mudança fica registrada com o motivo e sobe a revisão. |
| **Transparência real** | Cada etapa mostra o diff **medido** no dataframe: quais colunas saíram e por quê, quais células foram preenchidas, com qual valor e por qual estratégia, quantas linhas caíram. Os números vêm do pandas, não do LLM. |
| **Nada é copiado** | Fontes são apenas caminhos. CSV, diretório inteiro, parquet, excel, jsonl — o dado é lido de onde já está. Zero duplicação de disco. |
| **Retomar do ponto da falha** | Toda etapa concluída grava um checkpoint. Se a etapa 4 quebra, as 1–3 continuam válidas: corrija e clique em "Retomar de onde parou". |
| **Notebook no final** | Um `.ipynb` com o código de cada agente, a explicação de cada decisão e as leituras apontando para os caminhos originais. Roda sem o Garimpo. |
| **IA configurada no banco** | Provedor, modelo e chave ficam no SQLite (criado no start) ou num Postgres seu — não em variáveis de ambiente espalhadas. |

---

## Instalação

Pré-requisitos: **Python 3.10+**, **Node 20+**.

```bash
git clone <este-repo> garimpo-ai && cd garimpo-ai

# instala backend (venv) e frontend (npm)
make setup
```

Em dois terminais:

```bash
make api   # http://localhost:8000  (docs em /docs)
make ui    # http://localhost:4200
```

O `ng serve` já faz proxy de `/api` para a porta 8000 (`frontend/proxy.conf.json`).

### Banco de dados

Nada a configurar: no start o Garimpo cria `~/.garimpo-ai/garimpo.db` (SQLite) com as
tabelas. Para usar Postgres, exporte a URL antes de subir a API:

```bash
export GARIMPO_DATABASE_URL=postgresql+psycopg://garimpo:senha@localhost:5432/garimpo
```

As tabelas são criadas no start em qualquer um dos dois. Veja `backend/.env.example`
para as demais opções (diretórios permitidos, CORS, limite de linhas).

---

## Fluxo de uso

1. **Configuração de IA** — cadastre um provedor (Anthropic, OpenAI ou Ollama local),
   teste a conexão e marque um como padrão.
2. **Fontes de dados** — navegue pelo servidor e selecione o caminho de um arquivo ou de
   um diretório inteiro. O Garimpo lê uma amostra para mostrar colunas e tipos; o arquivo
   não sai do lugar.
3. **Novo garimpo** — escreva o objetivo em português, escolha as fontes e deixe o
   planejador montar o checklist.
4. **Revise o checklist** — ajuste títulos, instruções, adicione ou remova etapas.
5. **Inicie** — acompanhe ao vivo: qual agente está rodando, o que ele decidiu, o diff dos
   dados, o código gerado e a amostra do resultado de cada etapa.
6. **Baixe o notebook** — o `.ipynb` reproduz tudo do zero.

Sem IA configurada o Garimpo ainda roda as etapas determinísticas (`load` e `eda`); as
demais precisam de um modelo porque geram código.

---

## Agentes disponíveis

| id | Agente | O que faz |
| --- | --- | --- |
| `load` | Carga | Lê e consolida as fontes selecionadas (determinístico) |
| `wrangle` | Transformação | Reestrutura, junta, pivota — `DataWranglingAgent` |
| `clean` | Limpeza | Ausentes, tipos, duplicatas, outliers — `DataCleaningAgent` |
| `feature` | Atributos | Variáveis derivadas — `FeatureEngineeringAgent` |
| `eda` | Exploração | Perfil, ausentes, correlações (determinístico) |
| `viz` | Visualização | Gráfico Plotly — `DataVisualizationAgent` |

---

## Arquitetura

```
garimpo-ai/
├── backend/
│   └── garimpo/
│       ├── main.py              FastAPI (cria banco e tabelas no start)
│       ├── config.py            settings via GARIMPO_*
│       ├── db/models.py         AIConfig, DataSource, Run, ChecklistItem, RunStep, Event, Artifact
│       ├── api/                 ai_configs · sources (browse) · runs (SSE, notebook)
│       ├── core/
│       │   ├── checklist.py     planejador: cria e revisa o checklist
│       │   ├── runner.py        orquestra as etapas, checkpoint e retomada
│       │   ├── steps.py         adaptadores dos agentes (garimpo.agents)
│       │   ├── explain.py       diff determinístico + narrativa opcional
│       │   ├── storage.py       checkpoints em parquet
│       │   ├── notebook.py      geração do .ipynb final
│       │   ├── datasources.py   leitura por caminho (arquivo ou diretório)
│       │   └── events.py        trilha de eventos (SSE)
│       └── agents/              agentes de código (LangGraph) — MIT,
│                                ver agents/LICENSE
└── frontend/                    Angular 20 standalone + signals
    └── src/app/
        ├── core/                api.service.ts (REST + EventSource) · models.ts
        ├── components/          checklist · step-card · event-feed · path-browser · data-table · plotly
        └── pages/               dashboard · sources · ai-settings · run-new · run-detail
```

### Como a retomada funciona

Cada etapa concluída grava o dataframe em
`~/.garimpo-ai/workspace/runs/<run_id>/steps/NN_<agente>.parquet` e a linha correspondente
em `run_step` (código, resumo, explicação, caminho do checkpoint). Ao retomar, o runner
carrega o checkpoint da última etapa `done` e continua no primeiro item pendente — as
etapas anteriores não rodam de novo, e nenhuma chamada de LLM é repetida.

### Como a explicação é montada

1. **Fatos** (`core/explain.py`): diff entre o dataframe antes e depois — colunas removidas
   com a estatística que justifica a remoção (% de ausentes, cardinalidade, constância),
   células imputadas com a estratégia inferida ao comparar o valor usado com a média,
   mediana ou moda originais, mudanças de tipo, linhas descartadas.
2. **Narrativa**: o LLM escreve 2–4 frases *a partir* desses fatos e do código gerado.
   Se o modelo falhar ou não houver IA, a tela e o notebook continuam completos — só sem
   o parágrafo em prosa.

---

## Testes

```bash
make test
```

Cobrem o fluxo ponta a ponta sem depender de LLM: cadastro de fonte por caminho, criação
do run com checklist, execução com checkpoint, falha no meio com retomada reaproveitando o
checkpoint, explicabilidade (remoção e imputação) e geração do notebook.

---

## Licença

MIT. O time de agentes em `backend/garimpo/agents/` carrega a sua própria licença MIT
de origem em `backend/garimpo/agents/LICENSE`.
