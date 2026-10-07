# Walkthrough: Milestone D — Staff Management and Final Multi-Pharmacy Validation

## Implementation Status

Milestone D is complete. A pharmacy administrator can now manage staff accounts and maintain the pharmacy profile from the normal PharmaGuard application. These features are tenant-scoped and unavailable to `PHARMACY_STAFF` users.

The milestone also validates the complete onboarding path and confirms that two independently registered pharmacies cannot access one another's operational or clinical data.

## Architecture

```text
Public Website
      |
      v
Pharmacy Registration
      |
      v
Pharmacy Tenant
      |
      v
ADMIN
      |
      v
PHARMACY_STAFF
```

Each public registration creates one Pharmacy and its first ADMIN. That administrator can create staff accounts, but every staff account is assigned automatically to the administrator's pharmacy and always receives the `PHARMACY_STAFF` role.

## Routes Added

| Route | Purpose | Access |
| --- | --- | --- |
| `/staff/` | List staff for the current pharmacy | ADMIN |
| `/staff/add/` | Create a pharmacy staff account | ADMIN |
| `/staff/<id>/edit/` | Edit basic staff information | ADMIN, same tenant |
| `/staff/<id>/password/` | Set a new staff password | ADMIN, same tenant |
| `/staff/<id>/deactivate/` | Deactivate a staff account | ADMIN, same tenant, POST only |
| `/pharmacy-profile/` | Edit the current pharmacy profile | ADMIN |

## Demonstration Preparation

Start the application using the project's normal development command:

```powershell
.\.venv\Scripts\python.exe manage.py runserver
```

Open `http://127.0.0.1:8000/` in a browser. Use unique names, usernames, and email addresses if the database already contains demonstration records.

## Part 1: Register the First Pharmacy

1. Open the public landing page.
2. Select **Register Pharmacy**.
3. Enter the pharmacy information and first administrator details.
4. Submit the registration form.

Expected result:

- One new Pharmacy tenant is created.
- One ADMIN user is created and linked to that pharmacy.
- The administrator is signed in automatically.
- The browser redirects to the PharmaGuard dashboard.
- No demonstration clinical rules are inserted automatically.

Registration is atomic. If administrator creation fails, the Pharmacy record is rolled back rather than leaving an incomplete tenant.

## Part 2: Review the ADMIN Sidebar

The ADMIN sidebar includes the normal application navigation and the following section:

```text
Administration
    Staff
    Pharmacy Profile
```

These links are not rendered for `PHARMACY_STAFF`. The navigation remains in its scrollable region, while only **Sign Out** is pinned in the sidebar footer.

## Part 3: Update the Pharmacy Profile

1. Select **Administration > Pharmacy Profile**.
2. Review or update:
   - Pharmacy Name
   - Address
   - Phone
   - Email
   - License Number
3. Select **Save Changes**.

Expected result:

- The updated information is saved to the current Pharmacy tenant.
- No other pharmacy is modified.
- A duplicate pharmacy name produces a friendly validation error.

## Part 4: Create a Staff Account

1. Select **Administration > Staff**.
2. Select **Add Staff Member**.
3. Enter:
   - Full Name
   - Username
   - Email
   - Password
   - Confirm Password
4. Submit the form.

Expected result:

- The account appears in the staff table.
- Its role is `PHARMACY_STAFF`.
- Its pharmacy is the signed-in administrator's pharmacy.
- There is no role or pharmacy selector.
- Django password validation is applied.
- Duplicate usernames and email addresses produce clear errors.

The staff table shows full name, username, email, role, active status, and created date.

## Part 5: Edit, Reset Password, and Deactivate

From the Staff page:

1. Select **Edit** to change the staff member's name, username, or email.
2. Select **Change Password** to securely set a new password using Django's password validation and hashing.
3. Select **Deactivate** and confirm the POST action to disable the account.

Expected result:

- Editing does not change the user's role or pharmacy.
- Passwords are never stored as plain text.
- A deactivated user can no longer authenticate.
- The record remains available for history and auditing.

## Part 6: Verify Staff Permissions

1. Sign out as the administrator.
2. Sign in with the active staff account.
3. Confirm that the normal operational navigation remains available.
4. Confirm that **Administration**, **Staff**, and **Pharmacy Profile** are absent.
5. Attempt to open `/staff/` and `/pharmacy-profile/` directly.

Expected result:

- The staff user can use permitted pharmacy workflows.
- Staff-management and pharmacy-profile requests return HTTP 403.
- Hiding navigation is only a presentation aid; authorization is enforced server-side.

## Part 7: Complete the Operational Walkthrough

As the first pharmacy's ADMIN:

1. Create a medicine category.
2. Add a medicine.
3. Add an in-date inventory batch with available quantity.
4. Create the staff account described above.

Then sign out and sign in as that staff member:

1. Open **Direct Sale**, select a medicine, enter a quantity, and complete the permitted workflow.
2. Open **External Prescription**, enter the prescription details, perform the clinical review, and complete the transaction when safe and permitted.
3. Open **Consultation**, enter the patient and medicine information, run Clinical Review, review deterministic alerts and AI review priority, and complete the transaction when safe and permitted.
4. Review the resulting transaction history and inventory movement.

Finally, sign back in as ADMIN:

1. Review reports.
2. Review clinical governance pages.
3. Confirm that dashboard totals reflect only the first pharmacy.

The AI result remains a review-priority aid. It does not replace deterministic clinical safety checks or pharmacist judgement.

## Part 8: Register a Second Pharmacy

1. Sign out completely.
2. Return to the public website.
3. Register a second pharmacy with a different name, administrator username, and email.
4. Add a different category, medicine, batch, staff member, transaction, and clinical rule for the second pharmacy.

Expected result:

- A separate Pharmacy and ADMIN are created.
- The second administrator sees only second-pharmacy staff.
- Medicine and category lists do not contain first-pharmacy records.
- Inventory totals and batches are independent.
- Transaction lists and dashboard metrics are independent.
- Clinical rules, governance data, reports, and exports are independent.

## Part 9: Cross-Tenant Direct URL Test

For a clear manual security check:

1. While signed in as Pharmacy A's administrator, note the edit URL for one Pharmacy A staff member.
2. Sign in as Pharmacy B's administrator.
3. Attempt to open the saved Pharmacy A staff edit or password URL.
4. Attempt the equivalent check with known medicine, batch, transaction, clinical-rule, and governance record identifiers.

Expected result:

- Foreign staff-management URLs return HTTP 404.
- Foreign operational and clinical records remain unavailable.
- The application does not reveal or modify the other tenant's data.

## Django Admin

Django Admin remains the platform-maintenance interface for a superuser. Normal pharmacy owners should use the PharmaGuard Staff and Pharmacy Profile pages.

The new Administration sidebar links are limited to tenant ADMIN users. A platform superuser without a Pharmacy is not directed to a tenant profile that does not exist.

## Demo Data Policy

New pharmacies are not automatically populated with synthetic clinical knowledge. Clinical rules must be deliberately created through the existing governance workflow or through a separately controlled demonstration process.

This avoids presenting demonstration data as verified pharmacy-specific clinical knowledge.

## Automated Validation

Run the focused Milestone D tests:

```powershell
.\.venv\Scripts\python.exe manage.py test accounts.test_staff_management --settings=pharmacy_system.test_settings
```

Run the complete regression suite and project checks:

```powershell
.\.venv\Scripts\python.exe manage.py test --settings=pharmacy_system.test_settings
.\.venv\Scripts\python.exe manage.py check --settings=pharmacy_system.test_settings
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run --settings=pharmacy_system.test_settings
```

Verified result at Milestone D completion:

- Focused Milestone D tests: 9 passed.
- Complete test suite: 215 passed.
- Django system check: no issues.
- Migration check: no changes detected.

The test suite includes registration, first-admin creation, staff management, staff login, profile updates, permissions, tenant-isolated dashboards, inventory, transactions, clinical rules, governance, reports, direct-URL protection, and superuser behavior.

## Main Implementation Files

- `accounts/forms.py`
- `accounts/views.py`
- `accounts/test_staff_management.py`
- `pharmacy_system/urls.py`
- `templates/base.html`
- `templates/accounts/staff_list.html`
- `templates/accounts/staff_form.html`
- `templates/accounts/staff_password.html`
- `templates/accounts/pharmacy_profile.html`
- `static/css/style.css`
- `README.md`

## Known Limitations

- PharmaGuard is an academic multi-pharmacy prototype.
- The clinical decision-support implementation is not clinically validated.
- There is no email verification or email-based password recovery.
- There are no payments, subscriptions, billing, or production SaaS services.
- The normal application supports staff deactivation but does not currently expose reactivation; a platform superuser can perform maintenance through Django Admin.
- Production deployment hardening, monitoring, backup policy, and regulatory validation remain outside this milestone.

