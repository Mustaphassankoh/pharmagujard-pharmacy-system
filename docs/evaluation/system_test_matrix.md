# Milestone 13 System Test Matrix

Date: 2026-10-02  
Environment: Windows development workstation, Python 3.14.5, Django 6.1.1, SQLite in-memory test database.  
Evidence: automated Django tests, rendered response assertions, query capture, and repeatable response timing. Human UAT is tracked separately and remains pending.

| Test ID | Feature | Preconditions | Input | Steps | Expected result | Actual result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|---|
| AUTH-01 | Login | Active staff account | Valid username/password | POST login form | Redirect to dashboard and establish session | Redirected and dashboard accessible | Pass | Automated |
| AUTH-02 | Logout | Authenticated account | POST logout | Submit header logout form | Session ends and login page is shown | Redirected to login; protected page redirects | Pass | Automated |
| AUTH-03 | Role-based access | ADMIN and PHARMACY_STAFF exist | Shared/admin-only URLs | Request each URL as both roles | Shared pages available; management/governance denied to staff | Expected 200/403 responses observed | Pass | Automated matrix |
| AUTH-04 | Django Admin | ADMIN and PHARMACY_STAFF exist | `/admin/` | Request as each role | ADMIN admitted; staff denied | ADMIN 200; staff redirected | Pass | DEF-001 fixed and retested |
| MED-01 | Medicine categories | ADMIN authenticated | Valid category; duplicate name | Create and repeat | Valid category saved; duplicate rejected | Existing model/view tests pass | Pass | Automated |
| MED-02 | Medicine CRUD | ADMIN and staff authenticated | Valid/invalid medicine forms | Create, update, view, toggle | ADMIN manages; staff view-only; constraints enforced | Existing CRUD/permission tests pass | Pass | Automated |
| MED-03 | Medicine search/filter | Medicines exist | Search/filter/page values | Request list | Matching, paginated results | Existing search/filter test passes | Pass | Automated |
| INV-01 | Batch creation / stock-in | ADMIN, medicine exists | Valid batch | Submit batch form | Batch and STOCK_IN audit row created | Exact quantities and audit row verified | Pass | Automated |
| INV-02 | Stock adjustment | Existing batch | Increase/decrease values | Apply both adjustments | Exact quantities and audit history | Increase/decrease tests pass | Pass | Automated |
| INV-03 | Negative stock protection | Existing batch with 10 units | Decrease 15 | Apply adjustment | Clear validation error; no negative quantity | Validation raised; quantity preserved | Pass | Automated |
| INV-04 | Low stock | Medicine threshold configured | Valid/zero stock | Request low-stock page | Qualifying medicines shown | Aggregation/status tests pass | Pass | Automated |
| INV-05 | Expiry/inactive handling | Expired, inactive, active batches | Stock lookup | Evaluate availability | Expired/inactive batches excluded | Exclusion tests pass | Pass | Automated |
| INV-06 | FEFO allocation | Two batches with different expiry dates | Quantity spanning batches | Confirm allocation | Earliest-expiry batch consumed first | Single/multi-batch FEFO verified | Pass | Automated |
| INV-07 | Exact deduction/audit | Sufficient stock | Dispense quantity | Complete transaction | Stock deducted exactly; DISPENSED audit created | Exact previous/new quantities verified | Pass | Automated |
| TXN-01 | Transaction states | Draft transaction and stock | Draft/cancel/complete | Exercise lifecycle | Draft/cancel do not deduct; complete deducts once | All three behaviors verified | Pass | Automated |
| TXN-02 | Repeated confirmation | Completed transaction | Repeat confirm POST | Submit confirmation twice | Second request rejected; no second deduction/items | Second response 404; counts and stock unchanged | Pass | New evaluation test |
| TXN-03 | Totals/history/detail | Priced batch and cart | Quantity × Decimal price | Complete and view records | Exact line/transaction totals persist and display | Decimal total and SLE history/detail assertions pass | Pass | Automated |
| TXN-04 | Direct Sale | Staff, stock, cart | Synthetic medicine | Review and confirm | Completed transaction and exact deduction | Workflow/regression tests pass | Pass | Automated |
| TXN-05 | External Prescription | Staff, stock, metadata | Synthetic prescription | Save metadata, add item, confirm | Metadata/items retained; exact stock deduction | Workflow tests pass | Pass | Automated |
| TXN-06 | Consultation | Staff, stock, context | Synthetic consultation | Save context, review, confirm | Context retained; review gates confirmation | Workflow tests pass | Pass | Automated |
| CDSS-01 | Drug interaction | Synthetic governed rules | None/safe/LOW/MODERATE/HIGH/CRITICAL pairs | Run review | Correct PASSED/WARNING/NOT_APPLICABLE/NOT_CHECKED status and alerts | Controlled tests for all severities/statuses pass | Pass | No real clinical facts used |
| CDSS-02 | Allergy | Synthetic allergens/rules | Absent/no rule/match/missing/multiple | Run review | Conservative status and matching alerts | Structured and missing-context tests pass | Pass | Automated |
| CDSS-03 | Dosage | Synthetic dosage rules | Valid and each boundary/error case | Run review | Correct violation reason or conservative status | Range, frequency, duration, unit, age/weight tests pass | Pass | Decimal dosage logic |
| XAI-01 | Warning explanation | Synthetic warning exists | Render cart/detail | Inspect alert fields | Type, severity, medicines, reason, explanation, recommendation, source visible | Snapshot/UI assertions pass | Pass | Rendered integration tests |
| XAI-02 | ML explanation | Active synthetic model | Run prediction | Inspect assessment/UI | Raw/final priority, version, confidence, features, path, explanation, disclaimer | ML safety tests pass | Pass | Technical integration only |
| SAFE-01 | Priority safety guards | HIGH/CRITICAL deterministic alert | Model predicts LOW | Run prediction | HIGH→at least HIGH; CRITICAL→CRITICAL | Raw LOW retained; final guarded values correct | Pass | Automated |
| SAFE-02 | ML authority boundary | Missing/corrupt model | Review and confirmation | Run deterministic review and confirm | ML unavailable is visible; deterministic workflow continues | Failure tests pass without stock corruption | Pass | Automated |
| GOV-01 | Lifecycle eligibility | Rules in every lifecycle/date state | Run clinical checks | Evaluate rules | Only ACTIVE and effective current version used | Draft/review/approved/future/expired/retired/superseded tests pass | Pass | Automated |
| GOV-02 | History/audit | Versioned rule and audits | Transition/version rule | View history and mutate audit attempt | Lineage visible; snapshots stable; audit append-only | Governance/reporting tests pass | Pass | Automated |
| GOV-03 | Reports/CSV | ADMIN/staff and filters | Valid/invalid filters | View/export | ADMIN-only, readable filtered output, no crash | Reporting tests and access matrix pass | Pass | Clinical governance exports |
| ERR-01 | Invalid IDs | Authenticated user | Nonexistent batch/transaction | Request detail URLs | 404, no server error | 404 observed | Pass | Automated |
| ERR-02 | Insufficient/expired stock | Draft with unavailable quantity | Confirm | Attempt completion | Clear failure; no partial items/deduction | State and stock preserved | Pass | Automated |
| DATA-01 | Relationship integrity | Test database | Orphan/negative queries | Inspect all core relations | No orphaned required relationships or negative remaining stock | No violations found | Pass | Automated evaluation check |
| PERF-01 | Query efficiency | 30 medicines/batches/transactions | Representative list/report GETs | Capture SQL queries | No obvious row-scaled N+1 behavior | Inventory 6; transaction 4; governance 6; rule report 6 | Pass | DEF-002 fixed |
| PERF-02 | Response timing | Development-scale fixture | 5 runs per endpoint | Measure test-client responses | Record honest development timings | All endpoints completed; results in evaluation report | Pass | Not enterprise benchmarking |
| UAT-01 | Human user acceptance | Representative participants recruited | UAT task script/questionnaire | Moderated sessions | Real observations and scores recorded | NOT YET EVALUATED | Pending | No participant data fabricated |

