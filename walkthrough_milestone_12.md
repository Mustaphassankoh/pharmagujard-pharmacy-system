# Walkthrough: Milestone 12 Interpretable ML Review-Priority Prototype

## Implementation Status

Milestone 12 is complete as a development prototype. Migration `clinical.0005` is applied to the configured development Supabase environment and exactly one model is active with explicit synthetic-development labeling. Production deployment and final clinical evaluation have not begun.

All deterministic clinical checks, warning acknowledgement, FEFO allocation, inventory deduction, dispensing, rule governance, and governance reporting remain authoritative and unchanged.

## Objective

The Decision Tree predicts only pharmacist review priority:

- `LOW`
- `MODERATE`
- `HIGH`
- `CRITICAL`

The output is advisory workflow prioritization. It does not predict:

- Diagnosis or disease.
- Patient prognosis or probability of harm.
- Whether a medicine or prescription is clinically safe.
- Treatment correctness.
- Medicine selection, recommendation, substitution, or prescribing.
- Whether deterministic warnings may be ignored.

Existing deterministic warning acknowledgement remains the only clinical confirmation gate. The ML result does not independently block dispensing.

## Architecture

The implemented sequence is:

```text
Drug Interaction Check ─┐
Allergy Check ──────────┼──> Structured Feature Extraction
Dosage Check ───────────┘               │
                                        ▼
                              DecisionTreeClassifier
                                        │
                                        ▼
                              Raw Review Priority
                                        │
                                        ▼
                         Deterministic Severity Guard
                                        │
                                        ▼
                        Final Advisory Review Priority
```

`run_clinical_review()` completes all deterministic checks before invoking the advisory predictor.

If no active model exists or inference fails, the ML component returns `NOT_AVAILABLE`. Deterministic clinical review and dispensing continue normally.

## Models

### ClinicalRiskModelVersion

Stores reproducibility and training metadata:

- Model version.
- Model type.
- Artifact path.
- Training timestamp.
- Dataset name and version.
- Ordered feature schema.
- Evaluation metrics.
- Active/inactive state.
- Notes and creation timestamp.

Activating a model version deactivates other model-version rows. Pharmacy Staff cannot manage model versions through admin.

### ClinicalRiskAssessment

Stores one assessment snapshot per transaction:

- Model version.
- Raw predicted priority.
- Final guarded priority.
- Model confidence for the raw predicted class.
- Feature snapshot.
- Actual Decision Tree path.
- Factual explanation.
- Prediction timestamp.

Persisted assessments reject in-place updates. Completed transaction pages read this stored snapshot and do not rerun inference.

## Feature Extraction

`clinical/ml/features.py` defines the ordered runtime schema and extracts features exclusively from structured clinical-review data:

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

Transaction type uses a deterministic numeric mapping:

- Direct Sale: `0`
- External Prescription: `1`
- Consultation: `2`

Excluded from model features:

- Patient or staff names.
- User identity.
- Transaction number.
- Medicine names.
- Symptoms and other free text.
- Instructions and free-text dosage.
- Acknowledgement notes.

## Synthetic Development Dataset

The dataset is located at:

```text
clinical/ml/data/synthetic_review_priority.csv
```

It is explicitly identified as:

```text
DEVELOPMENT / SYNTHETIC DATA — NOT CLINICALLY VALIDATED
```

The dataset demonstrates the integration, feature schema, deterministic encoding, training process, inference, and explanation pipeline. It does not represent Sierra Leone patients, real pharmacies, clinical outcomes, or clinical effectiveness.

## Offline Training

`clinical/ml/train_decision_tree.py` performs offline training. Training is never run during a web request.

The trainer:

1. Loads the CSV dataset.
2. Requires an exact feature and target schema.
3. Splits the data with a fixed random seed.
4. Trains `DecisionTreeClassifier`.
5. Calculates development metrics.
6. Writes the binary artifact.
7. Writes a text representation of the fitted tree.
8. Registers reproducibility metadata when run against a database.

Tree parameters:

```text
max_depth = 5
min_samples_split = 4
min_samples_leaf = 2
random_state = 42
```

The parameters deliberately constrain complexity so the tree remains interpretable.

## Artifacts

Development artifacts are stored under:

```text
clinical/ml/artifacts/
```

The trainer produces:

- `decision_tree_demo-1.joblib`
- `decision_tree_demo-1.txt`

The text artifact supports human inspection of the fitted tree. The binary artifact is loaded only by the prediction service referenced by an active model-version record.

## Evaluation Results

The isolated synthetic-development evaluation produced:

```text
Accuracy:        1.0
Macro precision: 1.0
Macro recall:    1.0
Macro F1:        1.0

Confusion matrix:
[[1, 0, 0, 0],
 [0, 1, 0, 0],
 [0, 0, 1, 0],
 [0, 0, 0, 1]]
```

These results came from a very small synthetic test split. They must not be described as real-world accuracy or evidence of clinical effectiveness.

## Prediction and Explainability

`clinical/ml/predictor.py`:

1. Finds the active model-version record.
2. Extracts structured features.
3. Requires an exact schema match.
4. Loads the referenced artifact.
5. Produces the raw priority.
6. Obtains confidence for that predicted class.
7. Traverses the fitted tree node by node.
8. Records each actual feature, observed value, comparison, threshold, and branch result.
9. Applies the deterministic priority floor.
10. Stores an immutable assessment snapshot.

The explanation is constructed from the actual fitted tree. It is not generated by an LLM.

## Deterministic Safety Guard

The model cannot downgrade deterministic severity evidence:

- A CRITICAL deterministic alert sets a `CRITICAL` minimum final priority.
- A HIGH deterministic alert sets a `HIGH` minimum final priority.
- Otherwise, the model output is retained.

Both values are stored:

- `predicted_priority`: raw Decision Tree output.
- `final_priority`: result after applying the deterministic floor.

The guard affects only the displayed review priority. It does not replace deterministic alert presentation or warning acknowledgement.

## Confidence Interpretation

`prediction_probability` is derived from `predict_proba()` for the raw predicted class.

The UI labels it as model confidence in the review-priority classification. It is not presented as probability of harm, death, treatment failure, or unsafe medication.

## User Interface

The current clinical-review panel displays:

- `AI Review Priority`.
- Final guarded priority.
- Raw model output.
- Model version.
- Model confidence.
- Factual explanation.
- Decision path.
- Structured feature snapshot.

When no model is active, the panel displays:

```text
AI Review Priority: NOT_AVAILABLE
```

The panel also states:

```text
This prototype prioritizes pharmacist review. It does not diagnose,
prescribe, determine clinical safety, or override deterministic clinical
rules. Synthetic-development performance is not clinical validation.
```

Completed transaction pages display the historical stored assessment rather than rerunning the current model.

## Invalidation

`invalidate_clinical_review()` deletes a draft transaction's assessment along with stale clinical results and alerts.

The existing invalidation paths therefore cover:

- Medicine additions and removals.
- Allergy changes.
- Structured dose, frequency, and duration changes.
- Consultation age and weight changes.
- Any workflow action that invalidates deterministic clinical review.

Completed transaction assessments are retained.

## Failure Behavior

The predictor catches inference failures, logs the exception, and returns `NOT_AVAILABLE`.

It does not:

- Fabricate a fallback prediction.
- Modify deterministic results.
- Deduct stock.
- Block transaction confirmation.
- Suppress `NOT_CHECKED` clinical statuses.

## Administration and Permissions

`ClinicalRiskModelVersion` is visible to authorized clinical administrators. Training metadata and evaluation fields are read-only in admin.

`ClinicalRiskAssessment` is a read-only operational record. Pharmacy Staff cannot retrain models or activate model versions.

## Dependencies

Installed development dependencies:

```text
scikit-learn==1.7.2
joblib==1.6.0
```

The project requirements file was converted from its previous encoding so these dependencies could be recorded safely.

## Migration

Created:

```text
clinical.0005_clinicalriskmodelversion_clinicalriskassessment
```

The migration was exercised successfully in an isolated SQLite environment.

It was reviewed and applied successfully to the configured development Supabase database. It creates only the intended model-version metadata and immutable transaction-assessment structures.

## Verification Performed

Existing regression suite after ML integration:

```text
Found 141 test(s).
System check identified no issues (0 silenced).
Ran 141 tests in 9.982s
OK
```

Additional isolated checks:

```text
clinical.0005 migration applied successfully
Synthetic trainer completed successfully
No migration drift detected
Django system check: zero issues
```

Exactly one configured development model is active as `development-synthetic-1`, labeled `DEVELOPMENT / SYNTHETIC DATA — NOT CLINICALLY VALIDATED`. Dedicated tests also verify that disabling all models produces `NOT_AVAILABLE` without disrupting deterministic review or confirmation.

## Scientific Limitation

The Decision Tree component is a prototype demonstrating interpretable ML integration. Its synthetic-development performance does not establish clinical effectiveness. Clinical validation requires a representative, independently reviewed dataset, predefined evaluation protocol, external validation, bias assessment, calibration review, monitoring, and clinical governance approval.

## Updated Structure

```text
clinical/
├── admin.py
├── models.py
├── services.py
├── migrations/
│   └── 0005_clinicalriskmodelversion_clinicalriskassessment.py
└── ml/
    ├── __init__.py
    ├── features.py
    ├── predictor.py
    ├── train_decision_tree.py
    ├── data/
    │   └── synthetic_review_priority.csv
    └── artifacts/
        ├── decision_tree_demo-1.joblib
        └── decision_tree_demo-1.txt
```

Additional UI changes are in:

```text
templates/dispensing/_clinical_review.html
templates/dispensing/transaction_detail.html
```

## Dedicated Safety Verification

`clinical/test_ml_safety.py` covers exact feature schema, privacy exclusions, free-text exclusion, missing/corrupt models, fail-open clinical review and confirmation, confidence, real tree paths, explanations, HIGH/CRITICAL guards, raw/final snapshots, model version, immutability, completed-history preservation, invalidation, all transaction types, scientific UI labels, FEFO, and stock deduction.

Interactive browser verification was attempted but no browser backend was available in the execution environment. Rendered-page and workflow behavior was verified through Django integration tests; no unsupported visual-browser claim is made.

## Recommended Next Step

Milestone 12 is fully complete for development. The next action is controlled review and explicit approval before any production deployment or final clinical evaluation. No new milestone has begun.
