import { Component, computed, input } from '@angular/core';

const TONE: Record<string, string> = {
  done: 'ok',
  completed: 'ok',
  running: 'run',
  draft: '',
  pending: '',
  paused: 'warn',
  skipped: 'warn',
  failed: 'err',
  canceled: 'err',
};

const LABEL: Record<string, string> = {
  draft: 'rascunho',
  pending: 'pendente',
  running: 'executando',
  done: 'concluída',
  completed: 'concluído',
  paused: 'pausado',
  failed: 'falhou',
  skipped: 'pulada',
  canceled: 'cancelado',
};

@Component({
  selector: 'gm-status-chip',
  standalone: true,
  template: `
    <span class="chip" [class]="tone()" [class.pulse]="status() === 'running'">
      {{ label() }}
    </span>
  `,
})
export class StatusChipComponent {
  status = input.required<string>();
  tone = computed(() => TONE[this.status()] ?? '');
  label = computed(() => LABEL[this.status()] ?? this.status());
}
