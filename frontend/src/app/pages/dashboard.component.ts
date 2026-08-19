import { Component, computed, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { RouterLink } from '@angular/router';

import { ApiService } from '../core/api.service';
import { RUN_STATUS_LABELS, RunSummary } from '../core/models';
import { StatusChipComponent } from '../components/status-chip.component';

@Component({
  selector: 'gm-dashboard',
  standalone: true,
  imports: [DatePipe, RouterLink, StatusChipComponent],
  template: `
    <header class="page-head">
      <div>
        <h1>Garimpos</h1>
        <p class="muted">
          Cada garimpo é uma jornada de dados: checklist, agentes trabalhando à vista e um
          notebook reprodutível no final.
        </p>
      </div>
      <a class="btn-primary link" routerLink="/garimpos/novo">+ Novo garimpo</a>
    </header>

    @if (error()) {
      <div class="alert err">{{ error() }}</div>
    }

    <div class="stats">
      @for (stat of stats(); track stat.label) {
        <div class="card card-pad stat">
          <strong>{{ stat.value }}</strong>
          <span class="small muted">{{ stat.label }}</span>
        </div>
      }
    </div>

    <div class="card">
      <div class="card-head"><h2>Histórico</h2></div>
      @if (loading()) {
        <p class="empty pulse">Carregando…</p>
      } @else if (!runs().length) {
        <div class="empty">
          <p>Nenhum garimpo ainda.</p>
          <a class="btn-primary link" routerLink="/garimpos/novo">Começar o primeiro</a>
        </div>
      } @else {
        <div class="table-wrap">
          <table class="data">
            <thead>
              <tr>
                <th>Garimpo</th>
                <th>Status</th>
                <th>Revisão</th>
                <th>Criado</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              @for (run of runs(); track run.id) {
                <tr>
                  <td>
                    <a [routerLink]="['/garimpos', run.id]"><strong>{{ run.title }}</strong></a>
                    <div class="small muted objective">{{ run.objective }}</div>
                  </td>
                  <td><gm-status-chip [status]="run.status" /></td>
                  <td class="small muted">v{{ run.checklist_revision }}</td>
                  <td class="small muted">{{ run.created_at | date: 'dd/MM/yy HH:mm' }}</td>
                  <td>
                    <button class="btn-quiet" (click)="remove(run)" title="Excluir">🗑</button>
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      }
    </div>
  `,
  styles: [
    `
      .page-head {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 20px;
        margin-bottom: 22px;
      }
      .link {
        display: inline-block;
        color: #fff;
        padding: 9px 16px;
        border-radius: var(--radius-sm);
        background: var(--gold-500);
        font-weight: 650;
      }
      .stats {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
        gap: 14px;
        margin-bottom: 22px;
      }
      .stat strong {
        display: block;
        font-size: 26px;
        line-height: 1.1;
      }
      .objective {
        white-space: normal;
        max-width: 460px;
      }
    `,
  ],
})
export class DashboardComponent {
  private api = inject(ApiService);

  runs = signal<RunSummary[]>([]);
  loading = signal(true);
  error = signal('');

  stats = computed(() => {
    const all = this.runs();
    const count = (status: string) => all.filter((r) => r.status === status).length;
    return [
      { label: 'garimpos', value: all.length },
      { label: RUN_STATUS_LABELS.completed + 's', value: count('completed') },
      { label: 'em execução', value: count('running') },
      { label: 'a retomar', value: count('failed') + count('paused') },
    ];
  });

  constructor() {
    this.load();
  }

  private load(): void {
    this.loading.set(true);
    this.api.runs().subscribe({
      next: (runs) => {
        this.runs.set(runs);
        this.loading.set(false);
      },
      error: (err) => {
        this.error.set(
          err?.error?.detail ??
            'Não foi possível falar com a API. O backend está rodando em localhost:8000?',
        );
        this.loading.set(false);
      },
    });
  }

  remove(run: RunSummary): void {
    if (!confirm(`Excluir o garimpo "${run.title}"? Os checkpoints em disco são mantidos.`)) {
      return;
    }
    this.api.deleteRun(run.id).subscribe({
      next: () => this.runs.update((list) => list.filter((r) => r.id !== run.id)),
      error: (err) => this.error.set(err?.error?.detail ?? 'Falha ao excluir.'),
    });
  }
}
