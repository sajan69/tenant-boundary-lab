"""Fixed synthetic-fixture mutations for serial browser tests, never an API."""
import os
import sys
from uuid import UUID
import psycopg

B=UUID('22222222-2222-4222-8222-222222222222')
action=sys.argv[1]
if action not in ('revoke','restore','cleanup','check'):raise SystemExit('Unknown fixture action')
with psycopg.connect(host=os.environ.get('PGHOST','127.0.0.1'),port=os.environ.get('PGPORT','5432'),dbname='boundary_lab',
    user=os.environ.get('PGADMIN_USER','postgres'),password=os.environ['PGADMIN_PASSWORD']) as connection:
    if action in ('revoke','restore'):
        connection.execute("UPDATE tickets_membership SET active=%s WHERE tenant_id=%s AND user_id=(SELECT id FROM auth_user WHERE username='sam')",(action=='restore',B))
    elif action=='cleanup':
        identifier=UUID(sys.argv[2])
        connection.execute("DELETE FROM tickets_ticket WHERE id=%s AND tenant_id=%s AND created_by_id=(SELECT id FROM auth_user WHERE username='sam') AND title=%s",(identifier,B,'<img src=x onerror=alert(1)>'))
    else:
        assert connection.execute('SELECT count(*) FROM tickets_ticket').fetchone()[0]==2
        assert connection.execute('SELECT count(*) FROM tickets_comment').fetchone()[0]==1
