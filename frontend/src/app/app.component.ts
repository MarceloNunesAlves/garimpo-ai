import { Component } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

@Component({
  selector: 'gm-root',
  standalone: true,
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  template: `
    <div class="shell">
      <aside>
        <div class="brand">
          <span class="pick">⛏️</span>
          <div>
            <strong>Garimpo<span class="dot">.ai</span></strong>
            <small>dados que viram ouro</small>
          </div>
        </div>

        <nav>
          <a routerLink="/garimpos" routerLinkActive="active">
            <span>🏠</span> Garimpos
          </a>
          <a routerLink="/fontes" routerLinkActive="active"> <span>🗂️</span> Fontes de dados </a>
          <a routerLink="/ia" routerLinkActive="active"> <span>🧠</span> Configuração de IA </a>
        </nav>

        <a class="cta" routerLink="/garimpos/novo">+ Novo garimpo</a>

        <div class="foot small">
          Nenhum arquivo é copiado: o Garimpo lê seus dados direto do caminho de origem.
        </div>
      </aside>

      <main>
        <router-outlet />
      </main>
    </div>
  `,
  styles: [
    `
      .shell {
        display: grid;
        grid-template-columns: 248px 1fr;
        min-height: 100vh;
      }

      aside {
        background: var(--slate-950);
        color: var(--slate-200);
        padding: 22px 16px;
        display: flex;
        flex-direction: column;
        gap: 26px;
        position: sticky;
        top: 0;
        height: 100vh;
      }

      .brand {
        display: flex;
        align-items: center;
        gap: 11px;

        .pick {
          font-size: 26px;
        }

        strong {
          display: block;
          font-size: 17px;
          color: #fff;
          letter-spacing: -0.02em;
        }

        .dot {
          color: var(--gold-400);
        }

        small {
          color: var(--slate-500);
          font-size: 11.5px;
        }
      }

      nav {
        display: flex;
        flex-direction: column;
        gap: 3px;

        a {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 9px 12px;
          border-radius: var(--radius-sm);
          color: var(--slate-400);
          font-weight: 550;
          font-size: 13.5px;
          transition: background 0.15s, color 0.15s;

          &:hover {
            background: var(--slate-900);
            color: #fff;
          }

          &.active {
            background: var(--slate-800);
            color: #fff;
            box-shadow: inset 3px 0 0 var(--gold-400);
          }
        }
      }

      .cta {
        display: block;
        text-align: center;
        padding: 10px;
        border-radius: var(--radius-sm);
        background: var(--gold-500);
        color: #fff;
        font-weight: 650;
        font-size: 13.5px;

        &:hover {
          background: var(--gold-400);
        }
      }

      .foot {
        margin-top: auto;
        color: var(--slate-600);
        line-height: 1.45;
      }

      main {
        padding: 28px 32px 64px;
        max-width: 1320px;
        width: 100%;
      }

      @media (max-width: 900px) {
        .shell {
          grid-template-columns: 1fr;
        }
        aside {
          position: static;
          height: auto;
        }
        main {
          padding: 20px 16px 48px;
        }
      }
    `,
  ],
})
export class AppComponent {}
