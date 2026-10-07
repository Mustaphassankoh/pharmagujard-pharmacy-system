# Walkthrough: Milestone B — Public Landing Pages and Pharmacy Registration

## Implementation Status

Milestone B is complete. PharmaGuard now has a public product experience and a pharmacy-registration workflow built on the tenant foundation from Milestone A.

The milestone does not include billing, subscriptions, payments, pharmacy approval workflows, or email verification.

## Objective

Milestone B provides two related capabilities:

1. Public pages that explain the existing PharmaGuard product.
2. A secure registration flow that creates a pharmacy and its first administrator together.

The authenticated application remains separate and continues to use its existing sidebar layout.

## Public Routes

| Route | Purpose |
| --- | --- |
| `/` | Main landing page |
| `/features/` | Detailed existing-feature overview |
| `/about/` | Product purpose and academic context |
| `/how-it-works/` | End-to-end workflow explanation |
| `/register/` | Pharmacy and administrator registration |
| `/login/` | Existing authentication page |

The routes are defined in `pharmacy_system/urls.py`.

Authenticated users who visit `/` or `/register/` are redirected to `/dashboard/`.

## Public Layout

Public pages extend `templates/public/base_public.html` rather than the authenticated `base.html` application shell.

The public layout contains:

- PharmaGuard branding.
- Home navigation.
- Features navigation.
- About navigation.
- How It Works navigation.
- Login link.
- Register Pharmacy call to action.
- Public message area.
- Academic/demo footer notice.

The internal application sidebar is never rendered on public pages.

## Landing Page

The landing page is `templates/public/landing.html`.

Its sections are:

- Hero and primary calls to action.
- About PharmaGuard.
- Core feature cards.
- How It Works summary.
- Explainable clinical decision-support explanation.
- Inventory and dispensing overview.
- Governance and reporting overview.
- Academic/demo notice.
- Final registration and login call to action.

Only functionality already present in PharmaGuard is advertised.

## Existing Features Presented Publicly

The public feature content describes:

- Medicine management.
- Inventory and batch tracking.
- First-expiry, first-out allocation.
- Direct Sale.
- External Prescription.
- Consultation.
- Drug interaction checking.
- Allergy checking.
- Dosage checking.
- Explainable AI review priority.
- Clinical-rule governance.
- Reporting.

No billing, messaging, subscription, or other unimplemented feature is advertised.

## Responsive Design

Public styles are located in `static/css/style.css` under the public-product section.

The design reuses the existing PharmaGuard palette and includes responsive behavior for:

- Laptop layouts.
- Two-column tablet layouts.
- Single-column mobile layouts.
- Horizontally scrollable compact navigation on small screens.
- Responsive cards, hero content, workflow steps, calls to action, and registration form.

## Registration Form

`accounts.forms.PharmacyRegistrationForm` collects two groups of information.

### Pharmacy Information

- Pharmacy Name — required.
- Address — required.
- Phone — required.
- Email — required.
- License Number — optional.

### Administrator Information

- Full Name — required.
- Username — required.
- Email — required.
- Password — required.
- Confirm Password — required.

The form does not expose a role selector. The first user is always assigned the `ADMIN` role by the registration service.

## Validation

The form provides friendly validation for:

- An existing pharmacy name.
- An existing username.
- An administrator email already assigned to another user.
- Password and confirmation mismatch.
- Django password-validation failures.

Database constraint names and internal exceptions are not displayed to the user.

Password validation uses Django's configured validators:

- User-attribute similarity validation.
- Minimum length validation.
- Common-password validation.
- Numeric-password validation.

Passwords are passed to `User.objects.create_user()`, so Django performs the standard password hashing. Plain-text passwords are never saved.

## Atomic Registration Service

The registration service is `accounts.services.register_pharmacy_with_admin()`.

It is wrapped in `transaction.atomic` and performs:

```text
BEGIN TRANSACTION
    Create Pharmacy
    Create User with role ADMIN
    Link User to Pharmacy
COMMIT
```

If user creation or any other database operation fails, the transaction rolls back and the pharmacy is not retained.

The service returns the new pharmacy and administrator only after both records have been created successfully.

## Authentication After Registration

The registration view is `accounts.views.register_pharmacy_view`.

After successful registration:

1. The new administrator is authenticated with Django's `login()` function.
2. A success message is added.
3. The user is redirected to the dashboard.

The administrator therefore enters the pharmacy workspace without needing to submit the same credentials again.

The existing `/login/` route and Django authentication behavior remain unchanged. The login page now includes links back to the public home page and pharmacy registration.

## Academic Notice

The public pages explain that:

> PharmaGuard is an academic prototype developed for demonstration and evaluation purposes.

The landing and About content also clarify that its clinical decision-support components are not clinically validated.

## Main Files

### Python

- `pharmacy_system/urls.py`
- `accounts/forms.py`
- `accounts/services.py`
- `accounts/views.py`
- `accounts/tests.py`

### Templates

- `templates/public/base_public.html`
- `templates/public/landing.html`
- `templates/public/features.html`
- `templates/public/about.html`
- `templates/public/how_it_works.html`
- `templates/public/register.html`
- `templates/accounts/login.html`

### Styling

- `static/css/style.css`

No model change or database migration was required for Milestone B.

## Automated Tests

The Milestone B test coverage verifies:

- Landing page loads.
- Features page loads.
- About page loads.
- How It Works page loads.
- Registration page loads.
- Valid registration creates a pharmacy.
- Valid registration creates an administrator.
- Administrator role is always `ADMIN`.
- Administrator is linked to the new pharmacy.
- Password is hashed correctly.
- Successful registration logs the administrator in.
- Successful registration redirects to the dashboard.
- Duplicate username produces a friendly error.
- Duplicate email produces a friendly error.
- Duplicate pharmacy name produces a friendly error.
- Django password validation is applied.
- Failed administrator creation rolls back the pharmacy.
- Authenticated users are redirected away from public registration.
- Existing login continues to authenticate successfully.

Final verification:

```text
python manage.py test
198 tests passed

python manage.py check
System check identified no issues

python manage.py makemigrations --check --dry-run
No changes detected
```

The missing/invalid ML artifact messages produced during the full test suite are expected safety-path tests and do not indicate test failures.

## Manual Walkthrough

### 1. Review the public site

Start the development server:

```bash
python manage.py runserver
```

Open:

```text
http://127.0.0.1:8000/
```

Verify that the page shows:

- PharmaGuard branding.
- Hero statement.
- Existing product features.
- Clinical decision-support explanation.
- Academic notice.
- Login and Register Pharmacy actions.

Use the public navigation to visit Features, About, and How It Works.

### 2. Open registration

Navigate to:

```text
http://127.0.0.1:8000/register/
```

Verify the form has separate Pharmacy Information and Administrator Information sections and does not contain a role selector.

### 3. Check validation

Try submitting:

- Two different passwords.
- A common password such as `password`.
- An existing username.
- An existing administrator email.
- An existing pharmacy name.

Verify that each error is displayed next to the relevant field and that no partial pharmacy is created.

### 4. Complete registration

Submit unique pharmacy and administrator details with a valid password.

Expected result:

```text
Register Pharmacy
    → Pharmacy created
    → ADMIN user created
    → User linked to Pharmacy
    → User logged in
    → Dashboard displayed
```

### 5. Confirm database relationships

Open Django Admin as a superuser and confirm:

- The pharmacy exists.
- The new user has role `ADMIN`.
- The new user references the new pharmacy.
- The password is stored as a Django password hash, not plain text.

### 6. Confirm public/private separation

While authenticated:

- Visit `/` and confirm it redirects to the dashboard.
- Visit `/register/` and confirm it redirects to the dashboard.
- Confirm internal routes still display the application sidebar.
- Log out and confirm public pages remain accessible without authentication.

## Next Milestone Readiness

PharmaGuard can now onboard a pharmacy and its first administrator without manual database work.

Future milestones may build on this foundation for staff invitations, pharmacy profile management, or other tenant administration. Those capabilities were intentionally not introduced here.
