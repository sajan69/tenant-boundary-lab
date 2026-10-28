# Browser client

The React workspace supports login/logout, organization selection, ticket filtering/pagination, detail/edit forms, comments and JSON downloads. Viewer controls are read-only; editor controls follow the selected organization's role. The API remains authoritative even when a caller bypasses the interface or a membership changes. Status filters and pagination affect the visible list; JSON downloads contain the full bounded selected-tenant report, including records outside that visible filter/page.

## Run the built client

Use Node.js 24.22+ within the 24 LTS line, in addition to the Python/PostgreSQL setup in the README. Runtime dependencies are pinned to React/React DOM 19.3.1; the local build tool is Vite 8.3.5. No CDN, external account or frontend environment secret is used.

Keep the API running on `127.0.0.1:8000` with ordinary request-role settings. In a second terminal:

```sh
npm ci --prefix frontend --ignore-scripts
npm run build --prefix frontend
npm run preview --prefix frontend
```

Open `http://127.0.0.1:4173/`. Use the seeded usernames and `BOUNDARY_DEMO_PASSWORD` from the local setup. Do not put passwords in frontend source or a `VITE_` variable. `npm run dev --prefix frontend` provides a development server on `127.0.0.1:5173` instead; the built preview is the reproducible browser-test target.

Both servers bind to loopback with fixed ports and refuse fallback ports. A fixed `/api/` proxy targets only `http://127.0.0.1:8000`, preserving Host and Origin rather than changing backend CSRF/CORS rules. The browser sees a single origin and uses same-origin credentials. These two local processes are a lab arrangement, not a production hosting configuration. Do not expose or tunnel either server publicly.

## State and rendering

The CSRF token remains in module memory, refreshed from the session/login responses; cookies are HTTP-only and managed by the browser. There is no localStorage/sessionStorage persistence, offline/service-worker cache, telemetry or automatic write retry. Reloading obtains the current session from the API. Expired sessions return to sign-in and clear record state.

Organization/user boundaries unmount their record views and abort pending reads/actions. Each read also checks its lifetime before applying a response, so an old organization response cannot replace the new organization's list. Filter/page changes cancel obsolete reads. Signing out removes the workspace while the request is pending. On an access denial, the client clears visible records and asks for refreshed access. Revocation remains subject to the server's documented statement-level timing limits.

Aborting a browser request does not prove a server-side write was canceled. Reload the affected organization before retrying an uncertain mutation; the API has no idempotency key or optimistic version check. Edits are last-write-wins. Neither interface state nor hidden buttons are authorization controls.

Labels and comments render as React text, without HTML interpolation. The built preview sends a self-only CSP, no framing, no form navigation, no-referrer, nosniff and no-store headers. Vite's development mode uses its normal HMR behavior and does not claim the built preview's CSP. API responses retain their own restrictive headers. Other local processes/browser extensions and a compromised client/server remain outside this lab's isolation claim.

## Browser verification

After a fresh disposable setup with both API and built preview running, install Chromium and run:

```sh
npx --prefix frontend playwright install --with-deps chromium
npm run test:browser --prefix frontend
```

The test shell must also have the local PostgreSQL fixture environment loaded. Serial tests use a privileged fixture helper to revoke/restore only Sam's synthetic Harbor membership and remove the synthetic ticket they create. Do not run these against a live/shared application. The helper is a local test script, never an HTTP endpoint or bundled browser code.

Chromium scenarios exercise viewer controls and a forged API write, scoped viewer/editor downloads, delayed old-tenant responses, editor creation/status changes/comments, inert HTML/script labels, status filtering, membership revocation and record clearing, logout/account changes, session expiration, desktop/mobile layout, preview security headers and empty browser storage. The suite restores the seed's two-ticket/one-comment counts. Screenshots and a machine-readable case report are CI artifacts under `tenant-browser`, not committed customer data. These are functional synthetic checks, not an exhaustive security assessment, accessibility certification or production load test.

Official behavior checked 28 October 2026: [React versions](https://react.dev/versions), [Vite server/proxy options](https://vite.dev/config/server-options), [Vite preview options](https://vite.dev/config/preview-options) and [Node.js LTS releases](https://nodejs.org/en/about/previous-releases).
