# Milestone 13 Defect Log

Software defect severity below is separate from clinical-alert severity.

| Defect ID | Date | Module | Description | Severity | Reproduction steps | Expected behavior | Actual behavior | Status | Fix | Retest result |
|---|---|---|---|---|---|---|---|---|---|---|
| DEF-001 | 2026-10-02 | Accounts / Django Admin | Application `ADMIN` role did not synchronize Django's `is_staff` flag, blocking the Django Admin governance and ML management surface. | High | Create a user with `role=ADMIN`; authenticate; GET `/admin/`. | ADMIN reaches Django Admin; PHARMACY_STAFF remains denied. | ADMIN was redirected to admin login despite being authenticated. | Resolved | User save logic now synchronizes the flag; data migration updates existing users. | Pass: ADMIN received 200; staff remained redirected. |
| DEF-002 | 2026-10-02 | Inventory | Inventory overview performed row-scaled batch queries because model properties re-filtered a prefetched related manager. | Medium | Create 30 medicines/batches; capture queries for `/inventory/`. | Bounded query count independent of rows on the page. | 81 queries for a 15-row page. | Resolved | Added a filtered `Prefetch` and made stock/count/expiry properties consume its cache. | Pass: 6 queries; rendered values and regressions preserved. |

## Summary

- Critical: 0
- High: 1 resolved, 0 unresolved
- Medium: 1 resolved, 0 unresolved
- Low: 0

