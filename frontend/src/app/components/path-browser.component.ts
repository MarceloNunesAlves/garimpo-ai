import { Component, inject, input, output, signal } from '@angular/core';
import { DecimalPipe } from '@angular/common';

import { ApiService } from '../core/api.service';
import { BrowseEntry, BrowseResult } from '../core/models';

/**
 * Seletor de caminho no servidor. O usuário escolhe um arquivo ou um diretório
 * inteiro — o Garimpo guarda só o caminho, nada é enviado nem copiado.
 */
@Component({
  selector: 'gm-path-browser',
  standalone: true,
  imports: [DecimalPipe],
  template: `
    <div class="backdrop" (click)="closed.emit()"></div>
    <div class="modal card">
      <div class="card-head">
        <div>
          <h2>Selecionar caminho</h2>
          <span class="small muted">O arquivo permanece onde está — nada é copiado.</span>
        </div>
        <button class="btn-quiet" (click)="closed.emit()">✕</button>
      </div>

      <div class="bar">
        <button class="btn-ghost btn-sm" [disabled]="!current()?.parent" (click)="up()">
          ↑ Subir
        </button>
        <input
          class="path"
          [value]="current()?.path ?? ''"
          (keyup.enter)="go($any($event.target).value)"
          placeholder="/caminho/para/os/dados"
        />
        <button class="btn-ghost btn-sm" (click)="reload()">Ir</button>
      </div>

      @if (error()) {
        <div class="alert err">{{ error() }}</div>
      }

      <div class="list">
        @if (loading()) {
          <p class="empty small pulse">Lendo diretório…</p>
        } @else {
          @for (entry of current()?.entries ?? []; track entry.path) {
            <div class="row entry" (click)="entry.is_dir ? go(entry.path) : select(entry.path)">
              <span class="icon">{{ entry.is_dir ? '📁' : '📄' }}</span>
              <span class="name">{{ entry.name }}</span>
              @if (entry.fmt) {
                <span class="tag">{{ entry.fmt }}</span>
              }
              <span class="spacer"></span>
              @if (entry.size !== null) {
                <span class="small muted">{{ entry.size! / 1024 | number: '1.0-0' }} KB</span>
              }
              @if (!entry.is_dir) {
                <button class="btn-primary btn-sm" (click)="select(entry.path); $event.stopPropagation()">
                  Usar
                </button>
              }
            </div>
          } @empty {
            <p class="empty small">Nenhum arquivo tabular neste diretório.</p>
          }
        }
      </div>

      <div class="foot">
        <span class="small muted">
          Também é possível usar o diretório inteiro como fonte (todos os arquivos
          tabulares são concatenados).
        </span>
        <button class="btn-ghost btn-sm" (click)="select(current()?.path ?? '')">
          Usar este diretório
        </button>
      </div>
    </div>
  `,
  styles: [
    `
      .backdrop {
        position: fixed;
        inset: 0;
        background: rgba(16, 20, 28, 0.45);
        z-index: 40;
      }

      .modal {
        position: fixed;
        z-index: 41;
        top: 6vh;
        left: 50%;
        transform: translateX(-50%);
        width: min(760px, 92vw);
        max-height: 84vh;
        display: flex;
        flex-direction: column;
        box-shadow: var(--shadow);
      }

      .bar {
        display: flex;
        gap: 8px;
        padding: 12px 18px;
        border-bottom: 1px solid var(--slate-100);
      }

      .path {
        font-family: var(--mono);
        font-size: 12.5px;
      }

      .alert {
        margin: 12px 18px 0;
      }

      .list {
        flex: 1;
        overflow-y: auto;
        padding: 6px 0;
      }

      .entry {
        padding: 7px 18px;
        cursor: pointer;

        &:hover {
          background: var(--slate-50);
        }
      }

      .name {
        font-size: 13.5px;
      }

      .foot {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 14px;
        padding: 12px 18px;
        border-top: 1px solid var(--slate-100);
      }
    `,
  ],
})
export class PathBrowserComponent {
  private api = inject(ApiService);

  startPath = input<string | null>(null);
  picked = output<string>();
  closed = output<void>();

  current = signal<BrowseResult | null>(null);
  loading = signal(false);
  error = signal('');

  constructor() {
    queueMicrotask(() => this.go(this.startPath()));
  }

  go(path: string | null): void {
    this.loading.set(true);
    this.error.set('');
    this.api.browse(path).subscribe({
      next: (result) => {
        this.current.set(result);
        this.loading.set(false);
      },
      error: (err) => {
        this.error.set(err?.error?.detail ?? 'Não foi possível abrir o caminho.');
        this.loading.set(false);
      },
    });
  }

  up(): void {
    this.go(this.current()?.parent ?? null);
  }

  reload(): void {
    this.go(this.current()?.path ?? null);
  }

  select(path: string): void {
    if (path) {
      this.picked.emit(path);
    }
  }

  trackEntry(entry: BrowseEntry): string {
    return entry.path;
  }
}
