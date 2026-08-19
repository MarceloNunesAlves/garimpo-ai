import { Component, input } from '@angular/core';
import { DecimalPipe } from '@angular/common';

import { DataPreview } from '../core/models';

@Component({
  selector: 'gm-data-table',
  standalone: true,
  imports: [DecimalPipe],
  template: `
    @if (preview(); as data) {
      <div class="head small muted">
        {{ data.total_rows | number }} linhas × {{ data.total_columns }} colunas — exibindo
        as {{ data.rows.length }} primeiras
      </div>
      <div class="table-wrap">
        <table class="data">
          <thead>
            <tr>
              @for (col of data.columns; track col) {
                <th>
                  {{ col }}
                  <div class="dtype">{{ data.dtypes[col] }}</div>
                </th>
              }
            </tr>
          </thead>
          <tbody>
            @for (row of data.rows; track $index) {
              <tr>
                @for (col of data.columns; track col) {
                  <td [class.null]="row[col] === null || row[col] === undefined">
                    {{ row[col] === null || row[col] === undefined ? '—' : row[col] }}
                  </td>
                }
              </tr>
            }
          </tbody>
        </table>
      </div>
    }
  `,
  styles: [
    `
      .head {
        padding: 0 0 8px;
      }
      .dtype {
        font-family: var(--mono);
        font-size: 10.5px;
        font-weight: 400;
        text-transform: none;
        color: var(--slate-400);
      }
      td.null {
        color: var(--slate-400);
        font-style: italic;
      }
      .table-wrap {
        border: 1px solid var(--slate-200);
        border-radius: var(--radius-sm);
        max-height: 420px;
        overflow: auto;
      }
    `,
  ],
})
export class DataTableComponent {
  preview = input.required<DataPreview | null>();
}
