import { Component, input } from '@angular/core';
import { DatePipe } from '@angular/common';

import { RunEvent } from '../core/models';

const ICONS: Record<string, string> = {
  'run.created': '✨',
  'run.started': '▶️',
  'run.paused': '⏸️',
  'run.failed': '⛔',
  'run.completed': '🏁',
  'checklist.created': '📋',
  'checklist.revised': '✏️',
  'step.started': '⚙️',
  'step.progress': '…',
  'step.explained': '💡',
  'step.done': '✅',
  'step.failed': '❌',
  'notebook.ready': '📓',
};

@Component({
  selector: 'gm-event-feed',
  standalone: true,
  imports: [DatePipe],
  template: `
    <div class="card feed">
      <div class="card-head">
        <h2>O que está acontecendo</h2>
        @if (live()) {
          <span class="chip run pulse">ao vivo</span>
        }
      </div>
      <div class="scroll">
        @for (event of reversed(); track event.id) {
          <div class="item" [class]="event.level">
            <span class="icon">{{ icon(event.type) }}</span>
            <div>
              <div class="msg">{{ event.message }}</div>
              <div class="small muted">
                {{ event.ts | date: 'HH:mm:ss' }}
                @if (event.agent) {
                  · <span class="tag">{{ event.agent }}</span>
                }
              </div>
            </div>
          </div>
        } @empty {
          <p class="empty small">Nada por aqui ainda.</p>
        }
      </div>
    </div>
  `,
  styles: [
    `
      .scroll {
        max-height: 460px;
        overflow-y: auto;
        padding: 6px 0;
      }

      .item {
        display: flex;
        gap: 10px;
        padding: 9px 18px;
        border-bottom: 1px solid var(--slate-100);

        &:last-child {
          border-bottom: none;
        }
        &.error .msg {
          color: var(--err);
          font-weight: 600;
        }
        &.warning .msg {
          color: var(--warn);
        }
      }

      .icon {
        flex: none;
        width: 20px;
        text-align: center;
      }
      .msg {
        font-size: 13px;
        line-height: 1.45;
      }
    `,
  ],
})
export class EventFeedComponent {
  events = input.required<RunEvent[]>();
  live = input(false);

  reversed = () => [...this.events()].reverse();

  icon(type: string): string {
    return ICONS[type] ?? '•';
  }
}
