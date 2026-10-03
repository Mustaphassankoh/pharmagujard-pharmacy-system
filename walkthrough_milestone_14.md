# Milestone 14 Walkthrough — Pre-deployment Hardening

## Outcome

Milestone 14 completes the repository-level pre-deployment hardening that can be verified locally. PharmaGuard now has environment-driven production settings, HTTPS and cookie controls, PostgreSQL TLS configuration, WhiteNoise static assets, Gunicorn/Render configuration, a minimal liveness endpoint, generic branded error handling, console logging, cross-platform ML artifact resolution, deployment tests, and operational runbooks.

This milestone does **not** claim clinical-deployment readiness. Real participant UAT, provider-backed PostgreSQL validation, a real backup/restore rehearsal, load/security testing, and clinical validation remain pending.

## Implemented controls

- Production fails closed when `DEBUG=False` and `SECRET_KEY` is absent.
- Allowed hosts and trusted CSRF origins are environment-controlled.
- Secure session/CSRF cookies and HTTPS redirect default on outside debug mode.
- HSTS is configurable and deliberately starts disabled until HTTPS is verified.
- PostgreSQL connection health checks, pooling lifetime, and optional required TLS are configured.
- Static assets use compressed manifest storage in production and ordinary static storage in isolated tests.
- `/health/` discloses only liveness state.
- 400, 403, CSRF, 404, and 500 pages avoid internal details.
- Admin branding and safety-sensitive read-only permissions are regression-tested.
- Render, backup/restore, monitoring, incident, rollback, and release-check procedures are documented.

## Verification performed

On 3 October 2026:

- `python manage.py check`: passed with zero issues.
- `python manage.py makemigrations --check --dry-run`: no model changes detected (the configured remote database was unreachable from the sandbox during its migration-history advisory check).
- `python manage.py test --settings=pharmacy_system.test_settings`: **163/163 tests passed**.

The first isolated regression run exposed missing static manifest entries because the new production storage backend leaked into test settings. `test_settings.py` now overrides only test static storage; the full suite subsequently passed.

Expected error logs from deliberately missing/corrupt ML-artifact safety tests appeared, and those tests passed, confirming safe fallback behavior.

## Pending external evidence

| Activity | Status |
|---|---|
| Real participant UAT | NOT YET EVALUATED |
| Production/provider PostgreSQL migration and workflow validation | Pending |
| Backup creation and isolated restore rehearsal | Pending |
| Load, stress, penetration, and browser/device testing | Pending |
| Monitoring alert delivery and incident drill | Pending |
| Clinical validation of rules or Decision Tree | Not established |

No user feedback, timing, outcome, restore, or production claims have been fabricated.

## Next controlled action

Deploy to a non-clinical staging environment with synthetic data, execute the deployment checklist, rehearse backup restoration into an isolated database, and conduct the approved UAT sessions with representative users. Log observed defects and evidence before considering any further release decision.
