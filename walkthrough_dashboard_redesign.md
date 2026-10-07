# PharmaGuard Dashboard Redesign Walkthrough

## Outcome

The authenticated pharmacy dashboard now presents a focused operational overview without adding unnecessary widgets or dependencies. It retains PharmaGuard's existing visual language and contains only the approved areas:

1. Top summary cards
2. Operational Activity
3. Transactions Over the Past 7 Days

All displayed metrics come from existing tenant-scoped pharmacy data.

## Dashboard structure

### Top summary cards

The first row contains four responsive cards:

- **Total Medicines** — number of medicine records belonging to the signed-in user's pharmacy.
- **Low Stock Alerts** — medicines whose usable stock is at or below their configured minimum stock level. Only active, unexpired batches with remaining stock contribute to the available-stock total.
- **Today's Sales** — total value in SLE of transactions completed today.
- **Pending Prescriptions** — external-prescription transactions that are still in draft status.

The cards reuse the existing card, typography, spacing, colour, and status conventions. Supporting text explains what each value represents.

### Operational Activity

This section provides a compact snapshot of completed activity for the current day:

- Direct sales
- Consultations
- External prescriptions
- Medicine units dispensed

Transaction totals and dispensed quantities are calculated separately. This prevents the value of a transaction with multiple medicine items from being counted more than once.

### Transactions Over the Past 7 Days

The weekly section displays one bar for each calendar day from six days ago through today. Each bar represents the number of completed dispensing transactions on that date.

The chart is implemented with semantic HTML and CSS rather than a JavaScript charting package. It includes:

- daily transaction counts;
- weekday and date labels;
- proportional bar heights;
- a visible zero state for days with no completed transactions; and
- an accessible chart description.

## Data flow

The dashboard route remains `/dashboard/` and continues to use `accounts.views.dashboard_view`.

The view now:

1. scopes Medicine and DispensingTransaction querysets with the existing `scope_queryset` tenant helper;
2. calculates usable inventory with a filtered database aggregation;
3. filters completed transactions using the local calendar date;
4. groups today's completed transactions by workflow type;
5. separately sums completed revenue and dispensed item quantities;
6. groups completed transactions by date for the seven-day chart; and
7. fills missing dates with zero values before rendering the template.

No models, migrations, permissions, routes, dispensing behaviour, or inventory behaviour were changed.

## Files changed

| File | Purpose |
|---|---|
| `accounts/views.py` | Supplies tenant-scoped summary, operational, and seven-day data. |
| `templates/dashboard.html` | Implements the three-section dashboard layout. |
| `static/css/style.css` | Adds responsive dashboard cards, activity blocks, and chart styling. |
| `templates/base.html` | Updates the stylesheet cache version so the refreshed dashboard CSS loads after deployment. |
| `accounts/tests.py` | Tests dashboard data accuracy, tenant isolation, and required sections. |

## Responsive behaviour

- Summary cards automatically reflow based on available width.
- Operational metrics use four columns on wide screens and two columns at laptop/tablet widths.
- Section headings stack on narrow screens.
- The seven chart columns remain evenly distributed and use narrower bars on small screens.
- Existing sidebar and header behaviour is preserved.

## Automated verification

The following verification completed successfully:

- `python manage.py test` using an isolated local SQLite test configuration: **226 tests passed**.
- Focused dashboard tests: **2 tests passed**.
- `python manage.py check`: no issues found.
- `python manage.py makemigrations --check --dry-run`: no changes detected.
- `git diff --check`: passed.

Expected error logs from deliberate missing-model-artifact safety tests appeared during the full suite; those tests passed.

## Manual visual test checklist

1. Restart the development server if it was started with `--noreload`.
2. Sign in and open `http://localhost:8000/dashboard/`.
3. Confirm the four top cards appear in the approved order.
4. Compare Today's Sales with completed transactions from the transaction list.
5. Confirm draft external prescriptions appear in Pending Prescriptions.
6. Confirm low-stock medicines match the Inventory and Low Stock pages.
7. Confirm Operational Activity shows today's completed workflow counts and dispensed units.
8. Confirm the weekly chart contains seven consecutive dates ending today.
9. Check that zero-activity days still have visible labels and a subtle baseline marker.
10. Resize through desktop, laptop, tablet, and mobile widths and confirm there is no horizontal page overflow.
11. Confirm the sidebar, top header, and all non-dashboard pages retain their previous appearance.

## Deployment note

The dashboard stylesheet is referenced through Django's `{% static %}` tag with the cache version `dashboard-refresh-1`. Render's existing `collectstatic --noinput` build step will include the updated tracked stylesheet during the next deployment.
