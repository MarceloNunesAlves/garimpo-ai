import { Component, computed, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import {
  AGENT_ICONS,
  AGENT_LABELS,
  AgentKind,
  ChecklistItem,
  ChecklistItemInput,
} from '../core/models';
import { StatusChipComponent } from './status-chip.component';

const AGENTS: AgentKind[] = ['load', 'wrangle', 'clean', 'feature', 'eda', 'viz'];

/**
 * O checklist que o time de agentes segue. É montado antes da execução, o
 * usuário pode ajustar, e o planejador pode reescrever os itens pendentes entre
 * as etapas — quando isso acontece o item mostra o motivo da mudança.
 */
@Component({
  selector: 'gm-checklist',
  standalone: true,
  imports: [FormsModule, StatusChipComponent],
  template: `
    <div class="card">
      <div class="card-head">
        <div>
          <h2>Checklist da execução</h2>
          <span class="small muted">
            revisão {{ revision() }} · {{ doneCount() }}/{{ items().length }} concluídos
          </span>
        </div>
        @if (editable()) {
          @if (editing()) {
            <div class="row">
              <button class="btn-ghost btn-sm" (click)="cancel()">Cancelar</button>
              <button class="btn-primary btn-sm" (click)="save()">Salvar checklist</button>
            </div>
          } @else {
            <button class="btn-ghost btn-sm" (click)="edit()">Ajustar</button>
          }
        }
      </div>

      @if (!editing()) {
        <ol class="list">
          @for (item of items(); track item.id) {
            <li [class]="item.status">
              <span class="marker">
                @switch (item.status) {
                  @case ('done') { ✓ }
                  @case ('failed') { ! }
                  @case ('running') { ● }
                  @default { {{ $index + 1 }} }
                }
              </span>
              <div class="content">
                <div class="row">
                  <span class="icon">{{ icon(item.agent) }}</span>
                  <strong>{{ item.title }}</strong>
                  <span class="tag">{{ item.agent }}</span>
                  <span class="spacer"></span>
                  <gm-status-chip [status]="item.status" />
                </div>
                @if (item.instructions) {
                  <p class="small muted instr">{{ item.instructions }}</p>
                }
                @if (item.origin === 'revision' && item.rationale) {
                  <p class="small revised">
                    <strong>Plano ajustado:</strong> {{ item.rationale }}
                  </p>
                } @else if (item.origin === 'user') {
                  <p class="small muted">Item definido manualmente por você.</p>
                }
              </div>
            </li>
          }
        </ol>
      } @else {
        <div class="editor">
          @for (draft of drafts(); track $index) {
            <div class="draft">
              <div class="row">
                <select [(ngModel)]="draft.agent">
                  @for (agent of agents; track agent) {
                    <option [value]="agent">{{ label(agent) }}</option>
                  }
                </select>
                <input [(ngModel)]="draft.title" placeholder="Título da etapa" />
                <button class="btn-quiet" (click)="remove($index)" title="Remover">✕</button>
              </div>
              <textarea
                [(ngModel)]="draft.instructions"
                rows="2"
                placeholder="Instrução para o agente: o que fazer, em qual coluna, com qual critério"
              ></textarea>
            </div>
          }
          <button class="btn-ghost btn-sm" (click)="add()">+ Adicionar etapa</button>
          <p class="small muted">
            Etapas já concluídas não aparecem aqui — elas ficam preservadas com seus
            checkpoints.
          </p>
        </div>
      }
    </div>
  `,
  styles: [
    `
      .list {
        list-style: none;
        margin: 0;
        padding: 8px 0;
      }

      li {
        display: flex;
        gap: 12px;
        padding: 12px 20px;
        border-bottom: 1px solid var(--slate-100);

        &:last-child {
          border-bottom: none;
        }
        &.done .marker {
          background: var(--ok-bg);
          color: var(--ok);
          border-color: #b8e3cd;
        }
        &.running .marker {
          background: var(--info-bg);
          color: var(--info);
          border-color: #bcd8f2;
          animation: gm-pulse 1.4s ease-in-out infinite;
        }
        &.failed .marker {
          background: var(--err-bg);
          color: var(--err);
          border-color: #f0b9b9;
        }
      }

      .marker {
        flex: none;
        width: 24px;
        height: 24px;
        border-radius: 50%;
        border: 1px solid var(--slate-200);
        background: #fff;
        color: var(--slate-500);
        display: grid;
        place-items: center;
        font-size: 12px;
        font-weight: 700;
        margin-top: 1px;
      }

      .content {
        flex: 1;
        min-width: 0;
      }
      .icon {
        font-size: 15px;
      }
      .instr {
        margin: 3px 0 0;
      }

      .revised {
        margin: 6px 0 0;
        padding: 6px 10px;
        background: var(--gold-100);
        border-radius: var(--radius-sm);
        color: #6b4a08;
      }

      .editor {
        padding: 16px 20px;
        display: flex;
        flex-direction: column;
        gap: 12px;
      }

      .draft {
        border: 1px solid var(--slate-200);
        border-radius: var(--radius-sm);
        padding: 10px;
        display: flex;
        flex-direction: column;
        gap: 8px;

        select {
          max-width: 210px;
        }
      }
    `,
  ],
})
export class ChecklistComponent {
  items = input.required<ChecklistItem[]>();
  revision = input(1);
  editable = input(false);
  changed = output<ChecklistItemInput[]>();

  agents = AGENTS;
  editing = signal(false);
  drafts = signal<ChecklistItemInput[]>([]);

  doneCount = computed(() => this.items().filter((i) => i.status === 'done').length);

  icon(agent: AgentKind): string {
    return AGENT_ICONS[agent] ?? '•';
  }

  label(agent: AgentKind): string {
    return `${AGENT_ICONS[agent]} ${AGENT_LABELS[agent]}`;
  }

  edit(): void {
    this.drafts.set(
      this.items()
        .filter((i) => i.status !== 'done')
        .map((i) => ({ agent: i.agent, title: i.title, instructions: i.instructions })),
    );
    this.editing.set(true);
  }

  add(): void {
    this.drafts.update((list) => [
      ...list,
      { agent: 'eda', title: 'Nova etapa', instructions: '' },
    ]);
  }

  remove(index: number): void {
    this.drafts.update((list) => list.filter((_, i) => i !== index));
  }

  cancel(): void {
    this.editing.set(false);
  }

  save(): void {
    const items = this.drafts().filter((d) => d.title.trim());
    if (items.length) {
      this.changed.emit(items);
    }
    this.editing.set(false);
  }
}
