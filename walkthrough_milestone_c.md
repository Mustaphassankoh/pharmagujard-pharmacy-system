# Walkthrough: Milestone C — Tenant Data Isolation

## Implementation Status

Milestone C is complete. Tenant isolation is now enforced server-side across PharmaGuard’s authenticated application.

Normal administrators and pharmacy staff can access only records belonging to their assigned pharmacy. Superusers retain platform-wide access for maintenance and inspection.

No staff self-management functionality was introduced.

## Security Principle

The central rule is:

> A normal authenticated user may only read, create, update, or use data belonging to their pharmacy.

Isolation is enforced in querysets, direct object lookups, forms, services, clinical-rule evaluation, governance reporting, CSV exports, and Django Admin. It does not depend on hidden navigation links.

## Tenant Query Architecture

Shared tenant helpers are defined in `accounts/tenancy.py`.

### `scope_queryset()`

Restricts a queryset using the authenticated user’s pharmacy.

```python
scope_queryset(Medicine.objects.all(), request.user)
```

Superusers receive the complete queryset. Normal users receive records matching their `pharmacy_id`.

### `scope_to_pharmacy()`

Scopes a queryset to an explicitly supplied Pharmacy object. This is useful in service code that already has a trusted tenant context.

### `get_tenant_object_or_404()`

Combines tenant scoping with object retrieval. A guessed identifier belonging to another pharmacy behaves as an unavailable resource.

```python
get_tenant_object_or_404(
    DispensingTransaction.objects.all(),
    request.user,
    pk=transaction_id,
)
```

Cross-tenant direct URL requests therefore return `404` rather than exposing whether the foreign record exists.

## Query Audit

The milestone audited querysets and object lookups across:

- Dashboard.
- Medicines and categories.
- Inventory and batches.
- Stock transactions.
- Direct Sale.
- External Prescription.
- Consultation.
- Dispensing transaction history.
- Clinical checks and alerts.
- Allergens and clinical rules.
- Governance dashboards and reports.
- Rule and audit histories.
- CSV exports.
- Django Admin.

The audit identified remaining global queries in stock history, service-layer medicine re-fetches, clinical rule evaluation, governance reporting, audit views, CSV exports, and form relationship choices. Those paths are now tenant-scoped.

## Dashboard Isolation

Dashboard medicine totals use the tenant-scoped Medicine queryset.

The current dashboard’s available metrics therefore include only the signed-in user’s pharmacy data. Future metrics should use the same helper rather than querying global model managers directly.

## Medicine and Category Isolation

The following operations are pharmacy-scoped:

- Category list.
- Category creation and editing.
- Category status changes.
- Medicine list and filters.
- Medicine detail.
- Medicine creation and editing.
- Medicine status changes.
- Medicine search used by dispensing carts.

Direct access to another pharmacy’s medicine or category is rejected.

Medicine forms show categories from the current pharmacy only. Duplicate checks are also performed within the current pharmacy rather than across all tenants.

## Inventory Isolation

Inventory isolation covers:

- Inventory overview.
- Low-stock results.
- Expiry alerts.
- Batch list.
- Batch detail.
- Batch creation and editing.
- Stock adjustments.
- Stock transaction history.

Batch forms show only medicines owned by the current pharmacy.

Stock service functions verify that the user and selected medicine or batch belong to the same pharmacy. This prevents service calls from bypassing the view-level tenant filter.

## FEFO and Dispensing Isolation

FEFO remains medicine-relative, and Medicine is pharmacy-owned. Transaction confirmation now adds an explicit tenant boundary:

1. Lock the dispensing transaction.
2. Confirm that the acting user belongs to the transaction pharmacy.
3. Re-fetch each cart medicine from the transaction pharmacy.
4. Lock eligible batches belonging to that medicine.
5. Allocate through FEFO.
6. Create dispensing and stock records.

A forged cart containing another pharmacy’s medicine ID cannot be confirmed.

The medicine-search API and add-to-cart views are also tenant-scoped, so foreign medicines cannot be selected through normal or manipulated requests.

## Transaction and Consultation Isolation

Isolation applies to:

- Transaction list.
- Transaction detail.
- Draft cart routes.
- Direct Sale routes.
- External Prescription routes.
- Consultation routes.
- Clinical-review routes.
- Confirmation and cancellation routes.

Accessing another pharmacy’s transaction ID directly returns `404` or is rejected before processing.

Consultation forms show structured allergens from the current pharmacy only. Submitted foreign allergen IDs fail form validation.

## Clinical Rule Isolation

The deterministic clinical checks now use the pharmacy from the dispensing transaction.

### Drug interactions

Only medicines and `DrugInteractionRule` records belonging to the transaction pharmacy are considered.

### Allergies

Only tenant-owned medicines, structured allergens, and `AllergyRule` records are considered.

### Dosage

Only `DosageRule` records belonging to the transaction pharmacy are evaluated.

Pharmacy A’s clinical rules therefore cannot generate alerts in Pharmacy B’s consultation or dispensing review.

The Decision Tree model version remains platform-wide, as established in Milestone A.

## Clinical Governance Isolation

Governance lifecycle services now protect rules by pharmacy.

Normal administrators cannot submit, approve, activate, retire, or version another pharmacy’s rule. The service re-fetches and locks the rule through a tenant-filtered queryset.

When a normal administrator creates a rule through the governance service, its pharmacy is assigned from the administrator rather than browser-submitted tenant data.

Superseded rules are required to belong to the same pharmacy.

## Governance Reports and Audit History

Tenant scoping applies to:

- Governance dashboard counts.
- Action-required queues.
- Clinical-rule report.
- Creator and approver filters.
- Rule history and lineage.
- Recent governance activity.
- Audit report.
- Audit detail.

`ClinicalRuleAudit` does not store a duplicate pharmacy key. Audit ownership is derived from the referenced pharmacy-owned rule type and object identifier.

Rule lineage is restricted to records with the same pharmacy as the selected rule.

## CSV Export Isolation

Both governance exports are tenant-scoped:

- Clinical-rule CSV export.
- Clinical-rule audit CSV export.

A normal administrator’s export contains only their pharmacy’s rules and audits. Superusers can export cross-tenant platform data.

## Form and Dropdown Isolation

Tenant-sensitive choices are filtered before rendering and validated again during submission.

Examples include:

- Medicine category choices.
- Batch medicine choices.
- Consultation allergen choices.
- Clinical-rule medicine choices.
- Clinical-rule allergen choices.
- Rule creator and approver report filters.
- Tenant-owned Django Admin relationships.

Normal users cannot select another pharmacy through a crafted submitted pharmacy identifier. Tenant ownership is assigned from `request.user.pharmacy` or an already trusted tenant-owned parent.

## Cross-Tenant Relationship Validation

Model and service validation rejects invalid combinations such as:

- A medicine using another pharmacy’s category.
- A transaction using a user from another pharmacy.
- A dispensing item using a foreign medicine.
- A dispensing item using a batch belonging to another medicine.
- An interaction rule containing medicines from different pharmacies.
- An allergy rule combining a medicine and allergen from different pharmacies.
- A dosage rule using another pharmacy’s medicine.
- A stock operation against another pharmacy’s batch.

These checks provide defense in depth beyond form and view filtering.

## Django Admin

Django Admin behavior is:

- Superusers can inspect all pharmacies.
- Normal administrators see tenant-owned medicines, inventory, transactions, clinical records, rules, assessments, and audits only.
- Child records are scoped through their tenant-owned parent.
- Related-object choices are tenant-filtered.
- Normal administrators cannot reassign a record’s pharmacy.
- Platform-wide ML model metadata remains available according to existing governance permissions.

## Files Changed

### Shared tenancy

- `accounts/tenancy.py`
- `accounts/admin.py`

### Medicines and inventory

- `medicines/models.py`
- `medicines/forms.py`
- `medicines/views.py`
- `inventory/forms.py`
- `inventory/views.py`
- `inventory/services.py`

### Dispensing

- `dispensing/models.py`
- `dispensing/forms.py`
- `dispensing/views.py`
- `dispensing/services.py`

### Clinical governance and review

- `clinical/models.py`
- `clinical/services.py`
- `clinical/dosage.py`
- `clinical/governance.py`
- `clinical/reporting.py`
- `clinical/views.py`
- `clinical/admin.py`

### Tests

- `accounts/test_tenant_isolation.py`

No database migration was required because this milestone changed query, validation, form, service, and authorization behavior without adding schema fields.

## Two-Pharmacy Automated Test Setup

The isolation suite creates:

```text
Pharmacy A
├── Admin A
├── Staff A
├── Medicines A1 and A2
├── Batch A
├── Stock transaction A
├── Consultation transaction A
├── Allergen A
├── Clinical rule A
└── Governance audit A

Pharmacy B
├── Admin B
├── Staff B
├── Medicines B1 and B2
├── Batch B
├── Stock transaction B
├── Consultation transaction B
├── Allergen B
├── Clinical rule B
└── Governance audit B
```

It also creates an unassigned platform superuser.

## Isolation Tests

The dedicated tests verify:

- Admin A sees Pharmacy A medicines only.
- Staff A sees Pharmacy A medicines only.
- Admin B does not see Pharmacy A medicines.
- Medicine detail URL isolation.
- Inventory list isolation.
- Batch list and detail isolation.
- Stock transaction isolation.
- Transaction list and detail isolation.
- Consultation direct URL isolation.
- Governance dashboard isolation.
- Rule report isolation.
- Rule-history URL isolation.
- Audit-detail URL isolation.
- Rule CSV isolation.
- Audit CSV isolation.
- Category dropdown isolation.
- Batch medicine dropdown isolation.
- Consultation allergen isolation.
- Cross-tenant clinical-rule rejection.
- Manipulated cart submission rejection.
- Superuser cross-tenant visibility.

Results:

```text
Dedicated tenant-isolation suite
8 tests passed

Full regression suite
206 tests passed

python manage.py check
System check identified no issues

python manage.py makemigrations --check --dry-run
No changes detected
```

Expected missing/invalid ML artifact messages appear during dedicated safety-path tests and do not represent failures.

## Manual Verification

### 1. Prepare two pharmacies

Using registration or Django Admin, create:

- Pharmacy A with Admin A and Staff A.
- Pharmacy B with Admin B and Staff B.

Create separate medicines, batches, transactions, allergens, and rules for each.

### 2. Verify Pharmacy A

Sign in as Admin A and check:

- Dashboard totals exclude Pharmacy B.
- Medicine and inventory lists exclude Pharmacy B.
- Batch and stock history exclude Pharmacy B.
- Transaction history excludes Pharmacy B.
- Governance reports and exports exclude Pharmacy B.
- Medicine, allergen, and category dropdowns exclude Pharmacy B.

Repeat applicable operational checks as Staff A.

### 3. Attempt direct URL access

While signed in as an A user, copy the identifier of a Pharmacy B:

- Medicine.
- Batch.
- Dispensing transaction.
- Consultation.
- Clinical rule history.
- Governance audit.

Insert each identifier into the corresponding URL. The request should return `404` or be denied without showing the foreign record.

### 4. Verify Pharmacy B

Sign in as Admin B and confirm the same isolation in the opposite direction.

### 5. Verify exports

Download the rule and audit CSV exports as Admin A. Search the files for Pharmacy B medicine names, rule sources, and users. None should appear.

Repeat as Admin B.

### 6. Verify superuser access

Sign in as a Django superuser and confirm that Django Admin and cross-tenant reporting can inspect both pharmacies for platform maintenance.

## Security Outcome

Tenant separation is enforced through multiple layers:

```text
Authenticated User
       │
       ▼
Tenant-scoped View Query
       │
       ▼
Tenant-filtered Form Choices
       │
       ▼
Tenant-aware Service Re-fetch
       │
       ▼
Cross-tenant Model Validation
       │
       ▼
Tenant-owned Records and Audit Evidence
```

This layered approach protects normal UI usage, manipulated requests, guessed URLs, forged relationship identifiers, and service-level calls.

## Next Milestone Readiness

PharmaGuard now has the tenant boundary required before introducing pharmacy staff self-management or invitations.

Any future feature that reads or creates tenant-owned data should use the shared tenancy helpers and preserve the same service-layer validation pattern.
