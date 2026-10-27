"""Create a fresh disposable lab database and two distinct login roles."""
import os
import sys
import psycopg
from psycopg import sql


def bootstrap():
    host=os.environ.get('PGHOST','127.0.0.1')
    if host not in ('127.0.0.1','localhost'): raise ValueError('bootstrap_requires_loopback')
    owner_password=os.environ['BOUNDARY_OWNER_PASSWORD'];app_password=os.environ['BOUNDARY_APP_PASSWORD']
    if owner_password==app_password: raise ValueError('role_passwords_must_differ')
    with psycopg.connect(host=host,port=os.environ.get('PGPORT','5432'),dbname='postgres',
        user=os.environ.get('PGADMIN_USER','postgres'),password=os.environ['PGADMIN_PASSWORD'],autocommit=True,connect_timeout=5) as admin:
        with admin.cursor() as cursor:
            cursor.execute("SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname='boundary_lab') OR EXISTS(SELECT 1 FROM pg_roles WHERE rolname IN ('boundary_owner','boundary_app'))")
            if cursor.fetchone()[0]:raise ValueError('lab_database_or_roles_already_exist')
            # Advisory lock serializes this bootstrap on the same administrative database.
            cursor.execute('SELECT pg_advisory_lock(842731)')
            try:
                cursor.execute("SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname='boundary_lab') OR EXISTS(SELECT 1 FROM pg_roles WHERE rolname IN ('boundary_owner','boundary_app'))")
                if cursor.fetchone()[0]: raise ValueError('lab_database_or_roles_already_exist')
                for role,password in [('boundary_owner',owner_password),('boundary_app',app_password)]:
                    cursor.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {}').format(sql.Identifier(role),sql.Literal(password)))
                cursor.execute('CREATE DATABASE boundary_lab OWNER boundary_owner')
                cursor.execute('REVOKE ALL ON DATABASE boundary_lab FROM PUBLIC')
                cursor.execute('GRANT CONNECT ON DATABASE boundary_lab TO boundary_app')
            finally:cursor.execute('SELECT pg_advisory_unlock(842731)')
    with psycopg.connect(host=host,port=os.environ.get('PGPORT','5432'),dbname='boundary_lab',user='boundary_owner',password=owner_password,autocommit=True) as owner:
        owner.execute('REVOKE ALL ON SCHEMA public FROM PUBLIC')
        owner.execute('GRANT USAGE ON SCHEMA public TO boundary_app')
    print('Created fresh boundary_lab with separate migration and request roles.')

if __name__=='__main__':
    try:bootstrap()
    except (psycopg.Error,KeyError,ValueError) as error:
        code=str(error) if isinstance(error,ValueError) else 'bootstrap_failed_check_local_configuration'
        print(code,file=sys.stderr);sys.exit(2)
