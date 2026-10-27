"""Integration checks against the disposable seeded PostgreSQL lab, never SQLite."""
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE','boundary.settings')
import django
django.setup()
import unittest
from uuid import uuid4
import psycopg
from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured,PermissionDenied
from django.db import connection,transaction,DatabaseError,IntegrityError
from tickets.boundary import tenant_scope,verify_request_connection
from tickets.models import Ticket,Comment,Membership
from tickets.management.commands.seed_demo import A,B,TA,TB,CA


def privileged(user='postgres'):
    password=os.environ['PGADMIN_PASSWORD'] if user=='postgres' else os.environ['BOUNDARY_OWNER_PASSWORD']
    return psycopg.connect(host=os.environ.get('PGHOST','127.0.0.1'),port=os.environ.get('PGPORT','5432'),
        dbname='boundary_lab',user=user,password=password,autocommit=True,connect_timeout=5)

class RollbackProbe(Exception):pass

class BoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verify_request_connection()
        cls.alice=get_user_model().objects.get(username='alice').id
        cls.bob=get_user_model().objects.get(username='bob').id
        cls.sam=get_user_model().objects.get(username='sam').id

    @classmethod
    def tearDownClass(cls):connection.close()

    def admin(self,sql,params=()):
        with privileged() as admin:admin.execute(sql,params)

    def test_actual_backend_is_postgresql(self):
        self.assertEqual(connection.vendor,'postgresql')
        with connection.cursor() as c:
            c.execute('SHOW server_version');print('PostgreSQL integration version:',c.fetchone()[0])

    def test_runtime_role_is_distinct_unprivileged_and_not_owner(self):
        verify_request_connection()
        with connection.cursor() as c:
            c.execute('SELECT current_user');self.assertEqual(c.fetchone()[0],'boundary_app')

    def test_migration_owner_is_rejected_for_runtime(self):
        with privileged('boundary_owner') as owner:
            with self.assertRaisesRegex(ImproperlyConfigured,'unsafe_request_database_role'):verify_request_connection(owner)

    def test_superuser_is_rejected_for_runtime(self):
        with privileged() as admin:
            with self.assertRaises(ImproperlyConfigured):verify_request_connection(admin)

    def test_absent_context_returns_no_tickets_or_comments(self):
        self.assertEqual(Ticket.objects.count(),0);self.assertEqual(Comment.objects.count(),0)

    def test_scope_filters_unqualified_queries_and_related_rows(self):
        with tenant_scope(self.alice,A) as grant:
            self.assertEqual(grant.role,'editor')
            self.assertEqual(list(Ticket.objects.values_list('id',flat=True)),[TA])
            self.assertEqual(list(Comment.objects.values_list('id',flat=True)),[CA])
            self.assertFalse(Ticket.objects.filter(id=TB).exists())
        self.assertEqual(Ticket.objects.count(),0)

    def test_same_connection_can_change_tenant_without_leaking_scope(self):
        with tenant_scope(self.sam,A):self.assertEqual(Ticket.objects.get().id,TA)
        self.assertEqual(Ticket.objects.count(),0)
        with tenant_scope(self.sam,B):self.assertEqual(Ticket.objects.get().id,TB)
        self.assertEqual(Ticket.objects.count(),0)

    def test_viewer_can_read_but_application_write_scope_is_denied(self):
        with tenant_scope(self.bob,B):self.assertEqual(Ticket.objects.get().id,TB)
        with self.assertRaises(PermissionDenied):
            with tenant_scope(self.bob,B,write=True):self.fail('viewer obtained write scope')

    def test_forged_tenant_selector_is_denied(self):
        with self.assertRaises(PermissionDenied):
            with tenant_scope(self.alice,B):self.fail('cross-tenant scope')
        self.assertEqual(Ticket.objects.count(),0)

    def test_multimembership_roles_are_tenant_specific(self):
        with self.assertRaises(PermissionDenied):
            with tenant_scope(self.sam,A,write=True):self.fail('viewer A accepted')
        with tenant_scope(self.sam,B,write=True):self.assertEqual(Ticket.objects.get().id,TB)

    def test_invalid_context_identifiers_fail_closed(self):
        for user,tenant in [(True,A),(0,A),('1',A),(self.alice,'not-a-uuid'),(2**63,A)]:
            with self.assertRaises(PermissionDenied):
                with tenant_scope(user,tenant):self.fail('invalid context')
        self.assertEqual(Ticket.objects.count(),0)

    def test_nested_tenant_context_cannot_replace_existing_scope(self):
        with tenant_scope(self.sam,A):
            with self.assertRaisesRegex(ImproperlyConfigured,'root_transaction'):
                with tenant_scope(self.sam,B):pass
            self.assertEqual(Ticket.objects.get().id,TA)

    def test_existing_outer_transaction_is_rejected(self):
        with transaction.atomic():
            with self.assertRaises(ImproperlyConfigured):
                with tenant_scope(self.alice,A):pass

    def test_manual_transaction_mode_is_rejected(self):
        connection.set_autocommit(False)
        try:
            with self.assertRaises(ImproperlyConfigured):
                with tenant_scope(self.alice,A):pass
        finally:connection.rollback();connection.set_autocommit(True)

    def test_exception_rolls_back_effect_and_clears_context(self):
        with self.assertRaises(RollbackProbe):
            with tenant_scope(self.alice,A,write=True):
                Ticket.objects.filter(id=TA).update(title='Rollback probe')
                raise RollbackProbe()
        self.assertEqual(Ticket.objects.count(),0)
        with tenant_scope(self.alice,A):self.assertEqual(Ticket.objects.get().title,'Synthetic Cedar request')

    def test_revoked_membership_denies_next_scope_and_direct_policy_read(self):
        self.admin('UPDATE tickets_membership SET active=false WHERE user_id=%s AND tenant_id=%s',(self.alice,A))
        try:
            with self.assertRaises(PermissionDenied):
                with tenant_scope(self.alice,A):pass
            with transaction.atomic():
                self.raw_context(self.alice,A);self.assertEqual(Ticket.objects.count(),0)
        finally:self.admin('UPDATE tickets_membership SET active=true WHERE user_id=%s AND tenant_id=%s',(self.alice,A))

    def test_inactive_user_denies_scope_and_policy_read(self):
        self.admin('UPDATE auth_user SET is_active=false WHERE id=%s',(self.alice,))
        try:
            with self.assertRaises(PermissionDenied):
                with tenant_scope(self.alice,A):pass
            with transaction.atomic():
                self.raw_context(self.alice,A);self.assertEqual(Ticket.objects.count(),0)
        finally:self.admin('UPDATE auth_user SET is_active=true WHERE id=%s',(self.alice,))

    @staticmethod
    def raw_context(user,tenant):
        with connection.cursor() as c:c.execute("SELECT set_config('boundary.user_id',%s,true),set_config('boundary.tenant_id',%s,true)",[str(user),str(tenant)])

    def test_tenant_only_without_user_context_has_no_rows(self):
        with transaction.atomic():
            with connection.cursor() as c:c.execute("SELECT set_config('boundary.tenant_id',%s,true)",[str(A)])
            self.assertEqual(Ticket.objects.count(),0)

    def test_policy_rejects_context_user_without_membership(self):
        with transaction.atomic():
            self.raw_context(self.alice,B);self.assertEqual(Ticket.objects.count(),0)

    def test_database_denies_viewer_insert_even_if_caller_omits_write_flag(self):
        with self.assertRaises(DatabaseError):
            with tenant_scope(self.bob,B):
                Ticket.objects.create(tenant_id=B,created_by_id=self.bob,title='Should be denied')
        self.assertEqual(Ticket.objects.count(),0)

    def test_database_viewer_update_changes_zero_rows(self):
        with tenant_scope(self.sam,A):self.assertEqual(Ticket.objects.filter(id=TA).update(title='Denied'),0)

    def test_editor_insert_and_update_work_then_rollback(self):
        identifier=uuid4()
        with self.assertRaises(RollbackProbe):
            with tenant_scope(self.alice,A,write=True):
                Ticket.objects.create(id=identifier,tenant_id=A,created_by_id=self.alice,title='Temporary synthetic ticket')
                self.assertEqual(Ticket.objects.filter(id=identifier).update(status='closed'),1)
                self.assertEqual(Ticket.objects.get(id=identifier).status,'closed')
                raise RollbackProbe()
        with tenant_scope(self.alice,A):self.assertFalse(Ticket.objects.filter(id=identifier).exists())

    def test_cross_tenant_insert_is_rejected_by_with_check(self):
        with self.assertRaises(DatabaseError):
            with tenant_scope(self.alice,A):Ticket.objects.create(tenant_id=B,created_by_id=self.alice,title='Denied')

    def test_author_spoofing_is_rejected_by_insert_policy(self):
        with self.assertRaises(DatabaseError):
            with tenant_scope(self.alice,A):Ticket.objects.create(tenant_id=A,created_by_id=self.sam,title='Denied')

    def test_cross_tenant_ticket_id_cannot_be_attached_to_local_comment(self):
        with self.assertRaises(IntegrityError):
            with tenant_scope(self.alice,A):Comment.objects.create(tenant_id=A,ticket_id=TB,author_id=self.alice,body='Denied')

    def test_authorized_comment_insert_works_then_rolls_back(self):
        with self.assertRaises(RollbackProbe):
            with tenant_scope(self.alice,A,write=True):
                row=Comment.objects.create(tenant_id=A,ticket_id=TA,author_id=self.alice,body='Temporary synthetic comment')
                self.assertEqual(Comment.objects.get(id=row.id).body,row.body);raise RollbackProbe()

    def test_runtime_cannot_promote_membership(self):
        with self.assertRaises(DatabaseError):Membership.objects.filter(user_id=self.bob).update(role='editor')

    def test_runtime_cannot_change_tenant_ownership(self):
        with self.assertRaises(DatabaseError):
            with tenant_scope(self.alice,A):Ticket.objects.filter(id=TA).update(tenant_id=B)

    def test_runtime_has_no_delete_truncate_or_schema_creation_grants(self):
        for statement in ['DELETE FROM tickets_ticket','TRUNCATE tickets_ticket','CREATE TABLE public.forbidden_probe(id integer)']:
            with self.assertRaises(DatabaseError):
                with connection.cursor() as c:c.execute(statement)

    def test_guard_rejects_disabled_rls_and_recovers_after_restoration(self):
        self.admin('ALTER TABLE tickets_ticket DISABLE ROW LEVEL SECURITY')
        try:
            with self.assertRaisesRegex(ImproperlyConfigured,'unsafe_tenant_table'):
                with tenant_scope(self.alice,A):pass
        finally:self.admin('ALTER TABLE tickets_ticket ENABLE ROW LEVEL SECURITY')
        verify_request_connection()

    def test_negative_control_superuser_bypasses_policies(self):
        with privileged() as admin:
            self.assertEqual(admin.execute('SELECT count(*) FROM tickets_ticket').fetchone()[0],2)
        self.assertEqual(Ticket.objects.count(),0)

    def test_negative_control_sql_capable_caller_can_impersonate_context(self):
        # Custom settings are not cryptographic identity or a SQL-injection boundary.
        with transaction.atomic():
            self.raw_context(self.sam,B);self.assertEqual(Ticket.objects.get().id,TB)
        self.assertEqual(Ticket.objects.count(),0)
