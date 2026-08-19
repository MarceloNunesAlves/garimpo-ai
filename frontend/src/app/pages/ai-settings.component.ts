import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { ApiService } from '../core/api.service';
import { AiConfig, AiConfigInput } from '../core/models';

const BLANK: AiConfigInput = {
  name: '',
  provider: 'anthropic',
  model: 'claude-opus-5',
  api_key: '',
  base_url: '',
  max_tokens: 16000,
  temperature: null,
  is_default: true,
};

@Component({
  selector: 'gm-ai-settings',
  standalone: true,
  imports: [FormsModule],
  template: `
    <header class="page-head">
      <div>
        <h1>Configuração de IA</h1>
        <p class="muted">
          Provedor e modelo ficam salvos no banco do Garimpo (SQLite por padrão), não em
          variáveis de ambiente. Dá para manter várias configurações e escolher uma por
          garimpo.
        </p>
      </div>
    </header>

    @if (error()) {
      <div class="alert err">{{ error() }}</div>
    }

    <div class="layout">
      <div class="card">
        <div class="card-head">
          <h2>{{ editingId() ? 'Editar configuração' : 'Nova configuração' }}</h2>
          @if (editingId()) {
            <button class="btn-ghost btn-sm" (click)="reset()">Nova</button>
          }
        </div>
        <div class="card-pad">
          <label class="field">
            <span>Nome</span>
            <input [(ngModel)]="form.name" placeholder="Ex.: Claude produção" />
          </label>

          <label class="field">
            <span>Provedor</span>
            <select [(ngModel)]="form.provider" (ngModelChange)="onProvider($event)">
              <option value="anthropic">Anthropic (Claude)</option>
              <option value="openai">OpenAI</option>
              <option value="ollama">Ollama (local)</option>
            </select>
          </label>

          <label class="field">
            <span>Modelo</span>
            <input [(ngModel)]="form.model" list="models" />
            <datalist id="models">
              @for (model of models(); track model) {
                <option [value]="model"></option>
              }
            </datalist>
          </label>

          @if (form.provider !== 'ollama') {
            <label class="field">
              <span>
                Chave de API
                @if (editingId() && currentHasKey()) {
                  <em class="muted">(deixe em branco para manter a atual)</em>
                }
              </span>
              <input type="password" [(ngModel)]="form.api_key" placeholder="sk-… / anthropic key" />
            </label>
          }

          <label class="field">
            <span>Base URL <em class="muted">(opcional — proxy, gateway ou Ollama)</em></span>
            <input [(ngModel)]="form.base_url" placeholder="http://localhost:11434" />
          </label>

          <div class="grid-2">
            <label class="field">
              <span>Máximo de tokens de saída</span>
              <input type="number" [(ngModel)]="form.max_tokens" min="1024" step="1024" />
            </label>
            @if (form.provider === 'openai' || form.provider === 'ollama') {
              <label class="field">
                <span>Temperatura <em class="muted">(opcional)</em></span>
                <input type="number" [(ngModel)]="form.temperature" min="0" max="2" step="0.1" />
              </label>
            }
          </div>

          @if (form.provider === 'anthropic') {
            <p class="alert info small">
              Modelos Claude atuais não aceitam <code>temperature</code>, e o padrão de 1024
              tokens de saída truncaria o código gerado pelos agentes — por isso o limite
              acima começa em 16000.
            </p>
          }

          <label class="checkbox">
            <input type="checkbox" [(ngModel)]="form.is_default" />
            <span>Usar como configuração padrão dos novos garimpos</span>
          </label>

          <div class="row" style="margin-top:16px">
            <button class="btn-primary" (click)="save()" [disabled]="saving() || !form.name">
              {{ saving() ? 'Salvando…' : editingId() ? 'Salvar alterações' : 'Adicionar' }}
            </button>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-head"><h2>Configurações salvas</h2></div>
        @for (config of configs(); track config.id) {
          <div class="item">
            <div class="row">
              <strong>{{ config.name }}</strong>
              @if (config.is_default) {
                <span class="chip ok">padrão</span>
              }
              <span class="spacer"></span>
              <button class="btn-ghost btn-sm" (click)="test(config)">Testar</button>
              <button class="btn-ghost btn-sm" (click)="edit(config)">Editar</button>
              <button class="btn-quiet" (click)="remove(config)">🗑</button>
            </div>
            <div class="small muted">
              <span class="tag">{{ config.provider }}</span>
              {{ config.model }} · {{ config.max_tokens }} tokens
              @if (!config.has_api_key && config.provider !== 'ollama') {
                · <span class="warn-text">sem chave de API</span>
              }
            </div>
            @if (results()[config.id]; as result) {
              <div class="alert small" [class.err]="!result.ok" [class.info]="result.ok">
                {{ result.ok ? 'Conexão OK: ' + result.reply : result.error }}
              </div>
            }
          </div>
        } @empty {
          <p class="empty small">
            Nenhuma configuração ainda. Sem IA o Garimpo só executa as etapas
            determinísticas (carga e exploração).
          </p>
        }
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
      .layout {
        display: grid;
        grid-template-columns: minmax(320px, 460px) 1fr;
        gap: 20px;
        align-items: start;
      }
      @media (max-width: 980px) {
        .layout {
          grid-template-columns: 1fr;
        }
      }
      .item {
        padding: 14px 20px;
        border-bottom: 1px solid var(--slate-100);

        &:last-child {
          border-bottom: none;
        }
      }
      .warn-text {
        color: var(--warn);
      }
      em {
        font-style: normal;
        font-weight: 400;
      }
      .alert.small {
        margin-top: 8px;
      }
    `,
  ],
})
export class AiSettingsComponent {
  private api = inject(ApiService);

  configs = signal<AiConfig[]>([]);
  models = signal<string[]>([]);
  modelsByProvider = signal<Record<string, string[]>>({});
  results = signal<Record<string, { ok: boolean; reply?: string; error?: string }>>({});
  editingId = signal<string | null>(null);
  saving = signal(false);
  error = signal('');
  form: AiConfigInput = { ...BLANK };

  constructor() {
    this.load();
    this.api.providers().subscribe({
      next: (data) => {
        this.modelsByProvider.set(data.models);
        this.models.set(data.models[this.form.provider] ?? []);
      },
      error: () => undefined,
    });
  }

  private load(): void {
    this.api.aiConfigs().subscribe({
      next: (list) => this.configs.set(list),
      error: (err) =>
        this.error.set(err?.error?.detail ?? 'Não foi possível carregar as configurações.'),
    });
  }

  currentHasKey(): boolean {
    return this.configs().find((c) => c.id === this.editingId())?.has_api_key ?? false;
  }

  onProvider(provider: string): void {
    this.models.set(this.modelsByProvider()[provider] ?? []);
    const first = this.models()[0];
    if (first) {
      this.form.model = first;
    }
    if (provider === 'anthropic') {
      this.form.temperature = null;
    }
  }

  save(): void {
    this.saving.set(true);
    this.error.set('');
    const payload: AiConfigInput = {
      ...this.form,
      base_url: this.form.base_url || null,
      api_key: this.form.api_key || null,
    };
    const id = this.editingId();
    const request = id
      ? this.api.updateAiConfig(id, payload)
      : this.api.createAiConfig(payload);

    request.subscribe({
      next: () => {
        this.saving.set(false);
        this.reset();
        this.load();
      },
      error: (err) => {
        this.error.set(err?.error?.detail ?? 'Falha ao salvar.');
        this.saving.set(false);
      },
    });
  }

  edit(config: AiConfig): void {
    this.editingId.set(config.id);
    this.models.set(this.modelsByProvider()[config.provider] ?? []);
    this.form = {
      name: config.name,
      provider: config.provider,
      model: config.model,
      api_key: '',
      base_url: config.base_url ?? '',
      max_tokens: config.max_tokens,
      temperature: config.temperature,
      is_default: config.is_default,
    };
  }

  reset(): void {
    this.editingId.set(null);
    this.form = { ...BLANK };
  }

  test(config: AiConfig): void {
    this.results.update((map) => ({ ...map, [config.id]: { ok: false, error: 'testando…' } }));
    this.api.testAiConfig(config.id).subscribe({
      next: (result) => this.results.update((map) => ({ ...map, [config.id]: result })),
      error: (err) =>
        this.results.update((map) => ({
          ...map,
          [config.id]: { ok: false, error: err?.error?.detail ?? 'Falha no teste.' },
        })),
    });
  }

  remove(config: AiConfig): void {
    if (!confirm(`Excluir a configuração "${config.name}"?`)) {
      return;
    }
    this.api.deleteAiConfig(config.id).subscribe({
      next: () => this.load(),
      error: (err) => this.error.set(err?.error?.detail ?? 'Falha ao excluir.'),
    });
  }
}
