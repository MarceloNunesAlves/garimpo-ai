import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';

import { ApiService } from '../core/api.service';
import { AiConfig, DataSource } from '../core/models';

@Component({
  selector: 'gm-run-new',
  standalone: true,
  imports: [FormsModule, RouterLink],
  template: `
    <header class="page-head">
      <h1>Novo garimpo</h1>
      <p class="muted">
        Diga o que você quer descobrir e escolha as fontes. O planejador monta um
        checklist antes de qualquer agente tocar nos dados — você revisa e só então a
        execução começa.
      </p>
    </header>

    @if (error()) {
      <div class="alert err">{{ error() }}</div>
    }

    <div class="card card-pad stack">
      <label class="field">
        <span>1. O que você quer descobrir?</span>
        <textarea
          [(ngModel)]="objective"
          rows="3"
          placeholder="Ex.: entender por que os clientes cancelam o plano e quais variáveis mais explicam o churn"
        ></textarea>
      </label>

      <div>
        <span class="label">2. Fontes de dados</span>
        @if (!sources().length) {
          <div class="alert warn">
            Nenhuma fonte cadastrada.
            <a routerLink="/fontes">Adicione um caminho</a> para continuar.
          </div>
        } @else {
          <div class="grid-2">
            @for (source of sources(); track source.id) {
              <label class="source" [class.on]="selected().includes(source.id)">
                <input
                  type="checkbox"
                  [checked]="selected().includes(source.id)"
                  (change)="toggle(source.id)"
                />
                <div>
                  <div class="row">
                    <span>{{ source.kind === 'directory' ? '📁' : '📄' }}</span>
                    <strong>{{ source.name }}</strong>
                    @if (source.fmt) {
                      <span class="tag">{{ source.fmt }}</span>
                    }
                  </div>
                  <code class="path">{{ source.path }}</code>
                  <div class="small muted">
                    {{ source.profile.columns?.length ?? 0 }} colunas
                  </div>
                </div>
              </label>
            }
          </div>
        }
      </div>

      <div class="grid-2">
        <label class="field">
          <span>3. Configuração de IA</span>
          <select [(ngModel)]="aiConfigId">
            <option [ngValue]="null">Sem IA (só etapas determinísticas)</option>
            @for (config of configs(); track config.id) {
              <option [ngValue]="config.id">
                {{ config.name }} — {{ config.model }}
              </option>
            }
          </select>
        </label>

        <label class="field">
          <span>Variável-alvo <em class="muted">(opcional)</em></span>
          <input
            [(ngModel)]="targetVariable"
            list="columns"
            placeholder="Ex.: Churn"
          />
          <datalist id="columns">
            @for (col of availableColumns(); track col) {
              <option [value]="col"></option>
            }
          </datalist>
        </label>
      </div>

      <label class="checkbox">
        <input type="checkbox" [(ngModel)]="adaptive" />
        <span>
          <strong>Checklist adaptativo</strong>
          <span class="small muted">
            — depois de cada agente, o planejador reavalia o que ainda falta e pode
            reescrever as próximas etapas com base no que foi descoberto (toda mudança
            fica registrada com o motivo).
          </span>
        </span>
      </label>

      <div class="row">
        <button
          class="btn-primary"
          (click)="create()"
          [disabled]="creating() || !objective.trim() || !selected().length"
        >
          {{ creating() ? 'Montando o checklist…' : 'Gerar checklist' }}
        </button>
        <a class="btn-ghost link" routerLink="/garimpos">Cancelar</a>
      </div>
    </div>
  `,
  styles: [
    `
      .page-head {
        margin-bottom: 22px;
      }
      .page-head p {
        max-width: 680px;
      }
      .label {
        display: block;
        font-size: 12.5px;
        font-weight: 600;
        color: var(--slate-600);
        margin-bottom: 8px;
      }
      .source {
        display: flex;
        gap: 10px;
        align-items: flex-start;
        padding: 12px;
        border: 1px solid var(--slate-200);
        border-radius: var(--radius-sm);
        cursor: pointer;

        input {
          width: auto;
          margin-top: 3px;
        }

        &.on {
          border-color: var(--gold-400);
          background: var(--gold-100);
        }
      }
      .path {
        display: block;
        font-size: 11.5px;
        color: var(--slate-500);
        word-break: break-all;
        margin: 2px 0 3px;
      }
      .link {
        display: inline-flex;
        align-items: center;
        padding: 8px 14px;
        border: 1px solid var(--slate-200);
        border-radius: var(--radius-sm);
        color: var(--slate-600);
        font-weight: 600;
      }
      em {
        font-style: normal;
      }
    `,
  ],
})
export class RunNewComponent {
  private api = inject(ApiService);
  private router = inject(Router);

  sources = signal<DataSource[]>([]);
  configs = signal<AiConfig[]>([]);
  selected = signal<string[]>([]);
  objective = '';
  targetVariable = '';
  aiConfigId: string | null = null;
  adaptive = true;
  creating = signal(false);
  error = signal('');

  availableColumns = computed(() => {
    const chosen = this.selected();
    const columns = new Set<string>();
    for (const source of this.sources()) {
      if (chosen.includes(source.id)) {
        for (const col of source.profile.columns ?? []) {
          columns.add(col);
        }
      }
    }
    return [...columns];
  });

  constructor() {
    this.api.sources().subscribe({
      next: (list) => this.sources.set(list),
      error: (err) => this.error.set(err?.error?.detail ?? 'Falha ao carregar fontes.'),
    });
    this.api.aiConfigs().subscribe({
      next: (list) => {
        this.configs.set(list);
        this.aiConfigId = list.find((c) => c.is_default)?.id ?? list[0]?.id ?? null;
      },
      error: () => undefined,
    });
  }

  toggle(id: string): void {
    this.selected.update((list) =>
      list.includes(id) ? list.filter((s) => s !== id) : [...list, id],
    );
  }

  create(): void {
    this.creating.set(true);
    this.error.set('');
    this.api
      .createRun({
        objective: this.objective.trim(),
        source_ids: this.selected(),
        ai_config_id: this.aiConfigId,
        target_variable: this.targetVariable.trim() || null,
        adaptive_checklist: this.adaptive,
      })
      .subscribe({
        next: (run) => {
          this.creating.set(false);
          this.router.navigate(['/garimpos', run.id]);
        },
        error: (err) => {
          this.error.set(err?.error?.detail ?? 'Não foi possível criar o garimpo.');
          this.creating.set(false);
        },
      });
  }
}
