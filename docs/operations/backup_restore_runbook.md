# PostgreSQL Backup and Restore Runbook

Use provider-managed backups where available and supplement them with encrypted logical backups. Credentials must come from the secret store and must never be written into this document or committed files.

## Backup

1. Announce the maintenance window and identify the source database and release.
2. Run `pg_dump` in custom format against the TLS-protected database.
3. Store the resulting file in access-controlled encrypted storage outside the application host.
4. Record timestamp, database identifier, tool version, file size, and SHA-256 checksum.
5. Retain backups according to the approved retention policy and periodically verify they remain readable.

Example shape (substitute secret-backed connection values):

```text
pg_dump --format=custom --no-owner --no-acl --file=<backup-file> <database-url>
```

## Restore rehearsal

Never rehearse against production. Provision an empty isolated PostgreSQL database, restrict access, and restore with:

```text
pg_restore --clean --if-exists --no-owner --no-acl --dbname=<isolated-test-url> <backup-file>
```

Then run migrations, `python manage.py check`, and synthetic smoke tests. Compare critical row counts, verify users and permissions, confirm stock quantities are non-negative, and inspect transaction-to-stock relationships. Destroy the rehearsal environment according to the data-handling policy.

## Recovery controls

- Require a second-person check before any production restore.
- Preserve the failed database before replacement when feasible.
- Record recovery point and recovery time achieved.
- Rotate credentials if a backup or connection string may have been exposed.
- Escalate any missing, corrupt, unencrypted, or untested backup immediately.

Status for Milestone 14: the procedure is defined, but a provider-backed restore rehearsal has not yet been evidenced.
