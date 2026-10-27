from django.db import migrations

USER="NULLIF(current_setting('boundary.user_id', true), '')::bigint"
TENANT="NULLIF(current_setting('boundary.tenant_id', true), '')::uuid"

def membership(table, editor=False):
    role="AND m.role = 'editor'" if editor else ''
    return f"""{table}.tenant_id = {TENANT} AND EXISTS (
        SELECT 1 FROM tickets_membership m JOIN auth_user u ON u.id=m.user_id AND u.is_active WHERE m.tenant_id = {table}.tenant_id
        AND m.user_id = {USER} AND m.active {role})"""

SQL=''
for table,author in [('tickets_ticket','created_by_id'),('tickets_comment','author_id')]:
    scope=membership(table);edit=membership(table,True)
    SQL+=f'''
ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_read ON {table} FOR SELECT USING ({scope});
CREATE POLICY tenant_insert ON {table} FOR INSERT WITH CHECK ({edit} AND {author} = {USER});
'''
    if table=='tickets_ticket':
        SQL+=f'CREATE POLICY tenant_update ON {table} FOR UPDATE USING ({edit}) WITH CHECK ({edit});\n'
SQL+='''
ALTER TABLE tickets_comment ADD CONSTRAINT comment_ticket_same_tenant
    FOREIGN KEY (tenant_id,ticket_id) REFERENCES tickets_ticket(tenant_id,id) ON DELETE CASCADE;
GRANT SELECT ON tickets_organization,tickets_membership,auth_user TO boundary_app;
GRANT UPDATE (last_login) ON auth_user TO boundary_app;
GRANT SELECT,INSERT,UPDATE,DELETE ON django_session TO boundary_app;
GRANT SELECT,INSERT ON tickets_ticket,tickets_comment TO boundary_app;
GRANT UPDATE (title,status) ON tickets_ticket TO boundary_app;
'''
REVERSE='''
REVOKE ALL ON tickets_organization,tickets_membership,auth_user,django_session,tickets_ticket,tickets_comment FROM boundary_app;
REVOKE UPDATE(last_login) ON auth_user FROM boundary_app;
REVOKE UPDATE(title,status) ON tickets_ticket FROM boundary_app;
ALTER TABLE tickets_comment DROP CONSTRAINT comment_ticket_same_tenant;
DROP POLICY tenant_update ON tickets_ticket;
'''
for table in ('tickets_ticket','tickets_comment'):
    REVERSE+=f'''
DROP POLICY tenant_insert ON {table};
DROP POLICY tenant_read ON {table};
ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;
ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;
'''

class Migration(migrations.Migration):
    dependencies=[('tickets','0001_initial'),('auth','0012_alter_user_first_name_max_length'),('sessions','0001_initial')]
    operations=[migrations.RunSQL(SQL,reverse_sql=REVERSE)]
