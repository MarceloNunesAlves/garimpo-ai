import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'garimpos' },
  {
    path: 'garimpos',
    title: 'Garimpos · Garimpo.ai',
    loadComponent: () =>
      import('./pages/dashboard.component').then((m) => m.DashboardComponent),
  },
  {
    path: 'garimpos/novo',
    title: 'Novo garimpo · Garimpo.ai',
    loadComponent: () =>
      import('./pages/run-new.component').then((m) => m.RunNewComponent),
  },
  {
    path: 'garimpos/:id',
    title: 'Execução · Garimpo.ai',
    loadComponent: () =>
      import('./pages/run-detail.component').then((m) => m.RunDetailComponent),
  },
  {
    path: 'fontes',
    title: 'Fontes de dados · Garimpo.ai',
    loadComponent: () =>
      import('./pages/sources.component').then((m) => m.SourcesComponent),
  },
  {
    path: 'ia',
    title: 'Configuração de IA · Garimpo.ai',
    loadComponent: () =>
      import('./pages/ai-settings.component').then((m) => m.AiSettingsComponent),
  },
  { path: '**', redirectTo: 'garimpos' },
];
