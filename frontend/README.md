# TravelMate frontend — FE-01 (#12)

React + Vite + TypeScript frontend owned by Diyar. The Welcome and authentication UI follow Ali’s Riviera sources in `../docs/design/travelmate-des01-welcome-auth.zip`. This is a frontend UI foundation, not a working authenticated travel-planning application.

## Implemented UI and current limits

- **Welcome:** Riviera landing sections, sample postcards, price-label explanations, and links to Signup, Login and the demo entry. Hard-coded prices are marked Sample/Example; they are not live provider data.
- **Login:** email/password fields, password visibility, required/email validation, accessible errors, pending-state controls and navigation to Signup, Forgot Password, Home and Demo.
- **Signup:** display name, email, password and confirmation; a live password-rule checklist; shared password visibility; validation, accessible errors and pending-state controls. Name is a display name, not trip traveler data.
- **Forgot Password:** email validation and a reset-link request form in the centered Riviera layout.
- **Reset Password:** new-password/confirmation validation and password visibility in the same layout.

The auth forms call unconnected service boundaries that immediately reject with an explicit “not connected” message. They do not create accounts, establish sessions, send emails, update passwords or redirect as if authentication succeeded. Loading controls are prepared for future asynchronous integration; no artificial delay or simulated success is added. The current UI password rule is 8+ characters, including a letter and a number; it must be aligned with Adel’s configured Supabase policy before integration.

Trip Planner, Results and Offline Demo are **placeholder pages**. There is no trip form, contract-shaped mock-result renderer, live itinerary, complete offline demo, FastAPI HTTP client or Supabase SDK connection. Mock-result work remains deferred until the Team Leader confirms whether it belongs to FE-01 or FE-02.

## Prerequisites

Use Node.js 22.12 or newer and npm. Development checks were run with Node.js 24.15.0 and npm 11.12.1; the declared minimum version has not been separately tested. Exact dependencies are in `package.json` and `package-lock.json`.

Initial dependency installation requires access to the npm registry unless all required packages are cached. No backend, account, credentials or environment file is needed to view the current UI.

## Install and start

From the repository root (PowerShell, macOS or Linux shell):

```sh
cd frontend
npm ci
npm run dev
```

Open http://localhost:5173. Stop with Ctrl+C. Port 5173 must be free; the command fails instead of silently choosing another port.

If localhost resolution prevents access, bind explicitly to the loopback address:

```sh
npm run dev -- --host 127.0.0.1 --port 5173
```

Then open http://127.0.0.1:5173. Keep the terminal/process running during preview. If the port is occupied, stop the server you own or select a free port:

```sh
npm run dev -- --host 127.0.0.1 --port 5174
```

Use the actual Local URL printed by Vite. These are frontend-only commands; they do not start FastAPI. A combined application launcher is not implemented.

## Environment configuration

`.env.example` contains only an **unused placeholder** for future `VITE_API_BASE_URL` configuration. Do not copy it just to launch the UI. When backend integration is implemented, copy it locally to `.env.local` and replace the placeholder with the agreed public API base URL. There are no Supabase configuration values yet.

All `VITE_*` values are public browser configuration. Never add provider API secrets, access tokens, passwords or service-role keys. Local environment files, dependency folders and generated output are ignored; `.env.example` remains includable. Ignore rules do not protect a secret already committed to Git, so review the delivery diff before staging.

## Checks and production preview

From `frontend/`:

```sh
npm run typecheck
npm run build
npm run preview
```

Build runs strict TypeScript checking and writes production assets to `dist/`. Preview serves them at http://localhost:4173 (port must be free). It requires a successful build first. For a fresh checkout, always run `npm ci` before these commands.

Preview also supports explicit loopback/port overrides:

```sh
npm run preview -- --host 127.0.0.1 --port 4174
```

Open the URL printed by Vite (http://127.0.0.1:4174 for this example). Stop with Ctrl+C. Preview is for inspecting a local production build, not a production deployment. Do not commit `dist/` or `node_modules/`. No automated test or lint script is currently configured; typecheck/build checks do not prove Auth or backend integration.

Verification on 2026-10-15 (Windows, Node.js 24.15.0, npm 11.12.1): a clean `npm ci` succeeded in a temporary directory containing copies of the manifest and lockfile; `npm run typecheck` and `npm run build` passed in the working frontend. Development and preview startup also passed with the documented overrides on ports 5174 and 4174. This is same-machine evidence, not a second-computer handover test.

## Routes

| Path | Current behavior |
| --- | --- |
| `/` | Implemented Riviera Welcome / landing UI |
| `/login` | Implemented Login UI; authentication unconnected |
| `/signup` | Implemented Signup UI; account creation unconnected |
| `/forgot-password` | Implemented reset-link request UI; email delivery unconnected |
| `/reset-password` | Implemented new-password UI; recovery verification/update unconnected |
| `/trip-planner` | Trip Planner placeholder |
| `/results` | Results placeholder; no trip data loaded |
| `/offline-demo` | Explicitly labeled DEMO placeholder; no bundled trips loaded |
| Any other path | Page-not-found placeholder |

Routes are intentionally public while Auth is unconnected; no protected data is present. `/reset-password` is reserved for a future recovery-link destination. Opening that route is not authorization to update credentials; real integration must verify a valid recovery session first. There is no fake link-sent or password-updated screen.

BrowserRouter supports client navigation and direct links through Vite. A future static host must serve `index.html` for application routes.

## Main files and folders

- `src/main.tsx`: React entry point, BrowserRouter and global CSS.
- `src/App.tsx`: route definitions.
- `src/pages/`: implemented Welcome/auth/recovery UI plus planner/results/demo placeholders.
- `src/components/welcome/`: shared Riviera logo, price badges and illustrative postcards.
- `src/components/auth/`: reusable password input and recovery layout/error/submit components.
- `src/components/layout/AppLayout.tsx`: navigation and layout for the remaining placeholders and unknown routes.
- `src/components/PlaceholderPage.tsx`: reusable page content wrapper.
- `src/styles/`: global defaults, shared Riviera/Login styling and scoped Signup/recovery additions.
- `src/services/`: API conventions and unconnected sign-in, signup and recovery boundaries. These make no provider/backend requests and do not log or persist credentials.
- `src/types/`: shared TypeScript types; no speculative API models.
- `src/assets/`: reserved for approved local assets.
- `src/fixtures/`: reserved for future bundled demo examples.
- `vite.config.ts`, `tsconfig.json`: Vite React plugin and strict TypeScript configuration.

## Integration and offline boundaries

Scope follows the repository’s MVP scope and architecture: one destination, 1–4 adults, 1–7 nights, whole-trip USD budget, backend-owned budget calculations, and a separate read-only demo. These trip constraints are not yet implemented as a working planner form. The API v0.4 review candidate is not implicitly adopted by this frontend; confirm the integration baseline with the team before adding response models or API handling.

Supabase configuration, sessions, recovery-link validation, protected routes, FastAPI transport and real results are future integration work. Frontend Live-badge metadata must eventually be derived from trusted provider-sourced backend output and explicit online/demo context; a badge alone is not live-price evidence.

The current pages use local UI assets but request Fraunces/Figtree from Google Fonts. Fallback system/serif fonts are available without that network access. No authentication or travel-provider requests run. Offline Demo is only a labeled entry placeholder, not the FE-03 implementation or a verified offline handover. Complete online/demo operation and second-computer testing remain later work.
