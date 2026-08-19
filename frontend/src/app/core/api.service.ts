import { Injectable, NgZone, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

import {
  AiConfig,
  AiConfigInput,
  BrowseResult,
  ChecklistItemInput,
  DataPreview,
  DataSource,
  RunCreate,
  RunDetail,
  RunEvent,
  RunSummary,
  SourceProfile,
} from './models';

const API = '/api';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private http = inject(HttpClient);
  private zone = inject(NgZone);

  // ---- IA -------------------------------------------------------------- //
  providers(): Observable<{ providers: string[]; models: Record<string, string[]> }> {
    return this.http.get<{ providers: string[]; models: Record<string, string[]> }>(
      `${API}/ai-configs/providers`,
    );
  }

  aiConfigs(): Observable<AiConfig[]> {
    return this.http.get<AiConfig[]>(`${API}/ai-configs`);
  }

  createAiConfig(payload: AiConfigInput): Observable<AiConfig> {
    return this.http.post<AiConfig>(`${API}/ai-configs`, payload);
  }

  updateAiConfig(id: string, payload: AiConfigInput): Observable<AiConfig> {
    return this.http.put<AiConfig>(`${API}/ai-configs/${id}`, payload);
  }

  deleteAiConfig(id: string): Observable<void> {
    return this.http.delete<void>(`${API}/ai-configs/${id}`);
  }

  testAiConfig(id: string): Observable<{ ok: boolean; reply?: string; error?: string }> {
    return this.http.post<{ ok: boolean; reply?: string; error?: string }>(
      `${API}/ai-configs/${id}/test`,
      {},
    );
  }

  // ---- fontes ----------------------------------------------------------- //
  browse(path?: string | null, showHidden = false): Observable<BrowseResult> {
    const params: Record<string, string> = { show_hidden: String(showHidden) };
    if (path) {
      params['path'] = path;
    }
    return this.http.get<BrowseResult>(`${API}/sources/browse`, { params });
  }

  sources(): Observable<DataSource[]> {
    return this.http.get<DataSource[]>(`${API}/sources`);
  }

  createSource(payload: {
    path: string;
    name?: string;
    fmt?: string | null;
    options?: Record<string, unknown>;
  }): Observable<DataSource> {
    return this.http.post<DataSource>(`${API}/sources`, payload);
  }

  previewSource(path: string): Observable<SourceProfile> {
    return this.http.post<SourceProfile>(`${API}/sources/preview`, { path });
  }

  deleteSource(id: string): Observable<void> {
    return this.http.delete<void>(`${API}/sources/${id}`);
  }

  // ---- execuções -------------------------------------------------------- //
  runs(): Observable<RunSummary[]> {
    return this.http.get<RunSummary[]>(`${API}/runs`);
  }

  run(id: string): Observable<RunDetail> {
    return this.http.get<RunDetail>(`${API}/runs/${id}`);
  }

  createRun(payload: RunCreate): Observable<RunDetail> {
    return this.http.post<RunDetail>(`${API}/runs`, payload);
  }

  deleteRun(id: string): Observable<void> {
    return this.http.delete<void>(`${API}/runs/${id}`);
  }

  replaceChecklist(id: string, items: ChecklistItemInput[]): Observable<RunDetail> {
    return this.http.put<RunDetail>(`${API}/runs/${id}/checklist`, items);
  }

  startRun(id: string): Observable<RunSummary> {
    return this.http.post<RunSummary>(`${API}/runs/${id}/start`, {});
  }

  resumeRun(id: string): Observable<RunSummary> {
    return this.http.post<RunSummary>(`${API}/runs/${id}/resume`, {});
  }

  cancelRun(id: string): Observable<RunSummary> {
    return this.http.post<RunSummary>(`${API}/runs/${id}/cancel`, {});
  }

  events(id: string, after = 0): Observable<RunEvent[]> {
    return this.http.get<RunEvent[]>(`${API}/runs/${id}/events`, {
      params: { after: String(after) },
    });
  }

  stepData(runId: string, stepId: string, rows = 25): Observable<DataPreview> {
    return this.http.get<DataPreview>(`${API}/runs/${runId}/steps/${stepId}/data`, {
      params: { rows: String(rows) },
    });
  }

  notebookUrl(id: string): string {
    return `${API}/runs/${id}/notebook`;
  }

  /**
   * Fluxo SSE dos eventos da execução. Reemite dentro da zona do Angular para
   * que os signals atualizem a tela sem intervenção manual.
   */
  streamEvents(id: string, after = 0): Observable<RunEvent> {
    return new Observable<RunEvent>((subscriber) => {
      const source = new EventSource(`${API}/runs/${id}/stream?after=${after}`);

      const onMessage = (event: MessageEvent<string>) => {
        try {
          const data = JSON.parse(event.data);
          if (data && typeof data.id === 'number') {
            this.zone.run(() => subscriber.next(data as RunEvent));
          }
        } catch {
          /* eventos de heartbeat não trazem payload de evento */
        }
      };

      // O backend nomeia cada evento pelo `type`, então escutamos o genérico
      // e também os nomeados.
      source.onmessage = onMessage;
      for (const name of [
        'run.started',
        'run.paused',
        'run.failed',
        'run.completed',
        'checklist.created',
        'checklist.revised',
        'step.started',
        'step.progress',
        'step.explained',
        'step.done',
        'step.failed',
        'notebook.ready',
      ]) {
        source.addEventListener(name, onMessage as EventListener);
      }

      source.onerror = () => {
        // O EventSource reconecta sozinho; erro de rede não encerra o fluxo.
      };

      return () => source.close();
    });
  }
}
