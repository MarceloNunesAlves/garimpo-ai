import { Component, computed, inject, input, signal } from '@angular/core';
import { DatePipe, DecimalPipe, PercentPipe } from '@angular/common';

import { ApiService } from '../core/api.service';
import {
  AGENT_ICONS,
  AGENT_LABELS,
  ChecklistItem,
  DataPreview,
  RunStep,
} from '../core/models';
import { DataTableComponent } from './data-table.component';
import { PlotlyFigureComponent } from './plotly-figure.component';
import { StatusChipComponent } from './status-chip.component';

type Tab = 'explicacao' | 'dados' | 'codigo' | 'perfil' | 'grafico';

/**
 * O cartão que responde "o que este agente fez com os meus dados?".
 * Os números vêm do diff medido no backend — não de texto gerado por LLM.
 */
@Component({
  selector: 'gm-step-card',
  standalone: true,
  imports: [
    DatePipe,
    DecimalPipe,
    PercentPipe,
    DataTableComponent,
    PlotlyFigureComponent,
    StatusChipComponent,
  ],
  template: `
    <article class="card step" [class.failed]="step().status === 'failed'">
      <header (click)="open.set(!open())">
        <span class="icon">{{ icon() }}</span>
        <div class="title">
          <h3>{{ position() }}. {{ title() }}</h3>
          <div class="small muted">
            <span class="tag">{{ step().agent }}</span>
            {{ agentLabel() }}
            @if (step().attempt > 1) {
              · tentativa {{ step().attempt }}
            }
            @if (step().finished_at) {
              · {{ step().finished_at | date: 'HH:mm:ss' }}
            }
          </div>
        </div>
        <gm-status-chip [status]="step().status" />
        <span class="caret">{{ open() ? '▾' : '▸' }}</span>
      </header>

      @if (open()) {
        <div class="body">
          @if (step().status === 'failed') {
            <div class="alert err">
              <strong>Falhou.</strong> {{ step().error }}
            </div>
          }

          @if (headline(); as h) {
            <div class="headline">{{ h }}</div>
          }

          <nav class="tabs">
            @for (t of tabs(); track t.id) {
              <button
                class="btn-sm"
                [class.on]="tab() === t.id"
                (click)="select(t.id)"
              >
                {{ t.label }}
              </button>
            }
          </nav>

          <!-- ---------------- explicação ---------------- -->
          @if (tab() === 'explicacao') {
            @if (narrative()) {
              <p class="narrative">{{ narrative() }}</p>
            } @else if (step().summary) {
              <p class="narrative">{{ step().summary }}</p>
            }

            @if (shape(); as s) {
              <div class="shape">
                <span>{{ s.before }}</span>
                <span class="arrow">→</span>
                <span class="after">{{ s.after }}</span>
              </div>
            }

            @if (diff().columns_removed?.length) {
              <section>
                <h4>Colunas removidas <small>e o motivo de cada uma</small></h4>
                <div class="table-wrap">
                  <table class="data">
                    <thead>
                      <tr>
                        <th>Coluna</th>
                        <th>Ausentes</th>
                        <th>Distintos</th>
                        <th>Motivo</th>
                      </tr>
                    </thead>
                    <tbody>
                      @for (col of diff().columns_removed; track col.column) {
                        <tr>
                          <td><code>{{ col.column }}</code></td>
                          <td>{{ col.missing_pct | percent: '1.0-1' }}</td>
                          <td>{{ col.n_unique | number }}</td>
                          <td class="reason">{{ col.reason }}</td>
                        </tr>
                      }
                    </tbody>
                  </table>
                </div>
              </section>
            }

            @if (diff().imputations?.length) {
              <section>
                <h4>Valores preenchidos <small>quais células, com que valor e por quê</small></h4>
                <div class="table-wrap">
                  <table class="data">
                    <thead>
                      <tr>
                        <th>Coluna</th>
                        <th>Células</th>
                        <th>Estratégia</th>
                        <th>Valor</th>
                        <th>Motivo</th>
                      </tr>
                    </thead>
                    <tbody>
                      @for (imp of diff().imputations; track imp.column) {
                        <tr>
                          <td><code>{{ imp.column }}</code></td>
                          <td>
                            {{ imp.filled | number }}
                            <span class="muted">({{ imp.filled_pct | percent: '1.0-1' }})</span>
                          </td>
                          <td>{{ imp.strategy }}</td>
                          <td><code>{{ imp.value ?? '—' }}</code></td>
                          <td class="reason">{{ imp.reason }}</td>
                        </tr>
                      }
                    </tbody>
                  </table>
                </div>
              </section>
            }

            @if (loadedColumns().length) {
              <section>
                <h4>Colunas carregadas <small>{{ loadedColumns().length }} no total</small></h4>
                <div class="cols">
                  @for (col of loadedColumns(); track col.name) {
                    <span class="tag">{{ col.name }} <em>{{ col.dtype }}</em></span>
                  }
                </div>
              </section>
            }

            @if (diff().columns_added?.length) {
              <section>
                <h4>Colunas criadas</h4>
                <ul class="plain">
                  @for (col of diff().columns_added; track col.column) {
                    <li>
                      <code>{{ col.column }}</code>
                      <span class="tag">{{ col.dtype }}</span>
                      @if (col.derived_from.length) {
                        <span class="muted small">
                          derivada de {{ col.derived_from.join(', ') }}
                        </span>
                      }
                      @if (col.sample_values.length) {
                        <span class="muted small">
                          · ex.: {{ col.sample_values.join(', ') }}
                        </span>
                      }
                    </li>
                  }
                </ul>
              </section>
            }

            @if (diff().columns_changed?.length) {
              <section>
                <h4>Tipos alterados</h4>
                <ul class="plain">
                  @for (col of diff().columns_changed; track col.column) {
                    <li>
                      <code>{{ col.column }}</code>:
                      <span class="tag">{{ col.from }}</span> →
                      <span class="tag">{{ col.to }}</span>
                      <span class="muted small">{{ col.reason }}</span>
                    </li>
                  }
                </ul>
              </section>
            }

            @if (rowsRemoved() > 0) {
              <section>
                <h4>Linhas descartadas</h4>
                <p class="small">
                  {{ rowsRemoved() | number }} de
                  {{ diff().rows?.before | number }} linhas
                  ({{ diff().rows?.removed_pct | percent: '1.0-1' }}).
                  @if (diff().rows?.reasons?.length) {
                    Indícios: {{ diff().rows?.reasons?.join('; ') }}.
                  }
                </p>
              </section>
            }

            @if (nothingChanged()) {
              <p class="small muted">
                Esta etapa não alterou a estrutura dos dados.
              </p>
            }
          }

          <!-- ---------------- dados ---------------- -->
          @if (tab() === 'dados') {
            @if (loadingPreview()) {
              <p class="small muted pulse">Lendo o checkpoint da etapa…</p>
            } @else if (previewError()) {
              <div class="alert warn">{{ previewError() }}</div>
            } @else {
              <gm-data-table [preview]="preview()" />
            }
          }

          <!-- ---------------- código ---------------- -->
          @if (tab() === 'codigo') {
            @if (step().code) {
              <pre class="code">{{ step().code }}</pre>
              @if (step().explanation.call) {
                <p class="small muted">
                  No notebook esta função é aplicada com:
                  <code>{{ step().explanation.call }}</code>
                </p>
              }
            } @else {
              <p class="small muted">Esta etapa não gerou código.</p>
            }
          }

          <!-- ---------------- perfil (EDA) ---------------- -->
          @if (tab() === 'perfil' && eda(); as report) {
            <div class="grid-2">
              <div>
                <h4>Valores ausentes</h4>
                @if (missingList().length) {
                  <ul class="plain">
                    @for (m of missingList(); track m.column) {
                      <li>
                        <code>{{ m.column }}</code>
                        <span class="bar">
                          <span [style.width.%]="m.pct * 100"></span>
                        </span>
                        <span class="small muted">
                          {{ m.pct | percent: '1.0-1' }} ({{ m.count | number }})
                        </span>
                      </li>
                    }
                  </ul>
                } @else {
                  <p class="small muted">Nenhum valor ausente.</p>
                }
              </div>
              <div>
                <h4>Correlações mais fortes</h4>
                @if (report.top_correlations?.length) {
                  <ul class="plain">
                    @for (c of report.top_correlations; track c.a + c.b) {
                      <li>
                        <code>{{ c.a }}</code> × <code>{{ c.b }}</code>
                        <strong [class.neg]="c.corr < 0">{{ c.corr }}</strong>
                      </li>
                    }
                  </ul>
                } @else {
                  <p class="small muted">Sem pares com correlação relevante (≥ 0,5).</p>
                }
              </div>
            </div>
          }

          <!-- ---------------- gráfico ---------------- -->
          @if (tab() === 'grafico' && figure()) {
            <gm-plotly-figure [figure]="figure()" />
          }
        </div>
      }
    </article>
  `,
  styles: [
    `
      .step {
        overflow: hidden;
      }
      .step.failed {
        border-color: #f0b9b9;
      }

      header {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 13px 16px;
        cursor: pointer;
        user-select: none;

        &:hover {
          background: var(--slate-50);
        }
      }

      .icon {
        font-size: 19px;
      }
      .title {
        flex: 1;
        min-width: 0;
      }
      .caret {
        color: var(--slate-400);
      }

      .body {
        padding: 4px 16px 18px;
        border-top: 1px solid var(--slate-100);
      }

      .headline {
        margin: 12px 0;
        padding: 9px 12px;
        background: var(--gold-100);
        border-left: 3px solid var(--gold-400);
        border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
        font-weight: 600;
        font-size: 13px;
        color: #6b4a08;
      }

      .tabs {
        display: flex;
        gap: 6px;
        margin: 12px 0 14px;
        flex-wrap: wrap;

        button {
          background: transparent;
          border: 1px solid var(--slate-200);
          color: var(--slate-600);

          &.on {
            background: var(--slate-900);
            border-color: var(--slate-900);
            color: #fff;
          }
        }
      }

      .narrative {
        font-size: 14px;
        line-height: 1.6;
      }

      .shape {
        display: inline-flex;
        align-items: center;
        gap: 10px;
        padding: 6px 12px;
        background: var(--slate-50);
        border: 1px solid var(--slate-200);
        border-radius: var(--radius-sm);
        font-family: var(--mono);
        font-size: 12.5px;
        margin-bottom: 14px;

        .arrow {
          color: var(--gold-500);
        }
        .after {
          font-weight: 700;
        }
      }

      section {
        margin-bottom: 18px;
      }

      h4 {
        margin: 0 0 8px;
        font-size: 13px;

        small {
          font-weight: 400;
          color: var(--slate-500);
          margin-left: 6px;
        }
      }

      .reason {
        white-space: normal;
        min-width: 240px;
        color: var(--slate-600);
      }

      ul.plain {
        list-style: none;
        margin: 0;
        padding: 0;

        li {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 4px 0;
          border-bottom: 1px solid var(--slate-100);
          font-size: 13px;
        }
      }

      code {
        background: var(--slate-100);
        padding: 1px 5px;
        border-radius: 4px;
      }

      .bar {
        flex: 1;
        max-width: 140px;
        height: 6px;
        background: var(--slate-100);
        border-radius: 999px;
        overflow: hidden;

        span {
          display: block;
          height: 100%;
          background: var(--gold-400);
        }
      }

      strong.neg {
        color: var(--err);
      }

      .cols {
        display: flex;
        flex-wrap: wrap;
        gap: 5px;

        em {
          font-style: normal;
          color: var(--slate-400);
          margin-left: 4px;
        }
      }
    `,
  ],
})
export class StepCardComponent {
  private api = inject(ApiService);

  runId = input.required<string>();
  step = input.required<RunStep>();
  item = input<ChecklistItem | undefined>();
  expanded = input(false);

  open = signal(false);
  tab = signal<Tab>('explicacao');
  preview = signal<DataPreview | null>(null);
  loadingPreview = signal(false);
  previewError = signal('');

  constructor() {
    queueMicrotask(() => this.open.set(this.expanded()));
  }

  position = computed(() => this.step().position + 1);
  icon = computed(() => AGENT_ICONS[this.step().agent] ?? '•');
  agentLabel = computed(() => AGENT_LABELS[this.step().agent] ?? this.step().agent);
  title = computed(() => this.item()?.title ?? this.agentLabel());
  headline = computed(() => this.step().explanation?.headline ?? '');
  narrative = computed(() => this.step().explanation?.narrative ?? '');
  diff = computed(() => this.step().explanation?.diff ?? {});
  eda = computed(() => this.step().explanation?.extra?.eda);
  figure = computed(() => this.step().explanation?.extra?.figure);
  rowsRemoved = computed(() => this.diff().rows?.removed ?? 0);

  loadedColumns = computed(() =>
    Object.entries(this.diff().loaded_columns ?? {}).map(([name, dtype]) => ({
      name,
      dtype,
    })),
  );

  shape = computed(() => {
    const d = this.diff();
    if (!d.shape_after) {
      return null;
    }
    const before = d.shape_before
      ? `${d.shape_before[0]} linhas × ${d.shape_before[1]} colunas`
      : 'origem';
    return { before, after: `${d.shape_after[0]} linhas × ${d.shape_after[1]} colunas` };
  });

  nothingChanged = computed(() => {
    const d = this.diff();
    return (
      !d.columns_removed?.length &&
      !d.columns_added?.length &&
      !d.columns_changed?.length &&
      !d.imputations?.length &&
      !this.loadedColumns().length &&
      !this.rowsRemoved()
    );
  });

  missingList = computed(() => {
    const missing = this.eda()?.missing ?? {};
    return Object.entries(missing)
      .map(([column, value]) => ({ column, ...value }))
      .sort((a, b) => b.pct - a.pct)
      .slice(0, 12);
  });

  tabs = computed(() => {
    const list: { id: Tab; label: string }[] = [{ id: 'explicacao', label: 'O que foi feito' }];
    if (this.step().output_path) {
      list.push({ id: 'dados', label: 'Dados resultantes' });
    }
    if (this.step().code) {
      list.push({ id: 'codigo', label: 'Código' });
    }
    if (this.eda()) {
      list.push({ id: 'perfil', label: 'Perfil dos dados' });
    }
    if (this.figure()) {
      list.push({ id: 'grafico', label: 'Gráfico' });
    }
    return list;
  });

  select(tab: Tab): void {
    this.tab.set(tab);
    if (tab === 'dados' && !this.preview() && !this.loadingPreview()) {
      this.loadPreview();
    }
  }

  private loadPreview(): void {
    this.loadingPreview.set(true);
    this.previewError.set('');
    this.api.stepData(this.runId(), this.step().id).subscribe({
      next: (data) => {
        this.preview.set(data);
        this.loadingPreview.set(false);
      },
      error: (err) => {
        this.previewError.set(err?.error?.detail ?? 'Não foi possível ler o checkpoint.');
        this.loadingPreview.set(false);
      },
    });
  }
}
