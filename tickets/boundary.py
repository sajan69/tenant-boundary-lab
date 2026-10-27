"""Verified membership plus root-transaction-local database context."""
from contextlib import contextmanager
from dataclasses import dataclass
from uuid import UUID
from django.core.exceptions import ImproperlyConfigured, PermissionDenied
from django.db import connection, transaction
from .models import Membership


def verify_request_connection(db=connection):
    with db.cursor() as cursor:
        cursor.execute("""SELECT current_user,rolsuper,rolbypassrls,rolcreatedb,rolcreaterole,
            EXISTS(SELECT 1 FROM pg_auth_members WHERE member=pg_roles.oid)
            FROM pg_roles WHERE rolname=current_user""")
        role=cursor.fetchone()
        if not role or role[0]!='boundary_app' or any(role[1:]):
            raise ImproperlyConfigured('unsafe_request_database_role')
        cursor.execute("""SELECT c.relname,c.relrowsecurity,c.relforcerowsecurity,
            pg_get_userbyid(c.relowner)=current_user
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public' AND c.relname IN ('tickets_ticket','tickets_comment')""")
        tables=cursor.fetchall()
        if len(tables)!=2 or any(not enabled or not forced or owned for _,enabled,forced,owned in tables):
            raise ImproperlyConfigured('unsafe_tenant_table_configuration')
        cursor.execute("SELECT has_schema_privilege(current_user,'public','CREATE'),has_database_privilege(current_user,current_database(),'CREATE')")
        if any(cursor.fetchone()):raise ImproperlyConfigured('unsafe_request_database_privileges')


@dataclass(frozen=True)
class TenantGrant:
    user_id:int
    tenant_id:UUID
    role:str


@contextmanager
def tenant_scope(user_id,tenant_id,*,write=False):
    # Do not let a caller-selected tenant survive within a wider transaction.
    if connection.in_atomic_block or not connection.get_autocommit():
        raise ImproperlyConfigured('tenant_scope_requires_root_transaction')
    try:tenant_id=UUID(str(tenant_id))
    except (ValueError,TypeError,AttributeError):raise PermissionDenied('tenant_access_denied') from None
    if type(user_id) is not int or not 0<user_id<2**63:
        raise PermissionDenied('tenant_access_denied')
    verify_request_connection()
    with transaction.atomic(durable=True):
        # RLS also rechecks membership per statement under READ COMMITTED.
        membership=Membership.objects.filter(user_id=user_id,tenant_id=tenant_id,active=True,user__is_active=True).first()
        if membership is None or (write and membership.role!='editor'):
            raise PermissionDenied('tenant_access_denied')
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('boundary.user_id',%s,true),set_config('boundary.tenant_id',%s,true)",[str(user_id),str(tenant_id)])
        yield TenantGrant(user_id,tenant_id,membership.role)
