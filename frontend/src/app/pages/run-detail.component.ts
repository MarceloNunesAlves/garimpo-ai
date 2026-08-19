import {
  Component,
  DestroyRef,
  OnInit,
  computed,
  inject,
  input,
  signal,
} from '@angular/core';
import { DatePipe } from '@angular/common';
import { RouterLink } from '@angular/router';
import { Observable, Subscription } from 'rxjs';

import { ApiService } from '../core/api.service';
import {
  ChecklistItem,
  ChecklistItemInput,
  RunDetail,
  RunEvent,
  RunStep,
} from '../core/models';
import { ChecklistComponent } from '../components/checklist.component';
import { EventFeedComponent } from '../components/event-feed.component';
import { StepCardComponent } from '../components/step-card.component';
import { StatusChipComponent } from '../components/status-chip.component';

const REFRESH_ON = new Set([
  'step.started',
  'step.done',
  'step.failed',
  'checklist.revised',
  'checklist.created',
  'run.started',
  'run.paused',
  'run.failed',
  'run.completed',
  'notebook.ready',
]);

@Component({
  selector: 'gm-run-detail',
  standalone: true,
  imports: [
    DatePipe,
    RouterLink,
    ChecklistComponent,
    EventFeedComponent,
    StepCardComponent,
    StatusChipComponent,
  ],
  template: `
    @if (run(); as detail) {
      <header class="page-head">
        <div class="head-main">
          <a class="back small muted" routerLink="/garimpos">← Garimpos</a>
          <div class="row">
            <h1>{{ detail.title }}</h1>
            <gm-status-chip [status]="detail.status" />
          </div>
          <p class="muted objective">{{ detail.objective }}</p>
          <div class="row meta small muted">
            @for (source of detail.sources; track source.id) {
              <span class="tag" [title]="source.path">
                {{ source.kind === 'directory' ? '📁' : '📄' }} {{ source.name }}
              </span>
            }
            @if (detail.target_variable) {
              <span>alvo: <code>{{ detail.target_variable }}</code></span>
            }
            <span>criado {{ detail.created_at | date: 'dd/MM HH:mm' }}</span>
            @if (detail.adaptive_checklist) {
              <span title="O planejador pode reescrever as etapas pendentes entre os agentes">
                checklist adaptativo
              </span>
            }
          </div>
        </div>

        <div class="actions">
          @if (detail.status === 'draft') {
            <button class="btn-primary" (click)="start()" [disabled]="busy()">
              ▶ Iniciar garimpo
            </button>
          } @else if (detail.status === 'running') {
            <button class="btn-ghost" (click)="cancel()" [disabled]="busy()">⏸ Pausar</button>
          } @else if (detail.status === 'failed' || detail.status === 'paused') {
            <button class="btn-primary" (click)="resume()" [disabled]="busy()">
              ↻ Retomar de onde parou
            </button>
          }
          @if (detail.notebook_path) {
            <a class="btn-primary link" [href]="notebookUrl()" download>📓 Baixar notebook</a>
          }
        </div>
      </header>

      @if (detail.error) {
        <div class="alert err">
          <strong>Interrompido:</strong> {{ detail.error }}
          <div class="small">
            As etapas já concluídas foram preservadas em disco. Ajuste o checklist se
            necessário e clique em “Retomar de onde parou”.
          </div>
        </div>
      }

      @if (error()) {
        <div class="alert err">{{ error() }}</div>
      }

      @if (detail.status === 'draft') {
        <div class="alert info">
          O checklist abaixo foi montado a partir do seu objetivo e das colunas das fontes.
          Revise, ajuste o que quiser e então inicie — os agentes vão segui-lo na ordem.
        </div>
      }

      <div class="layout">
        <div class="stack">
          <gm-checklist
            [items]="detail.items"
            [revision]="detail.checklist_revision"
            [editable]="!detail.is_running && detail.status !== 'completed'"
            (changed)="saveChecklist($event)"
          />
          <gm-event-feed [events]="events()" [live]="detail.status === 'running'" />
        </div>

        <div class="stack">
          @if (detail.status === 'running') {
            <div class="card card-pad working">
              <span class="spin">⛏️</span>
              <div>
                <strong>{{ currentTitle() }}</strong>
                <div class="small muted">{{ lastMessage() }}</div>
              </div>
            </div>
          }

          @for (step of steps(); track step.id) {
            <gm-step-card
              [runId]="detail.id"
              [step]="step"
              [item]="itemFor(step)"
              [expanded]="$first"
            />
          } @empty {
            <div class="card empty">
              Nenhuma etapa executada ainda. Ao iniciar, cada agente aparece aqui com o
              que fez, o que removeu, o que preencheu — e por quê.
            </div>
          }
        </div>
      </div>
    } @else if (error()) {
      <div class="alert err">{{ error() }}</div>
    } @else {
      <p class="empty pulse">Carregando garimpo…</p>
    }
  `,
  styles: [
    `
      .page-head {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 20px;
        margin-bottom: 18px;
      }
      .back {
        display: inline-block;
        margin-bottom: 6px;
      }
      .objective {
        max-width: 720px;
        margin: 6px 0 8px;
      }
      .meta {
        flex-wrap: wrap;
        gap: 10px;
      }
      .actions {
        display: flex;
        gap: 8px;
        flex: none;
      }
      .link {
        display: inline-flex;
        align-items: center;
        color: #fff;
        padding: 8px 14px;
        border-radius: var(--radius-sm);
        font-weight: 650;
      }
      .alert {
        margin-bottom: 16px;
      }
      .layout {
        display: grid;
        grid-template-columns: minmax(320px, 440px) 1fr;
        gap: 20px;
        align-items: start;
      }
      @media (max-width: 1080px) {
        .layout {
          grid-template-columns: 1fr;
        }
      }
      .working {
        display: flex;
        align-items: center;
        gap: 14px;
        border-color: var(--gold-200);
        background: var(--gold-100);
      }
      .spin {
        font-size: 22px;
        animation: gm-pulse 1.2s ease-in-out infinite;
      }
      code {
        background: var(--slate-100);
        padding: 1px 5px;
        border-radius: 4px;
      }
    `,
  ],
})
export class RunDetailComponent implements OnInit {
  private api = inject(ApiService);
  private destroyRef = inject(DestroyRef);

  /** Vem da rota /garimpos/:id (withComponentInputBinding). */
  id = input.required<string>();

  run = signal<RunDetail | null>(null);
  events = signal<RunEvent[]>([]);
  busy = signal(false);
  error = signal('');

  private stream?: Subscription;
  private refreshTimer?: ReturnType<typeof setTimeout>;

  /** Etapas mais recentes primeiro — o que acabou de rodar fica no topo. */
  steps = computed(() =>
    [...(this.run()?.steps ?? [])].sort(
      (a, b) => new Date(b.started_at).getTime() - new Date(a.started_at).getTime(),
    ),
  );

  currentTitle = computed(() => {
    const item = this.run()?.items.find((i) => i.status === 'running');
    return item ? item.title : 'Preparando a próxima etapa…';
  });

  lastMessage = computed(() => this.events()[this.events().length - 1]?.message ?? '');

  ngOnInit(): void {
    this.reload(true);
    this.destroyRef.onDestroy(() => {
      this.stream?.unsubscribe();
      clearTimeout(this.refreshTimer);
    });
  }

  itemFor(step: RunStep): ChecklistItem | undefined {
    return this.run()?.items.find((i) => i.id === step.item_id);
  }

  notebookUrl(): string {
    return this.api.notebookUrl(this.id());
  }

  private reload(connect = false): void {
    this.api.run(this.id()).subscribe({
      next: (detail) => {
        this.run.set(detail);
        if (connect) {
          this.loadEvents();
          this.connect();
        }
      },
      error: (err) =>
        this.error.set(err?.error?.detail ?? 'Não foi possível carregar a execução.'),
    });
  }

  private loadEvents(): void {
    this.api.events(this.id()).subscribe({
      next: (events) => this.events.set(events),
      error: () => undefined,
    });
  }

  private connect(): void {
    this.stream?.unsubscribe();
    const lastId = this.events()[this.events().length - 1]?.id ?? 0;
    this.stream = this.api.streamEvents(this.id(), lastId).subscribe((event) => {
      this.events.update((list) =>
        list.some((e) => e.id === event.id) ? list : [...list, event],
      );
      if (REFRESH_ON.has(event.type)) {
        // Agrupa rajadas de eventos em um único GET do detalhe.
        clearTimeout(this.refreshTimer);
        this.refreshTimer = setTimeout(() => this.reload(), 250);
      }
    });
  }

  start(): void {
    this.act(this.api.startRun(this.id()));
  }

  resume(): void {
    this.act(this.api.resumeRun(this.id()));
  }

  cancel(): void {
    this.act(this.api.cancelRun(this.id()));
  }

  saveChecklist(items: ChecklistItemInput[]): void {
    this.busy.set(true);
    this.api.replaceChecklist(this.id(), items).subscribe({
      next: (detail) => {
        this.run.set(detail);
        this.busy.set(false);
      },
      error: (err) => {
        this.error.set(err?.error?.detail ?? 'Não foi possível salvar o checklist.');
        this.busy.set(false);
      },
    });
  }

  private act(request: Observable<unknown>): void {
    this.busy.set(true);
    this.error.set('');
    request.subscribe({
      next: () => {
        this.busy.set(false);
        this.reload();
        this.connect();
      },
      error: (err) => {
        this.error.set(err?.error?.detail ?? 'Ação não pôde ser executada.');
        this.busy.set(false);
      },
    });
  }
}
