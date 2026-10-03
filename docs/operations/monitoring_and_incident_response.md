# Monitoring and Incident Response

## Monitor

- Platform availability and `/health/` response.
- HTTP 5xx rate, latency, worker restarts, and failed deploys.
- PostgreSQL connectivity, connection use, storage, and backup status.
- Authentication failures, authorization denials, and unusual admin activity.
- Application exceptions, especially dispensing, inventory, deterministic clinical checks, and ML inference fallback.
- Expiring stock, low stock, and integrity exceptions through normal operational reports.

Logs must exclude passwords, secret keys, database URLs, request bodies containing patient information, and session or CSRF tokens. Restrict log access and define retention before live use.

## Respond

1. Triage severity and affected workflows.
2. Preserve relevant logs and timestamps without copying sensitive data into informal channels.
3. Contain the incident: disable the affected release or workflow when safety or inventory integrity is uncertain.
4. Recover using the approved rollback or restore procedure.
5. Verify authorization, stock integrity, transactions, and clinical history before reopening.
6. Document cause, impact, actions, owner, and preventive follow-up.

The deterministic clinical workflow remains authoritative. ML inference failure should degrade safely as tested; the Decision Tree is a synthetic-data prototype and is not clinically validated.
