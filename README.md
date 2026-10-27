# Tenant Boundary Lab

A Django/PostgreSQL lab for examining authorization boundaries in a multi-tenant support-ticket domain. Application membership checks and database row policies protect synthetic tickets and comments. Tests deliberately omit ORM tenant filters to exercise the database boundary.

## Run locally

Requires Python 3.12+, Docker Compose and a free local port 5432. Django is pinned to 5.2.18 LTS. PostgreSQL 16 and 18 are used by the integration workflow; Compose selects 18.

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
# Inspect the file, then load its disposable local values in this shell:
set -a
. ./.env
set +a
docker compose up -d --wait
bash scripts/verify.sh
```

The verification script creates a fresh `boundary_lab` database and separate `boundary_owner`/`boundary_app` logins, migrates with the owner, seeds synthetic data, checks the restricted request role and runs integration tests. Bootstrap refuses an existing database or either existing role. Use a disposable PostgreSQL instance: the tests temporarily change synthetic memberships and RLS settings to verify failure cases. Run them serially, without a live application sharing this lab database. Dummy credentials in `.env.example` are public local examples, not production settings.

After initial setup, checks can be rerun without bootstrap:

```sh
python manage.py check_boundary
python -m unittest discover -s tests -v
```

The seed contains Cedar and Harbor organizations, two tickets, one comment and these users:

| User | Cedar | Harbor |
| --- | --- | --- |
| alice | editor | no membership |
| bob | no membership | viewer |
| sam | viewer | editor |

Their local password comes from `BOUNDARY_DEMO_PASSWORD`. `seed_demo` refuses nonempty user/organization tables and commits the fixture atomically. To inspect the database using the supported scope helper:

```sh
python manage.py shell
```

```python
from django.contrib.auth import get_user_model
from tickets.boundary import tenant_scope
from tickets.models import Ticket
alice = get_user_model().objects.get(username="alice")
with tenant_scope(alice.id, "11111111-1111-4111-8111-111111111111"):
    print(list(Ticket.objects.values("title", "status")))
# Without a scope, a ticket query returns no rows.
```

## HTTP API

```sh
python manage.py runserver 127.0.0.1:8000 --noreload
# In another shell with the same environment:
python scripts/demo_api.py
```

The JSON API supports database-backed login/logout, current tenant discovery, ticket reads/creation/edits, comments and bounded tenant exports. Login and writes require CSRF protection; tenant membership and viewer/editor permissions are checked server-side. The loopback demo uses only the synthetic seed and verifies real HTTP cookie/CSRF behavior and denied access cases without creating domain records. See [API routes, inputs and limits](docs/API.md). No React interface is included yet. No external accounts, customer data or paid services are needed.

## Guarantees and limits

`tenant_scope` checks an active user/membership and the selected tenant's role, then binds context to a root transaction using PostgreSQL transaction-local settings. Missing context returns no ticket/comment rows; malformed context fails closed. Nested scopes and pre-existing transactions are refused. Materialize queries within the scope, before its transaction ends.

The request login is neither a table owner, superuser nor `BYPASSRLS` role. It cannot change memberships, schema or ticket ownership, delete tickets, or truncate tables. Ticket inserts require an editor and the authenticated context's creator ID. Comment links also have a composite foreign key enforcing ticket/tenant consistency. See [security boundaries](docs/SECURITY.md) for exact grants, revocation semantics and limitations.

Custom database settings are **not authenticated identity**. A SQL-capable attacker can impersonate context; RLS does not replace application authentication, parameterized queries or SQL-injection prevention. Privileged database roles can bypass policies. Organization/membership metadata is readable by the request role for authorization bootstrap and is not covered by domain RLS. This lab is not production deployment guidance.

## Verification

The 58 tests include 34 database-boundary tests, 19 HTTP/session integration tests and five parser/rate-limit tests, with actual PostgreSQL and no SQLite or mocked policy engine. They cover missing/forged context, tenant-specific roles, database-enforced write denials, cross-tenant relationships, transaction reuse/rollback, membership/user deactivation, unsafe role/configuration detection and deliberate privileged/context-impersonation negative controls. The HTTP tests include 24 read and 18 write role/tenant matrix cases, session rotation/logout replay, CSRF, scoped exports and input limits. CI runs fresh setup and the real loopback HTTP demo on PostgreSQL 16 and 18. Browser, load and production-security evaluations are not claimed here.

References: [OWASP multi-tenant security](https://cheatsheetseries.owasp.org/cheatsheets/Multi_Tenant_Security_Cheat_Sheet.html), [PostgreSQL RLS](https://www.postgresql.org/docs/current/ddl-rowsecurity.html), [Django transactions](https://docs.djangoproject.com/en/5.2/topics/db/transactions/).
