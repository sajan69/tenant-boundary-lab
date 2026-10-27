# Local JSON API

Start the server with ordinary request-role settings after the fresh setup in the README:

```sh
python manage.py check_boundary
python manage.py runserver 127.0.0.1:8000 --noreload
```

In a second shell with the same environment and virtualenv, run `python scripts/demo_api.py`. It calls only `127.0.0.1:8000` (`--port` can select another local port), disables proxy/redirect use and keeps cookies/tokens in memory. It logs in as seeded Alice and Bob, checks their different tenant visibility, verifies denied access/write cases and checks a scoped export. It creates no tickets/comments; login/logout update session/authentication state. It requires the original synthetic seed and prints only verification results, never credentials or session tokens. This is a functional demo, not a benchmark.

## Sessions and CSRF

`GET /api/session/` returns `{"user": null, "csrf_token": "..."}` anonymously or a username object when authenticated. Retain the returned CSRF token and the HTTP-only cookies. All unsafe methods, including login and logout, require `X-CSRFToken` plus the matching cookie. Login rotates the session key and CSRF secret, so use the new token from its response. Logout deletes the server-side session and returns an anonymous session response.

`POST /api/login/` accepts exactly `username` and `password`; `POST /api/logout/` accepts an empty JSON object. Invalid/unknown/inactive-user credentials share a generic 401 response. The default Django authentication backend is used. Login attempts are capped at ten per peer address per 60-second fixed window, counting successes and failures. The table holds at most 1,024 peers and fails closed when full; expired entries are removed. Quotas are process-local, not distributed, and ignore forwarded-peer headers. A 429 response includes `Retry-After: 60` (a conservative upper bound). This protects the small local demo from repeated hashing, not an internet service from abuse.

Every API request checks the restricted database role/configuration before session/auth middleware. API responses use `Cache-Control: no-store`, a restrictive CSP, no-referrer and nosniff. Cross-origin Origin values and `Sec-Fetch-Site: cross-site` are rejected; no CORS is enabled. Local settings accept loopback hostnames. Use a single origin for clients; no public proxy/deployment profile is provided.

## Domain routes

All routes below require an authenticated active user. Tenant IDs in URLs are selectors checked against current active membership. IDs are UUIDs. Nonmembers receive 403; an object absent from an authorized tenant receives the same 404 whether it is missing or belongs elsewhere. Client-supplied user/creator/tenant ownership fields are rejected, not used to select identity.

| Route | Methods | Input / behavior |
| --- | --- | --- |
| `/api/tenants/` | GET | Current user's active memberships: tenant ID, name and role; cap 100, refuse excess. |
| `/api/tenants/TENANT/tickets/` | GET | Paginated current tickets; optional `status=open\|closed`. |
| `/api/tenants/TENANT/tickets/` | POST | Editor only; required `title`, optional `status` (default `open`). |
| `/api/tenants/TENANT/tickets/TICKET/` | GET | One scoped ticket. |
| `/api/tenants/TENANT/tickets/TICKET/` | PATCH | Editor only; one or both of `title`, `status`. |
| `/api/tenants/TENANT/tickets/TICKET/comments/` | GET | Scoped, paginated comments. |
| `/api/tenants/TENANT/tickets/TICKET/comments/` | POST | Editor only; required `body`; parent and author assigned server-side. |
| `/api/tenants/TENANT/export/` | GET | Viewer/editor JSON attachment with selected tenant's current tickets/comments. |

Ticket fields returned are ID, tenant ID, title, status and creation time. Comments return ID, ticket ID, body and creation time. Password hashes, session rows, email addresses and authorization internals are never serialized. UUID ordering is deterministic, not a creation-time ordering.

List responses contain `items`, `limit`, `offset`, `has_more`, `next_offset` and `pagination_limit_reached`. Default limit is 25, maximum 100; offset is 0–10,000. At the offset boundary, `has_more` can be true while `next_offset` is null and the cap flag is true. There is no claim of a complete population beyond that cap. Unknown/duplicate query keys are rejected. Pagination over live edits is not an immutable snapshot.

## Input, exports and errors

Writes require UTF-8 `application/json` (optional UTF-8 charset), at most 65,536 body bytes. Duplicate JSON keys, nonfinite numbers, malformed encodings/JSON, wrong top-level types, unknown fields and invalid values are rejected. Titles are trimmed nonempty text up to 200 characters; comment bodies up to 2,000, permitting line breaks/tabs. Other controls and unpaired surrogates are refused. Status is exactly `open` or `closed`; PATCH must contain at least one allowed field. Raw input values and database exception details are not returned in errors.

Exports refuse more than 1,000 tickets, 2,000 comments or 1 MiB of serialized JSON, with a 413 response instead of truncating. The attachment name is fixed (`tenant-export.json`). It includes current records and a limitation notice, not event history or an atomic multi-query snapshot under concurrent changes. There is no CSV/HTML export. UI consumers must render strings as text.

Errors are JSON objects containing a stable `error` code: 400 invalid input/query, 401 authentication/credentials, 403 CSRF/origin/tenant permission, 404 unavailable route/object, 405 method, 409 write conflict, 413 size/count cap, 415 content type, 429 login quota or 503 database/configuration unavailability. Some framework-level rejections are normalized to `request_failed` without echoing request content. DB failures roll back scoped mutations. Ticket edits are last-write-wins; no version-conflict prevention or audit/event-history claim is made.

The API uses explicit tenant ORM filters as well as the existing RLS scope. Existing [database limitations](SECURITY.md) still apply: the internal user ID must come from authenticated server state, SQL-capable callers can forge custom context, privileged roles bypass RLS, and revocation cannot retract already-running statements. These endpoints expose no membership administration, arbitrary SQL, outbound callbacks or external account integrations.

Django behavior checked 28 October 2026: [CSRF/login rotation](https://docs.djangoproject.com/en/5.2/ref/csrf/), [authentication](https://docs.djangoproject.com/en/5.2/topics/auth/default/) and [database-backed sessions](https://docs.djangoproject.com/en/5.2/topics/http/sessions/).
