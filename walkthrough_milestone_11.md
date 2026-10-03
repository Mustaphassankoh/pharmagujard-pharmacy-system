# Walkthrough: Milestone 11 Governance Dashboard and Clinical Knowledge Reporting

## Overview

Milestone 11 makes the Milestone 10 governance data operationally visible to administrators. It adds read-only dashboards, reports, history pages, and CSV exports without changing clinical matching, lifecycle transitions, clinical alerts, acknowledgement, FEFO, inventory, or dispensing behavior.

No Decision Tree, ML, diagnosis, prescribing, clinical recommendation, or fabricated clinical knowledge was introduced.

## Access Control

Every governance route uses one server-side permission guard. Authenticated ADMIN users and superusers are allowed; Pharmacy Staff receive HTTP 403. Unauthenticated users are redirected to login.

The sidebar displays `Clinical Governance` only to ADMIN/superuser users. Hiding the navigation link is supplementary; all dashboard, detail, history, and CSV endpoints enforce authorization independently.

## Routes

```text
/clinical/governance/
/clinical/governance/rules/
/clinical/governance/rules/export.csv
/clinical/governance/rules/<rule_type>/<id>/history/
/clinical/governance/audits/
/clinical/governance/audits/export.csv
/clinical/governance/audits/<id>/
```

The route namespace is `clinical` and the main route name is `clinical:governance_dashboard`.

## Reporting Helper Layer

`clinical/reporting.py` contains read-only shared logic for:

- Cross-model rule normalization.
- Lifecycle and rule-type counts.
- Effective-state classification.
- Thirty-day expiry monitoring.
- Review-date classification.
- Action-required queues.
- Recent audit activity.
- Shared report filtering, searching, and sorting.
- Rule-version lineage.

The expiry/review window is defined by `EXPIRY_WINDOW_DAYS = 30`.

All rule querysets use `select_related` for medicine, allergen, governance users, and predecessor relationships. Audit querysets load `changed_by` with `select_related`. This avoids per-row relationship queries.

## Dashboard Metrics

The dashboard displays:

- Total clinical rules.
- Draft rules.
- Under-review rules.
- Approved rules.
- Active rules.
- Retired rules.
- Currently effective active rules.
- Future-dated active rules.
- Expired active rules.
- Rules expiring within 30 days.
- Source review overdue.
- Source review due within 30 days.
- Rules without a review date.

It also reports total, active, draft, retired, and expiring-soon counts separately for interaction, allergy, and dosage rules. Audit records are never counted as rules.

## Date Logic

Effective-state calculations use timezone-aware `timezone.now()` values:

- `effective`: lifecycle ACTIVE, enabled, not retired, and inside the effective period.
- `future`: ACTIVE with `effective_from` later than now.
- `expired`: ACTIVE with `effective_to` earlier than now.
- `retired`: retired lifecycle/timestamp or compatibility-disabled.
- `inactive`: a non-active lifecycle state.

An expiring-soon rule must currently be effective and have `effective_to` between now and 30 days from now.

Review dates use `timezone.localdate()`:

- `overdue`: before today.
- `due_soon`: today through 30 days.
- `scheduled`: later than 30 days.
- `none`: no review date configured.

Review status remains informational and never activates, retires, or disables a rule.

## Governance Queues

The dashboard presents separate queues for:

- Draft rules not yet submitted.
- Rules under review.
- Approved rules awaiting activation.
- Source reviews overdue or due soon.
- Currently effective rules expiring soon.

Rows identify the rule type, summary, version, lifecycle status, review date, and link to complete rule history.

## Rule Report

The paginated rule report supports:

- Rule type.
- Lifecycle status.
- Severity.
- Version.
- Effective state.
- Effective-period overlap.
- Review state.
- Creator.
- Approver.
- Medicine/allergen/description/source search.
- Updated, created, effective-date, review-date, lifecycle, and version sorting.

The three rule models are normalized into one report while retaining links to their original records and lineage. Results are paginated at 25 rows.

## Source Governance Reporting

The dashboard counts missing review dates, configured review dates due soon, and overdue reviews. The rule report exposes source reference/title search and source fields in CSV exports.

These fields are presented strictly as governance metadata. The application does not infer or claim clinical source quality.

## Audit Reporting

The audit report is paginated at 25 rows and can be filtered by rule type and action. Recent dashboard activity displays action, rule identity, version, responsible user, timestamp, and reason without exposing raw snapshots.

Audit detail pages show readable formatted before/after JSON along with the accountable user and lifecycle action. All audit pages are GET-only and read-only.

## Rule History

The history view displays:

- Selected version and lifecycle status.
- Effective dates.
- Creator, reviewer, and approver.
- Retirement identity and date.
- The complete predecessor/successor version lineage.
- Paginated audit events across every rule object in that lineage.

Lineage is derived from the existing `supersedes` relationships and does not alter governance state.

## CSV Exports

The rule CSV export honors the same report filters and includes:

- Rule type and object ID.
- Version, lifecycle, effective state, and severity.
- Medicine and allergen where applicable.
- Effective and review dates.
- Source reference/title/version.
- Creator and approver usernames.
- Creation and update timestamps.

The audit CSV includes audit ID, rule identity, version, action, username, timestamp, and reason. It intentionally excludes before/after JSON snapshots and authentication data.

Both exports enforce ADMIN/superuser permissions server-side.

## Templates

```text
templates/clinical/
├── _pagination.html
├── audit_detail.html
├── audit_report.html
├── governance_dashboard.html
├── rule_history.html
└── rule_report.html
```

The pages reuse existing application cards, tables, buttons, badges, navigation, and responsive layout conventions. No charting dependency was introduced.

## Migration Status

Milestone 11 requires no schema migration. Final migration drift verification returned:

```text
No changes detected
```

## Automated Verification

The complete test suite passed:

```text
Found 131 test(s).
System check identified no issues (0 silenced).
Ran 131 tests in 6.610s
OK
```

Coverage includes authentication, ADMIN/superuser access, Pharmacy Staff denial, lifecycle and type counts, effective/future/expired/expiring states, review-date states, queues, recent audits, filtering, search, lineage, audit detail, pagination, filtered rule CSV, audit CSV, exclusion of snapshots from exports, GET-only details, reporting non-mutation, all clinical decision-support regressions, governance lifecycle, FEFO, inventory, dispensing, medicines, and authentication.

## Manual Verification Status

The requested operational scenarios were rendered and exercised through Django's page client tests with synthetic isolated data. An interactive visual pass was attempted, but no in-app browser instance was available in the execution environment. Therefore no unsupported claim of visual browser verification is made.

Validated outcomes:

| Scenario | Result |
|---|---|
| Lifecycle counts | Match database state |
| Rule expiring within 30 days | Appears in Expiring Soon |
| Past review date | Appears as Review Overdue |
| Future effective date | Excluded from currently effective count |
| Draft/under-review/approved | Appear in their respective queues |
| Recent governance audit | Displays action, user, time, and reason |
| Versioned rule | Full supersession lineage displayed |
| Filtered CSV | Contains only matching rule rows |
| Pharmacy Staff | Dashboard, reports, details, history, and exports denied |

## Updated Structure

```text
clinical/
├── admin.py
├── dosage.py
├── governance.py
├── reporting.py
├── urls.py
├── views.py
├── test_governance.py
├── test_reporting.py
└── tests.py
```

## Final Scope and Recommendation

Milestone 11 is complete. A suitable Milestone 12 is controlled governance notifications and scheduled maintenance: configurable reminder delivery for expiring/review-due rules, administrator notification preferences, report scheduling, and auditable acknowledgement of governance tasks.

Decision Tree and ML implementation has not begun.
