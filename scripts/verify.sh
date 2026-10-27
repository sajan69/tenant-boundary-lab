#!/usr/bin/env bash
set -euo pipefail
python scripts/bootstrap.py
python manage.py migrate --settings=boundary.migration_settings --noinput
python manage.py seed_demo --settings=boundary.migration_settings
python manage.py check_boundary
python manage.py check
python -m unittest discover -s tests -v
