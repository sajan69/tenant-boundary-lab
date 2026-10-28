# Reproducible lab evaluation

The recorded evidence uses synthetic organizations, identities and requests, not customers or production traffic. The [source run](https://github.com/sajan69/tenant-boundary-lab/actions/runs/40647553682) on 28 October 2026 executed the full suite, permission matrix, HTTP demo, measured workload and built-client Chromium scenarios. Machine-readable reports retain their exact code revision, run URL, dataset hashes and environment. Later timings can differ.

## Authorization cases

Run `python scripts/evaluate.py --disposable-lab` in the loaded virtualenv/environment against the fresh disposable seed. It reuses the two existing permission-matrix tests with Django Client, enforced CSRF and real PostgreSQL. Matrix identities use `force_login`; password verification/session rotation are evaluated separately by the full suite and real HTTP/browser checks. The evaluator emits expected and observed statuses for every case and fails on an incomplete or mismatching run.

| Matrix | Expected allowed | Expected denied | Observed mismatches |
| --- | ---: | ---: | ---: |
| Six user/tenant combinations × four read routes | 16 | 8 | 0 |
| Six combinations × three write routes | 6 | 12 | 0 |
| Total | 22 | 20 | 0 |

All 42 cases matched on PostgreSQL 16.15 and 18.6 in the source run. The [recorded PostgreSQL 18 matrix](reports/evaluation-pg18.json) contains the individual requests/statuses. This finite matrix does not establish exhaustive authorization coverage or a real-world accuracy percentage. Other suite cases cover anonymous access, object-ID substitution, ownership spoofing, revocation, CSRF, session replay and configuration failures.

The full suite contains 60 test functions: 34 database-boundary, 19 HTTP/session and seven parser/rate-limit/workload-guard tests. The PostgreSQL 18 CI job also passes ten built-React Chromium scenarios: role-specific controls and forged writes; scoped downloads; delayed old-tenant responses; editor creation/edits/comments; inert HTML/script labels; filtering; revocation and clearing; logout/account changes; session expiry; mobile/layout/headers/storage. Screenshots and the browser case report are CI artifacts, not customer data. See [browser reproduction](WEB_CLIENT.md).

Negative controls deliberately succeed for a privileged database connection and a SQL-capable caller that forges custom context. They document the boundary's limits: RLS guards ordinary tenant-filter mistakes; it is not authenticated identity, SQL-injection prevention or protection from a compromised application/administrator. See [security assumptions](SECURITY.md).

## Authenticated-read workload

Use a fresh disposable lab with the standard seed, no concurrent application/browser activity, and the ordinary request-role API running on loopback:

```sh
python scripts/benchmark_api.py --disposable-lab --port 8000 --rows 100 --repeats 3 --requests 10
```

The command requires explicit disposable-lab confirmation and checks the original users, memberships, tickets and comment before inserting fixtures. Bounds are 10–200 generated tickets per tenant, one–five repetitions, and one–25 requests per operation per repetition. It refuses remote database hosts and calls only `127.0.0.1`, with proxy/redirect use disabled and bounded response sizes/timeouts. Privileged access is used only for fixture setup/cleanup and metadata; every measured HTTP request uses Alice's ordinary authenticated session and the restricted application database role.

The recorded workload has 100 generated tickets per tenant plus the two seed tickets: **202 tickets, one comment, two tenants**. The generated rows have deterministic UUIDs, labels, alternating open/closed states and a fixed synthetic timestamp. Their SHA-256 is `1321c5ff750d73cd90593aa91c5e1e5569fadbf931a985b86f482f2e01b2ba91`. A separate hash captures base seed projections whose creation timestamps depend on setup. The report stores both hashes.

One client executes list, detail, export and cross-tenant-denial reads in round-robin order. Three repetitions × ten requests × four operations gives **120 measured requests**, with no concurrency. List reads request 100 of the 101 authorized tickets and verify the continuation flag; exports verify all 101 authorized tickets and the one comment. Every response is checked for expected status, scope and relevant counts/IDs after stopping its timer. Cleanup removes only matching generated records without comments, refuses changed fixtures, and rechecks the original seed. The recorded run verified cleanup.

| Operation | Median wall time, ms (rounded to three decimals) |
| --- | ---: |
| List: 100 authorized tickets | 20.616 |
| Seed ticket detail | 18.654 |
| Export: 101 tickets and one comment | 22.115 |
| Denied cross-tenant read, HTTP 403 | 16.498 |

The [full measured report](reports/benchmark-pg18.json) includes every sample and each repetition's median. The overall figures above are medians of all 30 samples per operation, not a median-of-medians. Environment: Python 3.12.15, Django 5.2.18, psycopg 3.3.6, PostgreSQL 18.6, Linux x86_64/glibc 2.39 and four reported logical CPUs on a shared GitHub-hosted runner.

`time.perf_counter` measures request construction, loopback HTTP with `Connection: close`, session lookup, normal request database connections/queries/RLS, server serialization, response reading and client JSON decoding. The development server uses its normal request handling/logging. Fixture setup/cleanup, login/logout/password hashing and response-correctness assertions are excluded, as are TLS, cloud networks, Vite/React and browser rendering. Functional HTTP smoke checks/authentication precede timing; there is no dedicated warmup or explicit cache reset.

These results are a reproducible small workload, not a load-capacity test, production throughput guarantee or improvement over an unmeasured baseline. Shared hardware, caches, database state, operating-system load and the development server affect latency. There is no claim that a faster denial is a timing-side-channel defense. A changed/commented fixture causes cleanup refusal rather than deleting possible concurrent work; inspect that disposable lab before retrying. Do not run the measurements against a shared or real-user environment.
