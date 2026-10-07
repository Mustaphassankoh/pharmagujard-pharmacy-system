# PharmaGuard — Academic Multi-Pharmacy Prototype

PharmaGuard is an academic multi-pharmacy prototype designed primarily for independent and community pharmacies. It combines medicine management, tenant-isolated inventory, dispensing workflows, explainable clinical decision support, clinical-rule governance, and reporting.

## Multi-Pharmacy Architecture

```text
Public Website
      ↓
Pharmacy Registration
      ↓
Pharmacy Tenant
      ↓
ADMIN
      ↓
PHARMACY_STAFF
```

Registration creates one Pharmacy tenant and its first `ADMIN` atomically. That administrator can maintain the pharmacy profile and create or deactivate `PHARMACY_STAFF` accounts through the normal application UI. Staff, medicines, inventory, transactions, clinical rules, governance records, reports, and exports are isolated by pharmacy. Django superusers retain cross-tenant access through Django Admin for platform maintenance.

The Decision Tree model registry remains platform-wide. Its output prioritizes pharmacist review only and does not replace deterministic clinical checks or pharmacist judgement.

PharmaGuard is developed for academic demonstration and evaluation. It does not include payments, subscriptions, billing, email verification, or production SaaS infrastructure, and its clinical decision-support prototype is not clinically validated.

## Technology Stack
- **Backend:** Python, Django
- **Frontend:** Django Templates, HTML5, Vanilla CSS/JS
- **Database:** PostgreSQL (Hosted on Supabase)

## Local Setup Instructions

1. **Clone the repository** (if not already done).

2. **Create a virtual environment** and activate it:
   ```bash
   python -m venv .venv

   # Windows:
   .\.venv\Scripts\activate
   # macOS/Linux:
   source .venv/bin/activate
   ```

3. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Environment Variable Setup:**
   Create a `.env` file in the project root directory. You can copy the provided `.env.example`:
   ```bash
   cp .env.example .env
   ```
   Update `.env` with your Supabase credentials:
   - `DB_NAME` (e.g., postgres)
   - `DB_USER` (e.g., postgres)
   - `DB_PASSWORD` (Your Supabase Database Password)
   - `DB_HOST` (e.g., db.your-supabase-project.supabase.co)
   - `DB_PORT` (e.g., 5432)
   - `SECRET_KEY` (Django secret key)
   - `DEBUG` (True or False)

5. **Run Migrations:**
   Before running the server, apply the database migrations to set up the tables (including the custom `User` model):
   ```bash
   python manage.py makemigrations
   python manage.py migrate
   ```

6. **Create a Superuser:**
   To access the Django Admin and manage users/roles:
   ```bash
   python manage.py createsuperuser
   ```

7. **Start the Development Server:**
   ```bash
   python manage.py runserver
   ```
   Access the public website at `http://127.0.0.1:8000/`. Register a pharmacy or sign in to an existing workspace.
