# Enrollment System (MVP for Regular Students) — Django

Implements the flowchart workflow with 3 roles:
- Student
- Adviser
- Admin/Finance

## 1) Setup (local dev)
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env

python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open: http://127.0.0.1:8000/

## 2) Quick demo data
- Create users in Django Admin (/admin) and set role field:
  - STUDENT
  - ADVISER
  - FINANCE
- For a student user, create:
  - Student Profile
  - Student Finance Account (balance)
  - Previous Term Subjects (passed/failed)
  - Subjects list (to select during final adviser approval)
- Student submits enlistment.
- Adviser pre-approves -> Finance checks -> Adviser final approves and adds subjects -> Student pays.

## 3) Statuses (workflow)
- SUBMITTED (Student applied)
- RETURNED (Adviser returned for revision)
- FINANCE_REVIEW (Adviser pre-approved, waiting finance)
- FINANCE_HOLD_BALANCE
- FINANCE_HOLD_ACADEMIC
- FINANCE_APPROVED (cleared)
- APPROVED_FOR_PAYMENT (Adviser final approved + subjects added)
- ENROLLED (Payment recorded / confirmed)

## 4) Environment
See `.env.example`.

## 5) Shared dev database (Docker Postgres)
If your team wants shared logins, run the database on one host machine and point everyone to it.

Host machine:
```bash
docker compose up -d
```

Everyone (including host) update `.env`:
```
DB_ENGINE=postgres
DB_NAME=enrollsys
DB_USER=enrollsys
DB_PASSWORD=enrollsys_password
DB_HOST=<HOST_LAN_IP>
DB_PORT=5432
```

Then run:
```bash
python manage.py migrate
python manage.py createsuperuser
```

## 6) Deployment (gunicorn + nginx)
Sample configs in `/deploy`.
## Admin looks unstyled (no CSS)?
This usually means `DEBUG` is off, so Django isn't serving static files.
- Copy `.env.example` to `.env`
- Make sure it contains `DEBUG=1`
- Restart the server

You can also verify:
```bash
python manage.py shell -c "from django.conf import settings; print(settings.DEBUG, settings.STATIC_URL)"
```
