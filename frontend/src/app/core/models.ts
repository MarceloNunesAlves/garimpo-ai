export type AgentKind = 'load' | 'wrangle' | 'clean' | 'feature' | 'eda' | 'viz';

export type RunStatus =
  | 'draft'
  | 'running'
  | 'paused'
  | 'failed'
  | 'completed'
  | 'canceled';

export type ItemStatus = 'pending' | 'running' | 'done' | 'failed' | 'skipped';

export interface AiConfig {
  id: string;
  name: string;
  provider: 'openai' | 'anthropic' | 'ollama';
  model: string;
  base_url: string | null;
  max_tokens: number;
  temperature: number | null;
  is_default: boolean;
  extra: Record<string, unknown>;
  created_at: string;
  has_api_key: boolean;
}

export interface AiConfigInput {
  name: string;
  provider: string;
  model: string;
  api_key?: string | null;
  base_url?: string | null;
  max_tokens: number;
  temperature?: number | null;
  is_default: boolean;
  extra?: Record<string, unknown>;
}

export interface DataSource {
  id: string;
  name: string;
  kind: 'file' | 'directory';
  path: string;
  fmt: string | null;
  options: Record<string, unknown>;
  profile: SourceProfile;
  created_at: string;
}

export interface SourceProfile {
  columns?: string[];
  dtypes?: Record<string, string>;
  sample_rows?: number;
  files?: number;
  bytes?: number;
  preview?: Record<string, unknown>[];
  error?: string;
}

export interface BrowseEntry {
  name: string;
  path: string;
  is_dir: boolean;
  size: number | null;
  fmt: string | null;
  modified: number | null;
}

export interface BrowseResult {
  path: string;
  parent: string | null;
  entries: BrowseEntry[];
}

export interface ChecklistItem {
  id: string;
  position: number;
  agent: AgentKind;
  title: string;
  instructions: string;
  status: ItemStatus;
  origin: 'planner' | 'revision' | 'user';
  rationale: string | null;
  revision: number;
}

export interface ChecklistItemInput {
  agent: AgentKind;
  title: string;
  instructions: string;
}

/** Diff determinístico entre o dataframe antes e depois da etapa. */
export interface StepDiff {
  shape_before?: [number, number] | null;
  shape_after?: [number, number];
  columns_removed?: RemovedColumn[];
  columns_added?: AddedColumn[];
  columns_changed?: ChangedColumn[];
  imputations?: Imputation[];
  rows?: {
    before?: number;
    after?: number;
    removed?: number;
    added?: number;
    removed_pct?: number;
    reasons?: string[];
  };
  /** Presente apenas na etapa de carga: colunas que entraram e seus tipos. */
  loaded_columns?: Record<string, string>;
  index_aligned?: boolean;
  notes?: string[];
}

export interface RemovedColumn {
  column: string;
  reason: string;
  dtype: string;
  missing: number;
  missing_pct: number;
  n_unique: number;
}

export interface AddedColumn {
  column: string;
  dtype: string;
  derived_from: string[];
  sample_values: unknown[];
}

export interface ChangedColumn {
  column: string;
  change: string;
  from: string;
  to: string;
  reason: string;
}

export interface Imputation {
  column: string;
  filled: number;
  filled_pct: number;
  strategy: string;
  value: unknown;
  exact: boolean;
  reason: string;
}

export interface EdaReport {
  shape: [number, number];
  dtypes: Record<string, string>;
  missing: Record<string, { count: number; pct: number }>;
  describe: Record<string, Record<string, number>>;
  cardinality: Record<string, number>;
  top_correlations?: { a: string; b: string; corr: number }[];
  target?: Record<string, unknown>;
}

export interface StepExplanation {
  headline?: string;
  narrative?: string;
  diff?: StepDiff;
  call?: string;
  imports?: string[];
  extra?: {
    eda?: EdaReport;
    figure?: unknown;
    recommended_steps?: string | null;
  };
}

export interface RunStep {
  id: string;
  item_id: string | null;
  position: number;
  agent: AgentKind;
  attempt: number;
  status: 'running' | 'done' | 'failed';
  started_at: string;
  finished_at: string | null;
  code: string | null;
  summary: string | null;
  explanation: StepExplanation;
  error: string | null;
  output_path: string | null;
}

export interface RunSummary {
  id: string;
  title: string;
  objective: string;
  status: RunStatus;
  checklist_revision: number;
  created_at: string;
  updated_at: string;
  finished_at: string | null;
  error: string | null;
}

export interface RunDetail extends RunSummary {
  target_variable: string | null;
  ai_config_id: string | null;
  source_ids: string[];
  adaptive_checklist: boolean;
  notebook_path: string | null;
  items: ChecklistItem[];
  steps: RunStep[];
  sources: DataSource[];
  is_running: boolean;
}

export interface RunCreate {
  objective: string;
  source_ids: string[];
  ai_config_id?: string | null;
  title?: string | null;
  target_variable?: string | null;
  adaptive_checklist: boolean;
}

export interface RunEvent {
  id: number;
  ts: string;
  level: 'info' | 'warning' | 'error';
  type: string;
  agent: string | null;
  message: string;
  payload: Record<string, any>;
}

export interface DataPreview {
  columns: string[];
  dtypes: Record<string, string>;
  rows: Record<string, unknown>[];
  total_rows: number;
  total_columns: number;
}

export const AGENT_LABELS: Record<AgentKind, string> = {
  load: 'Carga de dados',
  wrangle: 'Transformação',
  clean: 'Limpeza',
  feature: 'Engenharia de atributos',
  eda: 'Exploração',
  viz: 'Visualização',
};

export const AGENT_ICONS: Record<AgentKind, string> = {
  load: '📥',
  wrangle: '🔀',
  clean: '🧹',
  feature: '🧬',
  eda: '🔍',
  viz: '📊',
};

export const RUN_STATUS_LABELS: Record<RunStatus, string> = {
  draft: 'rascunho',
  running: 'executando',
  paused: 'pausado',
  failed: 'falhou',
  completed: 'concluído',
  canceled: 'cancelado',
};
