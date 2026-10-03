# Walkthrough: Milestone 13 System Evaluation, Validation and User Acceptance Testing

## Implementation Status

Milestone 13 is complete as a formal technical evaluation milestone.

The system passed its defined technical acceptance criteria and is ready for supervised human user acceptance testing. It is not approved for clinical deployment. Deployment and final production documentation were not started.

The completed milestone provides:

- A formal system test matrix.
- Cross-cutting automated evaluation tests.
- Inventory, transaction, CDSS, governance, permission, and data-integrity validation.
- Development-scale performance and query measurements.
- A software defect log.
- A UAT task plan and questionnaire.
- A structured evaluation report and acceptance decision.

Human UAT remains **NOT YET EVALUATED**. No participant feedback or scores were fabricated.

## Evaluation Architecture

The evaluation combined five evidence sources:

```text
Existing Feature Tests ────────────────┐
Milestone 13 Cross-Cutting Tests ──────┤
Rendered Response / Database Checks ───┼──> Evaluation Evidence
SQL Query Capture ─────────────────────┤
Repeatable Response Timing ────────────┘
                                             │
                                             ▼
                                  Acceptance Decision
```

The evaluated application areas were:

- Accounts and authentication.
- Medicine categories and medicine master data.
- Inventory, batches, expiry, low stock, and stock adjustments.
- Direct Sale, External Prescription, and Consultation workflows.
- Transaction history and immutable transaction detail.
- Drug-interaction, allergy, and dosage decision support.
- Clinical warning acknowledgement and historical snapshots.
- Clinical-rule governance, audit reporting, history, and CSV exports.
- Decision Tree review-priority integration and explainability.

The supported application roles are:

- `ADMIN`
- `PHARMACY_STAFF`

Superusers retain Django's standard elevated behavior.

## Evaluation Files

Milestone 13 created the following evidence package:

```text
docs/
└── evaluation/
    ├── defect_log.md
    ├── milestone_13_evaluation_report.md
    ├── system_test_matrix.md
    └── uat_plan.md

reports/
└── test_evaluation.py
```

`system_test_matrix.md` records test IDs, preconditions, inputs, steps, expected results, actual results, status, and notes.

`defect_log.md` separates software-defect severity from clinical-alert severity and records reproduction, resolution, and retest evidence.

`uat_plan.md` contains the participant framework, ten-task script, observation metrics, Likert questionnaire, open-ended questions, and analysis approach.

`milestone_13_evaluation_report.md` consolidates the technical evidence, limitations, acceptance criteria, and final recommendation.

## Automated Evaluation Additions

`reports/test_evaluation.py` adds eight cross-cutting tests covering gaps that were not previously consolidated into a formal evaluation suite:

- Login, logout, and unauthenticated redirects.
- ADMIN and PHARMACY_STAFF access matrices.
- Django Admin access by application role.
- Repeated confirmation and double-deduction prevention.
- Invalid identifier and insufficient-stock behavior.
- Required relationship and negative-quantity inspection.
- Representative query budgets.
- Repeatable development-scale response timing.

These supplement the original 148 feature and safety tests rather than replacing them.

## Functional Validation

The formal matrix covers:

- Login and logout.
- Role-based access.
- Category and medicine management.
- Medicine search, filtering, and pagination.
- Batch creation and stock adjustment.
- Low-stock and expiry behavior.
- Direct Sale.
- External Prescription.
- Consultation.
- Transaction history and detail.
- Governance dashboard, reports, history, and CSV exports.
- Decision Tree review priority.

All automated functional cases passed. Interactive observation of real users remains pending.

## Inventory and FEFO Validation

The evaluation confirmed:

- Stock-in creates the expected batch and `STOCK_IN` audit entry.
- Adjustment increases and decreases preserve exact previous/new quantities.
- Stock cannot be adjusted below zero.
- Expired batches are excluded.
- Inactive batches are excluded.
- Zero-stock batches are excluded.
- FEFO selects the earliest-expiring valid batch.
- Multi-batch allocation exhausts earlier stock before later stock.
- Completed transactions deduct the exact quantity.
- DISPENSED stock audit entries preserve transaction references.
- Draft and cancelled transactions do not alter stock.
- Insufficient stock causes no partial item creation or partial deduction.

## Transaction Integrity

The `DRAFT`, `COMPLETED`, and `CANCELLED` states were formally evaluated.

A new repeated-confirmation test completes a Direct Sale and immediately repeats the confirmation request. The second request returns `404` because the transaction is no longer an eligible draft. The evaluation then verifies that:

- Remaining stock is unchanged after the second request.
- Only one dispensing item exists.
- Only one referenced stock transaction exists.
- The stored total remains unchanged.

This provides direct evidence that repeated submission does not double-deduct inventory.

## Clinical Decision-Support Validation

All clinical scenarios use controlled synthetic rules and data.

### Drug interaction

Coverage includes:

- No applicable pair.
- Pair with no configured warning.
- LOW, MODERATE, HIGH, and CRITICAL warnings.
- Multiple medicine pairs and multiple alerts.
- Rerun deduplication.
- Historical snapshot stability after rule edits.

### Allergy

Coverage includes:

- Structured allergy context absent.
- Structured allergy present with no matching rule.
- Matching synthetic allergy rules.
- Multiple allergies.
- Free text correctly excluded from structured claims.
- Missing context represented conservatively.

### Dosage

Coverage includes:

- Valid dosage.
- Below-minimum and above-maximum single dose.
- Above maximum daily dose.
- Frequency below and above configured limits.
- Duration above configured limits.
- Incompatible units.
- No matching rule.
- Missing age or weight required by a rule.

The evaluation confirms correct use of `PASSED`, `WARNING`, `NOT_APPLICABLE`, and `NOT_CHECKED`.

## Explainability and Safety Guards

Deterministic warning records and rendered pages preserve:

- Alert type.
- Severity.
- Relevant medicines or allergen context.
- Description or reason.
- Explanation.
- Recommendation.
- Source reference.
- Historical rule snapshot.

Decision Tree assessments preserve:

- Raw predicted priority.
- Final guarded priority.
- Model version.
- Confidence.
- Ordered feature snapshot.
- Actual traversed tree path.
- Factual explanation.
- Synthetic-development disclaimer.

Safety validation confirmed:

- A deterministic HIGH alert cannot produce a final LOW or MODERATE priority.
- A deterministic CRITICAL alert produces a final CRITICAL priority.
- `NOT_CHECKED` remains visible.
- ML does not suppress deterministic warnings.
- ML does not independently approve or block dispensing.
- Deterministic acknowledgement remains authoritative.
- Missing or corrupt model artifacts fail open as `NOT_AVAILABLE`.

## Governance Validation

The governance evaluation confirmed that new clinical checks use only the current ACTIVE rule version within its effective date window.

The following are ignored for new checks:

- DRAFT rules.
- UNDER_REVIEW rules.
- APPROVED-only rules.
- Future rules.
- Expired rules.
- RETIRED rules.
- Superseded versions.

Historical alerts remain unchanged when live rules are edited or retired. Rule lineage remains visible, audit records reject update/delete, and Pharmacy Staff cannot manage governance.

## Access-Control Defect and Resolution

The initial Milestone 13 evaluation discovered `DEF-001`.

Application users with `role='ADMIN'` passed application-level permission checks but could not enter Django Admin because Django also requires `is_staff=True`. This blocked the intended clinical-rule and ML-model management surface.

The correction adds one invariant to `accounts.User.save()`:

```text
ADMIN           -> is_staff = True
PHARMACY_STAFF  -> is_staff = False
superuser       -> standard Django behavior preserved
```

This synchronization also works when callers use `save(update_fields=[...])`.

Migration `accounts.0002_sync_admin_role_staff_flag` updates existing accounts:

- Existing ADMIN users become staff-enabled.
- Non-superuser PHARMACY_STAFF users remain staff-disabled.

The retest confirmed ADMIN receives the Django Admin index while PHARMACY_STAFF remains denied.

The migration was created and applied automatically to clean test databases. It must be applied to each configured development/production database with the normal migration process before relying on the corrected access behavior.

## Query-Efficiency Defect and Resolution

The initial inventory measurement discovered `DEF-002`.

Although inventory views prefetched batches, model properties called new filtered queries for every displayed medicine:

- `total_available_stock`
- `active_batches_count`
- `nearest_expiry_date`

For a 15-row page this produced 81 queries.

The focused correction adds one filtered `Prefetch` containing active, unexpired, positive-stock batches. The three existing properties use that cache when available and retain their original database-query behavior in other contexts.

Post-fix query counts were:

| Page | Queries |
|---|---:|
| Inventory list | 6 |
| Transaction history | 4 |
| Governance dashboard | 6 |
| Rule report | 6 |

The inventory-focused timing average improved from 210.67 ms before the fix to 32.92 ms in the immediate post-fix evaluation run. Functional output remained unchanged.

## Development-Scale Performance

The final complete-suite run measured five requests per operation using Django's test client and an in-memory SQLite database.

| Operation | Average | Slowest |
|---|---:|---:|
| Login | 8.12 ms | 13.20 ms |
| Dashboard | 9.65 ms | 11.66 ms |
| Medicine list | 38.40 ms | 41.71 ms |
| Inventory list | 45.49 ms | 60.09 ms |
| Transaction creation | 10.31 ms | 12.53 ms |
| Clinical review | 68.15 ms | 80.43 ms |
| Governance dashboard | 61.15 ms | 65.65 ms |
| Rule report | 68.76 ms | 80.97 ms |
| CSV export | 55.89 ms | 62.73 ms |

The fixture contained 30 synthetic medicines and 30 batches. The query fixture also contained 30 transactions.

These figures are development measurements only. They are not production PostgreSQL, concurrency, load, stress, endurance, or enterprise-scale results.

## ML/XAI Prototype Evaluation

The evaluated artifact is a scikit-learn `DecisionTreeClassifier` trained on 16 synthetic development records.

Training configuration:

- Maximum configured depth: 5.
- Minimum samples split: 4.
- Minimum samples leaf: 2.
- Fixed random seed: 42.
- Evaluated artifact depth: 3.
- Evaluated artifact leaves: 4.

The exact structured feature list remains:

```text
medicine_count
interaction_warning_count
allergy_warning_count
dosage_warning_count
low_alert_count
moderate_alert_count
high_alert_count
critical_alert_count
not_checked_count
warning_check_count
transaction_type
```

Identifiers, names, symptoms, instructions, acknowledgement notes, and other free text remain excluded.

The ML component was evaluated for technical integration, reproducibility, interpretability, and workflow behavior. Clinical effectiveness was not established. Synthetic metrics are not presented as clinical accuracy.

> **The Decision Tree component is a prototype trained on synthetic development data. Evaluation of its technical behavior does not constitute clinical validation. Real clinical deployment would require representative independently reviewed data, external validation, bias assessment, calibration, monitoring, and clinical governance approval.**

## UAT Framework

The UAT plan recommends three representative perspectives:

- Pharmacy staff or pharmacy worker.
- Administrator or pharmacy manager.
- Technically knowledgeable evaluator.

The ten tasks cover login, medicine search, batch creation, all three dispensing workflows, clinical-warning review and acknowledgement, transaction history, and administrator governance review.

The framework captures:

- Task completion success.
- Task completion time.
- Number of errors.
- Requests for assistance.
- Satisfaction scores.
- Qualitative comments and defect references.

The questionnaire contains ten 5-point Likert statements and six open-ended questions.

Actual human UAT status remains **NOT YET EVALUATED**.

## Defect Summary

| Severity | Identified | Resolved | Unresolved |
|---|---:|---:|---:|
| Critical | 0 | 0 | 0 |
| High | 1 | 1 | 0 |
| Medium | 1 | 1 | 0 |
| Low | 0 | 0 | 0 |

The absence of unresolved defects in the tested scope does not prove that no latent defects exist.

## Automated Verification

The final complete regression run reported:

```text
Found 156 test(s).
Ran 156 tests
OK
```

This consists of the original 148 tests plus eight Milestone 13 cross-cutting evaluation tests.

The Django system check reported:

```text
System check identified no issues (0 silenced).
```

Migration drift verification reported:

```text
No changes detected
```

Logged `FileNotFoundError` messages for `invalid.joblib` and `missing/model.joblib` are intentional missing/corrupt-model safety scenarios. Their tests passed and confirmed fail-open behavior.

## Acceptance Decision

The following technical criteria are met:

- Critical workflows complete successfully.
- No unresolved Critical or High software defects were found.
- Negative inventory is rejected.
- Repeated confirmation does not double-deduct stock.
- Deterministic checks follow configured synthetic rules.
- Historical clinical snapshots remain stable.
- Governance permissions are enforced.
- ML failures do not break deterministic workflows.
- All 156 automated tests pass.
- Django reports no system-check issues.
- No migration drift remains.

The following are not established:

- Real-user usability acceptance.
- Clinical effectiveness.
- Production PostgreSQL performance.
- Concurrent-load behavior.
- Security penetration results.
- Backup/restore and disaster-recovery readiness.
- Cross-browser and device compatibility.

## Final Conclusion and Next Milestone

Milestone 13 demonstrates that the current development system satisfies its defined technical acceptance criteria. The system is suitable to proceed to supervised human UAT and pre-deployment hardening.

It is not approved for clinical deployment, and the Decision Tree remains a synthetic-data technical prototype.

Recommended Milestone 14 scope:

- Conduct real UAT using the approved synthetic-data task script.
- Record actual participant results without fabrication.
- Resolve observed usability defects.
- Validate the application against production PostgreSQL.
- Review security and deployment configuration.
- Test backup and restoration.
- Define monitoring and operational support.
- Evaluate supported browsers and devices.

Deployment itself should begin only after those readiness activities and an explicit approval decision.
