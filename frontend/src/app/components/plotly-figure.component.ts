import {
  Component,
  ElementRef,
  effect,
  input,
  signal,
  viewChild,
} from '@angular/core';

/**
 * Renderiza a figura Plotly que o agente de visualização produziu.
 * O plotly é carregado sob demanda para não pesar no bundle inicial.
 */
@Component({
  selector: 'gm-plotly-figure',
  standalone: true,
  template: `
    <div #host class="plot"></div>
    @if (error()) {
      <p class="small muted">
        Não foi possível renderizar o gráfico aqui ({{ error() }}). Ele está no
        notebook gerado no final da execução.
      </p>
    }
  `,
  styles: [
    `
      .plot {
        width: 100%;
        min-height: 360px;
      }
    `,
  ],
})
export class PlotlyFigureComponent {
  figure = input.required<any>();
  private host = viewChild.required<ElementRef<HTMLDivElement>>('host');
  error = signal('');

  constructor() {
    effect(() => {
      const spec = this.figure();
      const element = this.host().nativeElement;
      if (!spec) {
        return;
      }
      import('plotly.js-dist-min')
        .then((mod: any) => {
          const plotly = mod.default ?? mod;
          plotly.react(element, spec.data ?? [], spec.layout ?? {}, {
            responsive: true,
            displaylogo: false,
          });
        })
        .catch((err) => this.error.set(String(err?.message ?? err)));
    });
  }
}
