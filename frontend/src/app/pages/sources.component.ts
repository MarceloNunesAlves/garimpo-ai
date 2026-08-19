import { Component, inject, signal } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';

import { ApiService } from '../core/api.service';
import { DataSource, SourceProfile } from '../core/models';
import { PathBrowserComponent } from '../components/path-browser.component';

@Component({
  selector: 'gm-sources',
  standalone: true,
  imports: [DecimalPipe, FormsModule, PathBrowserComponent],
  template: `
    <header class="page-head">
      <div>
        <h1>Fontes de dados</h1>
        <p class="muted">
          Selecione o caminho de um arquivo ou de um diretório inteiro. O Garimpo lê os
          dados de onde eles já estão — sem upload, sem cópia, sem duplicar disco.
        </p>
      </div>
      <button class="btn-primary" (click)="browsing.set(true)">+ Adicionar fonte</button>
    </header>

    @if (error()) {
      <div class="alert err">{{ error() }}</div>
    }

    @if (candidate()) {
      <div class="card card-pad candidate">
        <h2>Confirmar fonte</h2>
        <code class="path">{{ candidate() }}</code>

        <label class="field">
          <span>Nome</span>
          <input [(ngModel)]="candidateName" placeholder="Como você quer chamar esta fonte" />
        </label>

        @if (previewing()) {
          <p class="small muted pulse">Lendo uma amostra…</p>
        } @else if (profile(); as p) {
          @if (p.error) {
            <div class="alert warn">{{ p.error }}</div>
          } @else {
            <p class="small muted">
              {{ p.columns?.length }} colunas · {{ p.files }} arquivo(s) ·
              {{ (p.bytes ?? 0) / 1024 / 1024 | number: '1.0-2' }} MB no disco de origem
            </p>
            <div class="cols">
              @for (col of p.columns ?? []; track col) {
                <span class="tag">{{ col }} <em>{{ p.dtypes?.[col] }}</em></span>
              }
            </div>
          }
        }

        <div class="row">
          <button class="btn-primary" (click)="save()" [disabled]="saving()">
            {{ saving() ? 'Salvando…' : 'Salvar fonte' }}
          </button>
          <button class="btn-ghost" (click)="cancel()">Cancelar</button>
        </div>
      </div>
    }

    <div class="grid-2">
      @for (source of sources(); track source.id) {
        <div class="card card-pad">
          <div class="row">
            <span class="icon">{{ source.kind === 'directory' ? '📁' : '📄' }}</span>
            <strong>{{ source.name }}</strong>
            @if (source.fmt) {
              <span class="tag">{{ source.fmt }}</span>
            }
            <span class="spacer"></span>
            <button class="btn-quiet" (click)="remove(source)" title="Remover da lista">🗑</button>
          </div>
          <code class="path">{{ source.path }}</code>
          @if (source.profile.error) {
            <p class="small alert warn">{{ source.profile.error }}</p>
          } @else {
            <p class="small muted">
              {{ source.profile.columns?.length ?? 0 }} colunas ·
              {{ source.profile.files ?? 1 }} arquivo(s) ·
              {{ (source.profile.bytes ?? 0) / 1024 / 1024 | number: '1.0-2' }} MB
            </p>
            <div class="cols">
              @for (col of (source.profile.columns ?? []).slice(0, 12); track col) {
                <span class="tag">{{ col }}</span>
              }
              @if ((source.profile.columns?.length ?? 0) > 12) {
                <span class="small muted">
                  +{{ (source.profile.columns?.length ?? 0) - 12 }}
                </span>
              }
            </div>
          }
        </div>
      } @empty {
        <div class="card empty">Nenhuma fonte cadastrada ainda.</div>
      }
    </div>

    @if (browsing()) {
      <gm-path-browser
        (picked)="onPicked($event)"
        (closed)="browsing.set(false)"
      />
    }
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
      .page-head p {
        max-width: 620px;
      }
      .candidate {
        margin-bottom: 20px;
        border-color: var(--gold-200);
      }
      .path {
        display: block;
        margin: 6px 0 10px;
        padding: 6px 9px;
        background: var(--slate-50);
        border-radius: 6px;
        word-break: break-all;
        font-size: 12px;
        color: var(--slate-600);
      }
      .cols {
        display: flex;
        flex-wrap: wrap;
        gap: 5px;
        margin-top: 8px;

        em {
          font-style: normal;
          color: var(--slate-400);
          margin-left: 4px;
        }
      }
      .icon {
        font-size: 17px;
      }
    `,
  ],
})
export class SourcesComponent {
  private api = inject(ApiService);

  sources = signal<DataSource[]>([]);
  browsing = signal(false);
  candidate = signal<string | null>(null);
  candidateName = '';
  profile = signal<SourceProfile | null>(null);
  previewing = signal(false);
  saving = signal(false);
  error = signal('');

  constructor() {
    this.load();
  }

  private load(): void {
    this.api.sources().subscribe({
      next: (list) => this.sources.set(list),
      error: (err) =>
        this.error.set(
          err?.error?.detail ?? 'Não foi possível carregar as fontes. Backend no ar?',
        ),
    });
  }

  onPicked(path: string): void {
    this.browsing.set(false);
    this.candidate.set(path);
    this.candidateName = path.split('/').filter(Boolean).pop() ?? path;
    this.previewing.set(true);
    this.profile.set(null);
    this.api.previewSource(path).subscribe({
      next: (profile) => {
        this.profile.set(profile);
        this.previewing.set(false);
      },
      error: (err) => {
        this.profile.set({ error: err?.error?.detail ?? 'Falha ao ler o caminho.' });
        this.previewing.set(false);
      },
    });
  }

  save(): void {
    const path = this.candidate();
    if (!path) {
      return;
    }
    this.saving.set(true);
    this.api.createSource({ path, name: this.candidateName }).subscribe({
      next: (source) => {
        this.sources.update((list) => [source, ...list]);
        this.saving.set(false);
        this.cancel();
      },
      error: (err) => {
        this.error.set(err?.error?.detail ?? 'Não foi possível salvar a fonte.');
        this.saving.set(false);
      },
    });
  }

  cancel(): void {
    this.candidate.set(null);
    this.profile.set(null);
  }

  remove(source: DataSource): void {
    if (!confirm(`Remover "${source.name}" da lista? O arquivo original não é tocado.`)) {
      return;
    }
    this.api.deleteSource(source.id).subscribe({
      next: () => this.sources.update((list) => list.filter((s) => s.id !== source.id)),
      error: (err) => this.error.set(err?.error?.detail ?? 'Falha ao remover.'),
    });
  }
}
