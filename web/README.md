# DyPol.ai — web

Next.js 15 (App Router) + React 19 + TypeScript + Tailwind v4 port of the original
static `index.html` and `home.html` design.

## Stack

| Concern        | Choice                                              |
|----------------|-----------------------------------------------------|
| Framework      | Next.js 15 (App Router, Turbopack dev)              |
| Language       | TypeScript (strict, `noUncheckedIndexedAccess`)     |
| Styling        | Tailwind CSS v4 (CSS-first config via `@theme`)     |
| Fonts          | `next/font/google` (Inter, Instrument Serif, JetBrains Mono) |
| Linting        | ESLint flat config (`eslint-config-next`)           |
| Formatting     | Prettier + `prettier-plugin-tailwindcss`            |
| Node           | ≥ 20.11                                             |

## Project layout

```
src/
├── app/                       # Next.js App Router
│   ├── layout.tsx             # Root layout — fonts, metadata
│   ├── globals.css            # Design tokens (@theme), legacy CSS classes
│   ├── page.tsx               # /  — marketing landing
│   └── dashboard/page.tsx     # /dashboard — product shell ("Engineering pulse")
├── components/
│   ├── marketing/             # Marketing sections (Hero, Pricing, FAQ, …)
│   └── app/                   # Product shell (Sidebar, Topbar, Drawer, views/)
└── lib/
    ├── fonts.ts               # next/font setup, exports CSS variables
    ├── cn.ts                  # tiny classnames helper
    ├── useReveal.ts           # IntersectionObserver scroll-reveal
    └── app/                   # Mock data, types, hooks for /app
```

Routes:

- `/` — marketing landing page (port of `index.html`).
- `/dashboard` — product shell, multiple views switched in-page by client state.

## Scripts

```bash
npm install
npm run dev          # Next dev server (Turbopack) on :3000
npm run build        # production build
npm run start        # production server
npm run typecheck    # tsc --noEmit
npm run lint         # next lint
npm run format       # Prettier write
```

## Design tokens

Brand tokens live in `src/app/globals.css`:

- `@theme { --color-* }` declarations expose Tailwind utilities
  (`bg-bg`, `text-ink`, `border-hairline`, `font-serif`, …).
- `:root` and `html.dark` define the CSS variables (`var(--ink)`,
  `var(--accent)`, …) used by the legacy class names ported from the
  source HTML.

Theme toggle stores user preference in `localStorage` under `pulse-theme`.

## Notes

- Mock data (devs, repos, ask answers) lives in `src/lib/app/data.ts`.
  Swap for a real API by replacing those exports (`DEVS`, `REPOS`,
  `ASK_ANSWERS`).
- The Ask Anything view streams a faked response with a tool trace —
  the imperative DOM manipulation lives inside `AskView` (intentional,
  for fidelity with the original streaming UX).
- Sign-in modal currently routes to `/dashboard` after a fake auth trace.
  The route is named `/dashboard` (not `/app`) because Next.js 15.5's page
  collector mis-resolves a route folder named `app/` nested inside the App
  Router root.
  Wire the GitHub OAuth flow into `SignInModal.startAuth`.
