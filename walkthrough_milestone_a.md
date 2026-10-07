# Walkthrough: Milestone A — Pharmacy Tenant Foundation

## Implementation Status

Milestone A is complete. PharmaGuard now has a pharmacy-tenant foundation while preserving the existing workflows and data model relationships.

This milestone does not include public registration, landing pages, subscriptions, payments, billing, or email verification.

## Objective

The original system treated all application records as belonging to one implicit pharmacy. Milestone A introduces an explicit `Pharmacy` tenant so future users and data can be separated by pharmacy.

The implementation follows two rules:

1. Store a pharmacy directly on tenant root records.
2. Derive the pharmacy through an existing parent relationship for child records.

This avoids storing duplicate pharmacy keys that could become inconsistent.

## Architecture Before Milestone A

The following records were global:

- Users and roles.
- Medicine categories and medicines.
- Medicine batches and stock transactions.
- Dispensing transactions and their consultation/prescription details.
- Allergens and clinical rules.
- Clinical review records and alerts.
- ML model metadata.

Important global uniqueness constraints included category names, medicine formulations, allergens, and versioned clinical rules. Those constraints would have prevented two pharmacies from maintaining equivalent catalog or rule records.

## Pharmacy Model

`accounts.Pharmacy` is the tenant root and contains:

- `name`
- `address`
- `phone`
- `email`
- `license_number`
- `is_active`
- `created_at`
- `updated_at`

No billing or subscription fields were introduced.

## User Relationship

`accounts.User` now has an optional `pharmacy` foreign key.

Existing roles remain unchanged:

- `ADMIN`
- `PHARMACY_STAFF`

Normal users can belong to one pharmacy. Superusers may remain unassigned so they can perform platform-level administration across all tenants.

## Directly Pharmacy-Scoped Models

The following tenant roots now store a pharmacy relationship directly:

- `User`
- `MedicineCategory`
- `Medicine`
- `DispensingTransaction`
- `Allergen`
- `DrugInteractionRule`
- `AllergyRule`
- `DosageRule`

New dispensing transactions automatically inherit the creating user's pharmacy. New medicines can inherit the pharmacy of their category.

## Tenant Context Inherited Through Parents

The following records remain structurally scoped without adding duplicate pharmacy columns:

| Model | Tenant source |
| --- | --- |
| `MedicineBatch` | `medicine.pharmacy` |
| `StockTransaction` | `batch.medicine.pharmacy` |
| `DispensingItem` | `transaction.pharmacy` |
| `Consultation` | `transaction.pharmacy` |
| `ExternalPrescription` | `transaction.pharmacy` |
| `ClinicalReview` | `transaction.pharmacy` |
| `ClinicalCheckResult` | `transaction.pharmacy` |
| `ClinicalAlert` | `transaction.pharmacy` |
| `ClinicalRiskAssessment` | `transaction.pharmacy` |

This design prevents a child record from accidentally carrying a different pharmacy from its parent.

## Platform-Wide Models

`ClinicalRiskModelVersion` remains platform-wide. PharmaGuard continues to use one governed model registry rather than maintaining a separate ML model per pharmacy.

Role choices and static application configuration also remain platform-wide.

## Data-Preservation Migration

The migration sequence is:

1. Create `Pharmacy` and add `User.pharmacy`.
2. Add nullable pharmacy relationships to tenant root models.
3. Create `PharmaGuard Demo Pharmacy`.
4. Assign existing non-superuser users and existing application records to the demo pharmacy.
5. Add tenant-aware uniqueness constraints.

The backfill migration is `accounts.0004_backfill_default_pharmacy`.

It updates existing:

- Users, excluding superusers.
- Medicine categories.
- Medicines.
- Dispensing transactions.
- Allergens.
- Allergy, dosage, and interaction rules.

No existing application rows are deleted or recreated.

Tenant fields remain nullable at the schema boundary for platform administration and backward compatibility. Normal migrated application records receive the demo pharmacy.

## Migration Files

- `accounts/0003_pharmacy_user_pharmacy.py`
- `accounts/0004_backfill_default_pharmacy.py`
- `medicines/0002_remove_medicine_unique_medicine_formulation_and_more.py`
- `medicines/0003_medicine_unique_unassigned_medicine_formulation_and_more.py`
- `dispensing/0007_dispensingtransaction_pharmacy.py`
- `clinical/0006_remove_allergyrule_unique_versioned_medicine_allergen_rule_and_more.py`
- `clinical/0007_allergen_unique_unassigned_allergen_name_and_more.py`

## Tenant-Aware Uniqueness

These uniqueness boundaries now include pharmacy:

- Pharmacy + medicine category name.
- Pharmacy + generic name + brand name + strength + dosage form.
- Pharmacy + allergen name.
- Pharmacy + medicine A + medicine B + interaction-rule version.
- Pharmacy + medicine + allergen + allergy-rule version.

This allows two pharmacies to use the same category, formulation, allergen, or rule identity while still preventing duplicates inside one pharmacy.

Conditional fallback constraints preserve the original uniqueness protection for intentionally unassigned records.

Batch uniqueness remains `medicine + batch_number`, which is tenant-safe because Medicine is pharmacy-owned. Transaction numbers remain globally unique.

## Application Query Isolation

`accounts.tenancy.scope_queryset()` provides a shared tenant-filtering helper.

It is used by the main user-facing surfaces for:

- Dashboard medicine totals.
- Category and medicine lists/details.
- Inventory, batch, low-stock, and expiry views.
- Transaction history and transaction details.
- Medicine search used by dispensing carts.

Normal assigned users receive records from their pharmacy. Superusers receive the complete queryset. Unassigned users retain backward-compatible behavior during the transition period.

## Django Admin Behavior

The admin now displays pharmacy ownership for users, catalog records, transactions, allergens, and clinical rules.

- Superusers can inspect all pharmacies.
- Normal administrators are restricted to their pharmacy.
- Derived models such as batches and dispensing items are filtered through their tenant-owned parent.
- Normal administrators cannot reassign tenant-owned objects to another pharmacy.
- The platform-wide ML model registry is not tenant-filtered.

## Automated Tests

Tenant-foundation tests cover:

- Pharmacy creation.
- Linking a user to a pharmacy.
- Superusers without a pharmacy.
- Transaction pharmacy inheritance.
- Equivalent category names in different pharmacies.
- Equivalent medicine formulations in different pharmacies.
- Duplicate prevention inside one pharmacy.
- Clinical knowledge pharmacy fields.
- Tenant-limited normal-admin querysets.
- Presence of the default-pharmacy migration.
- Preservation of the legacy database uniqueness safety net.

Final verification results:

```text
python manage.py test
190 tests passed

python manage.py check
System check identified no issues

python manage.py makemigrations --check --dry-run
No changes detected
```

The logged missing/invalid ML artifact errors during the test suite are expected safety-path tests and do not represent failures.

## Manual Verification

After applying migrations in a target environment:

1. Open Django Admin as a superuser.
2. Confirm `PharmaGuard Demo Pharmacy` exists under Pharmacies.
3. Confirm existing non-superuser accounts reference that pharmacy.
4. Confirm existing medicines, categories, transactions, allergens, and clinical rules reference it.
5. Create two pharmacies and add the same category name to both.
6. Confirm a duplicate category inside one pharmacy is rejected.
7. Sign in as a normal administrator and confirm other-pharmacy records are not listed.
8. Sign in as a superuser and confirm records from both pharmacies are visible.

Apply migrations with:

```bash
python manage.py migrate
```

## Files Updated

The main implementation files are:

- `accounts/models.py`
- `accounts/admin.py`
- `accounts/views.py`
- `accounts/tenancy.py`
- `accounts/tests.py`
- `medicines/models.py`
- `medicines/views.py`
- `medicines/admin.py`
- `inventory/views.py`
- `inventory/admin.py`
- `dispensing/models.py`
- `dispensing/views.py`
- `dispensing/admin.py`
- `clinical/models.py`
- `clinical/admin.py`

## Next Milestone Readiness

The system now has the structural tenant boundary needed for a later pharmacy-onboarding workflow. A future milestone can create a pharmacy and its first `ADMIN` user without redesigning the existing inventory, dispensing, or clinical models.

Public registration and other SaaS features remain deliberately out of scope.
