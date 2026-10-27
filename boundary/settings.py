"""Local-only settings. Runtime never loads migration credentials."""
import os
from django.core.exceptions import ImproperlyConfigured


def required(name):
    value=os.environ.get(name)
    if not value: raise ImproperlyConfigured('missing_required_environment_setting: '+name)
    return value

SECRET_KEY=required('BOUNDARY_SECRET_KEY')
DEBUG=False
ALLOWED_HOSTS=['127.0.0.1','localhost']
INSTALLED_APPS=['django.contrib.auth','django.contrib.contenttypes','django.contrib.sessions','tickets']
MIDDLEWARE=['django.middleware.security.SecurityMiddleware','tickets.http.ApiBoundaryMiddleware','django.contrib.sessions.middleware.SessionMiddleware',
            'django.middleware.common.CommonMiddleware','django.middleware.csrf.CsrfViewMiddleware',
            'django.contrib.auth.middleware.AuthenticationMiddleware','django.middleware.clickjacking.XFrameOptionsMiddleware']
ROOT_URLCONF='boundary.urls'
DATABASES={'default':{'ENGINE':'django.db.backends.postgresql','NAME':'boundary_lab',
    'USER':'boundary_app','PASSWORD':required('BOUNDARY_APP_PASSWORD'),
    'HOST':os.environ.get('PGHOST','127.0.0.1'),'PORT':os.environ.get('PGPORT','5432'),
    'CONN_MAX_AGE':0,'OPTIONS':{'connect_timeout':5,'options':'-c statement_timeout=5000 -c lock_timeout=3000'}}}
DEFAULT_AUTO_FIELD='django.db.models.BigAutoField'
USE_TZ=True
TIME_ZONE='UTC'
SESSION_COOKIE_HTTPONLY=True
SESSION_COOKIE_SAMESITE='Lax'
SESSION_COOKIE_SECURE=False  # Loopback HTTP lab; not production settings.
CSRF_COOKIE_SAMESITE='Lax'
CSRF_COOKIE_SECURE=False
SESSION_COOKIE_AGE=3600
X_FRAME_OPTIONS='DENY'
DATA_UPLOAD_MAX_MEMORY_SIZE=65536
AUTH_PASSWORD_VALIDATORS=[{'NAME':'django.contrib.auth.password_validation.MinimumLengthValidator'}]

CSRF_FAILURE_VIEW="tickets.http.csrf_failure"
CSRF_COOKIE_HTTPONLY=True
