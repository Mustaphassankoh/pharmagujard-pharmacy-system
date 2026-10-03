# Milestone 13 Evaluation Report

Date: 2026-10-02  
Conclusion: **Technical acceptance criteria passed; ready for supervised human UAT, not clinical deployment.**

## 1. Evaluation objectives

This milestone evaluated functional correctness, inventory and transaction integrity, FEFO, deterministic clinical decision support, explainability, governance, permissions, error handling, data integrity, development-scale performance, query efficiency, ML/XAI integration, regression stability, and readiness for user acceptance testing. It did not add a major product feature and did not begin deployment.

## 2. Scope and architecture

The evaluated system is a Django application with these functional areas:

- `accounts`: authentication and the `ADMIN` / `PHARMACY_STAFF` roles.
- `medicines`: categories, medicine master data, search, validation, and role-aware management.
- `inventory`: batches, stock adjustments, expiry/low-stock views, and immutable stock transaction history.
- `dispensing`: Direct Sale, External Prescription, Consultation, transaction history/detail, FEFO allocation, and Decimal totals.
- `clinical`: drug-interaction, allergy, and dosage checks; warning acknowledgement; immutable snapshots; governed rule lifecycle; reports and CSV exports.
- ML/XAI: a Decision Tree development prototype that assigns review priority after deterministic checks and records an explainable immutable assessment.

The `reports` app contains the cross-cutting Milestone 13 evaluation suite; it does not currently implement a separate operational financial-reporting product surface.

## 3. Test environment and method

- Operating environment: Windows development workstation
- Python: 3.14.5
- Django: 6.1.1
- Automated-test database: SQLite in-memory database created by Django
- Production configuration target: PostgreSQL (not performance-tested in this milestone)
- Timing fixture: 30 synthetic medicines and 30 batches; five requests per endpoint
- Query fixture: 30 synthetic medicines, 30 batches, and 30 transactions
- Evidence types: 156 automated tests, rendered response assertions, database state assertions, SQL query capture, repeatable test-client timing, and source/configuration inspection

These are development-scale technical measurements, not load, concurrency, endurance, or enterprise-scale results.

## 4. Functional test results

The full matrix is in `system_test_matrix.md`. Login, logout, role checks, category and medicine management, batch/adjustment flows, low-stock and expiry behavior, all three dispensing workflows, history/detail pages, governance pages, rule history, CSV exports, and ML review priority passed their automated evaluations.

Manual interactive user testing: **NOT YET EVALUATED**. Rendered server responses were exercised automatically, but this is not a substitute for observation of real users.

## 5. Inventory validation

Validated results:

- Stock-in creates the batch and corresponding audit transaction.
- Adjustment increase/decrease records exact previous and new quantities.
- Attempts to reduce below zero are rejected.
- Expired, inactive, and zero-stock batches are excluded from dispensing availability.
- Single- and multi-batch FEFO allocate the earliest-expiring valid stock first.
- Completed transactions deduct exact stock and create DISPENSED audit rows.
- Draft and cancelled transactions do not alter stock.
- Insufficient stock produces no partial item or stock mutation.

No negative remaining inventory was found in the controlled evaluation database.

## 6. Transaction validation

`DRAFT`, `COMPLETED`, and `CANCELLED` behavior passed. The new repeated-confirmation evaluation confirmed that the first submission completes and deducts once, while a second submission receives 404 because the transaction is no longer an eligible draft. Item and stock-audit counts remain one, and stock remains unchanged after the repeated request. Decimal line and transaction totals remain exact, and historical records are not recalculated.

## 7. Clinical CDSS validation

Controlled synthetic rules cover:

- Drug interaction: no applicable pair, safe/no-match pairs, and LOW/MODERATE/HIGH/CRITICAL warnings.
- Allergy: absent structured context, structured context with no matching rule, matches, missing context, and multiple allergies.
- Dosage: valid dose; below/above limits; daily maximum; frequency and duration violations; incompatible units; no rule; and missing age/weight.
- Status behavior: `PASSED`, `WARNING`, `NOT_APPLICABLE`, and conservative `NOT_CHECKED` states.

No real clinical facts were invented. Deterministic warning acknowledgement remains the authoritative confirmation gate. Clinical review alone does not deduct stock.

## 8. Explainability and safety guards

Warning records and rendered views preserve alert type, severity, involved medicine/allergen context, description/reason, explanation, recommendation, source reference, and rule snapshot. Historical displays use stored snapshots rather than mutable live rule text.

ML assessments preserve raw predicted priority, final guarded priority, model version, confidence, exact feature snapshot, actual traversed decision path, and a generated explanation. The interface identifies the component as development/synthetic and states that it does not diagnose, prescribe, determine safety, or override deterministic rules.

Safety guards passed:

- A deterministic HIGH alert cannot end with LOW or MODERATE final priority.
- A deterministic CRITICAL alert ends with CRITICAL final priority.
- `NOT_CHECKED` remains visible.
- ML failure does not suppress deterministic checks or corrupt stock.
- ML does not independently approve or block dispensing.

## 9. Governance validation

Only ACTIVE rules within their effective window are clinically eligible. DRAFT, UNDER_REVIEW, APPROVED-only, future, expired, RETIRED, and superseded versions are ignored for new checks. Version lineage and audit history remain visible. Active clinical fields are protected, audits reject update/delete, and historical alert snapshots remain unchanged after rule edits or retirement. Governance reports and exports are ADMIN-only.

## 10. Access-control validation

- Unauthenticated users are redirected to login for protected application pages.
- ADMIN and PHARMACY_STAFF can use shared operational views.
- Medicine/category management, batch management, stock transaction history, governance, reports, and exports enforce their documented role rules.
- PHARMACY_STAFF cannot manage clinical governance.
- Django Admin now admits application ADMIN users and continues to deny PHARMACY_STAFF.

DEF-001 corrected the mismatch between the application role and Django's `is_staff` flag. A data migration synchronizes existing accounts, and model save behavior maintains the invariant thereafter.

## 11. Data integrity and error handling

Required medicine, batch, stock transaction, dispensing item, review, result, and alert relationships showed no orphans in the evaluation database. Database constraints protect canonical/unique governed rules and one-to-one clinical/metadata snapshots. Invalid batch and transaction identifiers return 404. Invalid stock/dosage/governance inputs are rejected without partial state. Missing and corrupt ML artifacts return `NOT_AVAILABLE`; their logged exceptions during tests are expected safety-test evidence rather than suite failures.

## 12. Performance and query efficiency

Five-run test-client measurements from the complete regression run:

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

Captured query counts:

| Page | Queries |
|---|---:|
| Inventory list | 6 |
| Transaction history | 4 |
| Governance dashboard | 6 |
| Rule report | 6 |

DEF-002 reduced the inventory list from 81 queries before the fix to 6 afterward by using one filtered prefetch cache for total stock, active-batch count, and nearest expiry. Its focused timing average improved from 210.67 ms before the fix to 32.92 ms after the fix; the full-suite evidence above is the final recorded run.

## 13. ML/XAI prototype evaluation

- Model type: scikit-learn `DecisionTreeClassifier`
- Synthetic dataset: 16 development records
- Training configuration: maximum depth 5, minimum split 4, minimum leaf 2, random seed 42
- Checked artifact: actual depth 3, 4 leaves
- Features: medicine count; interaction, allergy, and dosage warning counts; LOW/MODERATE/HIGH/CRITICAL alert counts; NOT_CHECKED count; warning-check count; encoded transaction type
- Excluded: usernames, staff names, transaction identifiers, patient-identifying data, symptoms/free text, instructions, and other unstructured text
- Reproducibility: fixed split/model random seed and stored feature schema/model metadata
- Availability behavior: absent/corrupt artifacts fail open as `NOT_AVAILABLE`
- Interpretability: actual decision path, confidence, feature snapshot, explanation, raw priority, and guarded priority are stored

The ML component was evaluated for technical integration, reproducibility, interpretability, and workflow behavior. Clinical effectiveness was not established. Synthetic-development metrics are not reported as clinical accuracy.

> **The Decision Tree component is a prototype trained on synthetic development data. Evaluation of its technical behavior does not constitute clinical validation. Real clinical deployment would require representative independently reviewed data, external validation, bias assessment, calibration, monitoring, and clinical governance approval.**

## 14. User acceptance methodology and status

The participant roles, ten-task script, per-task observation metrics, 5-point Likert questionnaire, open-ended questions, and analysis approach are defined in `uat_plan.md`.

Actual UAT status: **NOT YET EVALUATED**. No participant scores or feedback are claimed.

## 15. Defects

Two software defects were identified and resolved:

- DEF-001, High: ADMIN users blocked from Django Admin.
- DEF-002, Medium: inventory overview N+1 queries.

Unresolved Critical/High/Medium/Low defects found by this evaluation: **0**. This means none were found in the tested scope; it is not proof that no latent defects exist.

## 16. Automated regression and checks

- Complete suite: **156 tests, 156 passed, 0 failed, 0 errors**
- Django system check: **System check identified no issues (0 silenced).**
- Migration drift: **No changes detected.**
- New migration: `accounts.0002_sync_admin_role_staff_flag`, required to repair existing role/flag data

## 17. Acceptance criteria

| Criterion | Status | Evidence |
|---|---|---|
| Critical workflows complete successfully | Met | Direct Sale, External Prescription, Consultation tests |
| No unresolved Critical/High software defects | Met | Defect log: both discovered defects resolved |
| No negative inventory | Met in evaluated scope | Validation and integrity tests |
| No double stock deduction | Met | Repeated-confirmation evaluation |
| Deterministic checks follow configured rules | Met | Synthetic CDSS suites |
| Historical clinical snapshots preserved | Met | Rule-edit/retirement/history tests |
| Governance permissions enforced | Met | Lifecycle, reporting, and access tests |
| ML failure does not break deterministic workflows | Met | Missing/corrupt artifact tests |
| Full automated regression passes | Met | 156/156 |
| Django system check clean | Met | 0 issues |
| No pending migration drift | Met | No changes detected |
| Real-user usability acceptance | Pending | NOT YET EVALUATED |
| Clinical validity for deployment | Not established | Outside prototype scope |

## 18. Known limitations

- No real participant UAT has occurred.
- No clinical validation, patient outcome evaluation, calibration, bias assessment, or external validation has occurred.
- Performance evidence uses Django's test client and SQLite, not production PostgreSQL, concurrent users, or production hardware.
- No load, stress, endurance, security penetration, browser/device compatibility, backup/restore, or disaster-recovery evaluation was performed.
- The standalone operational `reports` app remains a placeholder; current implemented reports are clinical-governance reports.

## 19. Final evaluation conclusion

The system meets the defined technical acceptance criteria for its current development scope and is suitable to proceed to supervised human UAT and pre-deployment hardening. It is **not approved for clinical deployment** based on this milestone. The ML component remains a synthetic-data technical prototype.

## 20. Recommendation for Milestone 14

Make Milestone 14 a controlled UAT and pre-deployment-hardening milestone: recruit representative users, execute the approved UAT script with synthetic data, remediate observed usability defects, validate production PostgreSQL behavior, perform security/deployment configuration review, and define backup/restore and operational monitoring. Do not represent the Decision Tree as clinically validated.
