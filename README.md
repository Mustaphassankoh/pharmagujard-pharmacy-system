# Intelligent Pharmacy Management System

This is a web-based pharmacy management system designed primarily for independent and community pharmacies. It features medicine management, inventory management, point-of-sale capabilities, and an explainable clinical decision support system.

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
   Access the application at `http://127.0.0.1:8000/`. You should be redirected to the login page.