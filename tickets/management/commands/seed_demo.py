import os
from uuid import UUID
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand,CommandError
from django.db import connection,transaction
from tickets.models import Organization,Membership,Ticket,Comment

A=UUID('11111111-1111-4111-8111-111111111111')
B=UUID('22222222-2222-4222-8222-222222222222')
TA=UUID('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa')
TB=UUID('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb')
CA=UUID('cccccccc-cccc-4ccc-8ccc-cccccccccccc')

class Command(BaseCommand):
    help='Seed three synthetic users and two tenants into a fresh lab database.'
    def handle(self,*args,**options):
        with connection.cursor() as cursor:
            cursor.execute('SELECT current_user')
            if cursor.fetchone()[0]!='boundary_owner':raise CommandError('seed_requires_migration_profile')
        password=os.environ.get('BOUNDARY_DEMO_PASSWORD')
        if not password or len(password)<12:raise CommandError('set_demo_password_of_at_least_12_characters')
        with transaction.atomic():
            # No overwrites or partial updates to existing user work.
            if get_user_model().objects.exists() or Organization.objects.exists():raise CommandError('seed_requires_empty_lab')
            Organization.objects.bulk_create([Organization(id=A,name='Cedar Lab'),Organization(id=B,name='Harbor Lab')])
            users={name:get_user_model().objects.create_user(name,password=password) for name in ('alice','bob','sam')}
            Membership.objects.bulk_create([Membership(tenant_id=A,user=users['alice'],role='editor'),
                Membership(tenant_id=B,user=users['bob'],role='viewer'),Membership(tenant_id=A,user=users['sam'],role='viewer'),
                Membership(tenant_id=B,user=users['sam'],role='editor')])
            for tenant,ticket,user,title in [(A,TA,users['alice'],'Synthetic Cedar request'),(B,TB,users['sam'],'Synthetic Harbor request')]:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT set_config('boundary.user_id',%s,true),set_config('boundary.tenant_id',%s,true)",[str(user.id),str(tenant)])
                Ticket.objects.create(id=ticket,tenant_id=tenant,created_by=user,title=title)
                if tenant==A:Comment.objects.create(id=CA,tenant_id=A,ticket_id=TA,author=user,body='Synthetic local comment')
        self.stdout.write('Seeded Cedar/Harbor, alice/bob/sam, two tickets and one comment. No credentials printed.')
