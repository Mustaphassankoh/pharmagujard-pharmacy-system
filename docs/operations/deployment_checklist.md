# Deployment Checklist

This checklist supports a controlled prototype deployment. It is not clinical-deployment approval.

## Before deployment

- Use a dedicated PostgreSQL database and a least-privilege application user.
- Set `SECRET_KEY`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, every `DB_*` variable, and production SMTP settings in the platform secret store.
- Confirm `DEBUG=False`, secure cookies, HTTPS redirect, proxy SSL handling, and `DB_SSLMODE=require`.
- Keep HSTS at zero for the first HTTPS verification. Increase it only after confirming every intended host and subdomain works over HTTPS.
- Run `python manage.py check --deploy` and review every warning.
- Run `python manage.py makemigrations --check --dry-run`.
- Run the complete isolated suite: `python manage.py test --settings=pharmacy_system.test_settings`.
- Create and verify a database backup before applying migrations.

## Release verification

- Confirm `/health/` returns only `{"status": "ok"}` over HTTPS.
- Confirm unauthenticated users cannot access protected pages.
- Sign in with each representative role and verify its permitted navigation.
- Exercise one synthetic direct sale, external prescription, and consultation; verify FEFO deduction and transaction history.
- Confirm application errors show the branded generic page and do not expose configuration or tracebacks.
- Inspect platform logs for migration, static-file, database, CSRF, and server errors.

## Rollback decision

Stop or roll back the release if migrations fail, authentication/authorization changes unexpectedly, stock integrity is violated, static assets fail broadly, or error rates remain elevated. Restore data only through the tested restore procedure; never overwrite the only database copy.

## Evidence record

Record the release identifier, operator, timestamp, database backup identifier, migration result, smoke-test result, unresolved warnings, rollback decision, and approver. Do not mark PostgreSQL, UAT, backup restore, or clinical validity as passed without observed evidence.
