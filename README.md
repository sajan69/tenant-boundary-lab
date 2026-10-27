# Tenant Boundary Lab

A local lab for examining authorization boundaries in a multi-tenant support-ticket application, with synthetic organizations, users and tickets as its domain.

Client-supplied tenant identifiers are selectors, not proof of access. Application authorization and PostgreSQL row policies address different failure modes; privileged database roles require separate treatment.

References: [OWASP multi-tenant security guidance](https://cheatsheetseries.owasp.org/cheatsheets/Multi_Tenant_Security_Cheat_Sheet.html) and [PostgreSQL row-security policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html).
