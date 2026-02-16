#!/usr/bin/env bash
set -euo pipefail

skip_migrate=0
if [[ "${1:-}" == "--skip-migrate" ]]; then
  skip_migrate=1
fi

if ! command -v python >/dev/null 2>&1; then
  echo "Python is not installed or not available in PATH." >&2
  exit 1
fi

if [[ ! -f .env ]]; then
  if [[ ! -f .env.example ]]; then
    echo "Missing both .env and .env.example in project root." >&2
    exit 1
  fi

  cp .env.example .env
  echo "Created .env from .env.example. Update DB_HOST if you are using shared Postgres."
fi

db_engine="$(grep -E '^DB_ENGINE=' .env | tail -n 1 | cut -d= -f2- | tr '[:upper:]' '[:lower:]')"
db_engine="${db_engine:-sqlite}"
if [[ "$db_engine" == "postgresql" ]]; then
  db_engine="postgres"
fi

if [[ "$db_engine" == "postgres" ]]; then
  db_host="$(grep -E '^DB_HOST=' .env | tail -n 1 | cut -d= -f2-)"
  if [[ -z "$db_host" || "$db_host" == \<* ]]; then
    echo "DB_ENGINE=postgres but DB_HOST is not set to a real host in .env." >&2
    exit 1
  fi
fi

if [[ "$skip_migrate" -eq 0 ]]; then
  python manage.py migrate
fi

python manage.py runserver
