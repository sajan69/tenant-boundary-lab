import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE','boundary.settings')
import django
django.setup()
import json
import unittest
from unittest.mock import patch
from uuid import UUID,uuid4
from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.db import connection
from django.test import Client
from tickets.auth_api import LoginLimiter
from tickets.models import Ticket
from tickets.management.commands.seed_demo import A,B,TA,TB,CA
from tests.test_boundary import privileged


def collection(tenant):return f'/api/tenants/{tenant}/tickets/'
def detail(tenant,ticket):return collection(tenant)+f'{ticket}/'
def comments(tenant,ticket):return detail(tenant,ticket)+'comments/'
def export(tenant):return f'/api/tenants/{tenant}/export/'

class ApiTests(unittest.TestCase):
    def setUp(self):
        self.clients=[];self.created_tickets=[];self.created_comments=[]
        self.users={name:get_user_model().objects.get(username=name) for name in ('alice','bob','sam')}
        with privileged() as admin:
            self.before=admin.execute('SELECT id,title,status FROM tickets_ticket WHERE id IN (%s,%s)',(TA,TB)).fetchall()
        self.limiter=patch('tickets.auth_api.login_limiter',LoginLimiter());self.limiter.start()
        self.addCleanup(self.limiter.stop)
        self.addCleanup(self.cleanup)

    def cleanup(self):
        for client in self.clients:client.logout()
        with privileged() as admin:
            for identifier in self.created_comments:admin.execute('DELETE FROM tickets_comment WHERE id=%s',(identifier,))
            for identifier in self.created_tickets:admin.execute('DELETE FROM tickets_ticket WHERE id=%s',(identifier,))
            for identifier,title,status in self.before:admin.execute('UPDATE tickets_ticket SET title=%s,status=%s WHERE id=%s',(title,status,identifier))
        connection.close()

    def client(self,user=None):
        client=Client(enforce_csrf_checks=True,HTTP_HOST='127.0.0.1')
        self.clients.append(client)
        if user:client.force_login(self.users[user])
        response=client.get('/api/session/');self.assertEqual(response.status_code,200,response.content)
        client.csrf=response.json()['csrf_token'];return client

    def call(self,client,method,path,data=None,**headers):
        if method=='GET':response=client.get(path,**headers)
        else:response=client.generic(method,path,data=json.dumps(data if data is not None else {}),content_type='application/json',HTTP_X_CSRFTOKEN=client.csrf,**headers)
        if response.get('Content-Type','').startswith('application/json'):
            value=response.json()
            if 'csrf_token' in value:client.csrf=value['csrf_token']
            if response.status_code==201:
                if 'ticket' in value:self.created_tickets.append(UUID(value['ticket']['id']))
                if 'comment' in value:self.created_comments.append(UUID(value['comment']['id']))
        return response

    def test_actual_login_rotates_csrf_and_session_then_logout_invalidates_replay(self):
        client=self.client();old_csrf=client.cookies['csrftoken'].value
        anonymous=client.session;anonymous['probe']='before-login';anonymous.save()
        old_session=client.cookies['sessionid'].value
        response=self.call(client,'POST','/api/login/',{'username':'alice','password':os.environ['BOUNDARY_DEMO_PASSWORD']})
        self.assertEqual(response.status_code,200,response.content);self.assertEqual(response.json()['user'],{'username':'alice'})
        self.assertNotEqual(client.cookies['csrftoken'].value,old_csrf)
        session=client.cookies['sessionid'].value
        self.assertNotEqual(session,old_session)
        with privileged() as admin:self.assertEqual(admin.execute('SELECT count(*) FROM django_session WHERE session_key=%s',(old_session,)).fetchone()[0],0)
        self.assertTrue(client.cookies['sessionid']['httponly']);self.assertTrue(client.cookies['csrftoken']['httponly'])
        self.assertEqual(self.call(client,'GET',collection(A)).status_code,200)
        self.assertEqual(self.call(client,'POST','/api/logout/').status_code,200)
        client.cookies['sessionid']=session
        self.assertEqual(self.call(client,'GET',collection(A)).status_code,401)

    def test_missing_login_and_write_csrf_are_rejected(self):
        client=self.client()
        response=client.post('/api/login/',data=json.dumps({'username':'alice','password':os.environ['BOUNDARY_DEMO_PASSWORD']}),content_type='application/json')
        self.assertEqual(response.status_code,403);self.assertEqual(response.json()['error'],'csrf_failed')
        client=self.client('alice')
        self.assertEqual(client.post(collection(A),data='{"title":"Denied"}',content_type='application/json').status_code,403)
        self.assertEqual(client.patch(detail(A,TA),data='{"status":"closed"}',content_type='application/json').status_code,403)
        self.assertEqual(client.post('/api/logout/',data='{}',content_type='application/json').status_code,403)

    def test_wrong_password_and_unknown_user_have_same_public_error(self):
        client=self.client()
        responses=[self.call(client,'POST','/api/login/',{'username':name,'password':'wrong-password'}) for name in ('alice','unknown-user')]
        self.assertEqual([r.status_code for r in responses],[401,401])
        self.assertEqual(responses[0].json(),responses[1].json())
        self.assertNotIn('sessionid',client.cookies)

    def test_login_rate_limit_ignores_forwarded_peer_headers(self):
        client=self.client()
        with patch('tickets.auth_api.login_limiter',LoginLimiter(attempts=1)):
            first=self.call(client,'POST','/api/login/',{'username':'unknown','password':'wrong-password'},HTTP_X_FORWARDED_FOR='a')
            second=self.call(client,'POST','/api/login/',{'username':'alice','password':os.environ['BOUNDARY_DEMO_PASSWORD']},HTTP_X_FORWARDED_FOR='b')
        self.assertEqual(first.status_code,401);self.assertEqual(second.status_code,429);self.assertEqual(second['Retry-After'],'60')

    def test_tenant_list_is_bound_to_current_authenticated_user(self):
        for user,expected in [('alice',{str(A)}),('bob',{str(B)}),('sam',{str(A),str(B)})]:
            response=self.call(self.client(user),'GET','/api/tenants/')
            self.assertEqual({row['id'] for row in response.json()['tenants']},expected)
            self.assertNotIn('password',response.content.decode())

    def test_read_permission_matrix_covers_all_roles_and_tenants(self):
        cases=[('alice',A,TA,True),('alice',B,TB,False),('bob',A,TA,False),('bob',B,TB,True),('sam',A,TA,True),('sam',B,TB,True)]
        for user,tenant,ticket,allowed in cases:
            client=self.client(user)
            for path in (collection(tenant),detail(tenant,ticket),comments(tenant,ticket),export(tenant)):
                with self.subTest(user=user,path=path):self.assertEqual(self.call(client,'GET',path).status_code,200 if allowed else 403)

    def test_write_permission_matrix_covers_editors_viewers_and_nonmembers(self):
        cases=[('alice',A,TA,True),('alice',B,TB,False),('bob',A,TA,False),('bob',B,TB,False),('sam',A,TA,False),('sam',B,TB,True)]
        for user,tenant,ticket,allowed in cases:
            client=self.client(user)
            for method,path,data,success in [('POST',collection(tenant),{'title':'Matrix probe'},201),('PATCH',detail(tenant,ticket),{'title':'Matrix probe'},200),('POST',comments(tenant,ticket),{'body':'Matrix probe'},201)]:
                with self.subTest(user=user,path=path):self.assertEqual(self.call(client,method,path,data).status_code,success if allowed else 403)

    def test_anonymous_domain_endpoints_require_authentication(self):
        client=self.client()
        for method,path,data in [('GET','/api/tenants/',None),('GET',collection(A),None),('GET',detail(A,TA),None),('GET',comments(A,TA),None),('GET',export(A),None),('POST',collection(A),{'title':'Denied'}),('PATCH',detail(A,TA),{'status':'closed'}),('POST',comments(A,TA),{'body':'Denied'})]:
            with self.subTest(path=path,method=method):self.assertEqual(self.call(client,method,path,data).status_code,401)

    def test_cross_tenant_object_ids_are_indistinguishable_from_missing_ids(self):
        client=self.client('alice')
        for path in (detail(A,TB),detail(A,uuid4()),comments(A,TB)):
            self.assertEqual(self.call(client,'GET',path).status_code,404)
        self.assertEqual(self.call(client,'PATCH',detail(A,TB),{'title':'Denied'}).status_code,404)
        self.assertEqual(self.call(client,'POST',comments(A,TB),{'body':'Denied'}).status_code,404)

    def test_unknown_owner_and_identity_fields_are_rejected_without_mutation(self):
        client=self.client('alice')
        for key in ('tenant_id','created_by_id','user_id','id'):
            with self.subTest(key=key):self.assertEqual(self.call(client,'POST',collection(A),{'title':'Denied',key:str(B)}).status_code,400)
        self.assertEqual(self.call(client,'PATCH',detail(A,TA),{'tenant_id':str(B)}).status_code,400)
        self.assertEqual(self.call(client,'POST',comments(A,TA),{'body':'Denied','author_id':self.users['sam'].id}).status_code,400)
        self.assertEqual(self.call(client,'POST',collection(A),{'title':'Created'},HTTP_X_USER_ID=str(self.users['sam'].id)).status_code,201)
        with privileged() as admin:self.assertEqual(admin.execute('SELECT created_by_id,tenant_id FROM tickets_ticket WHERE id=%s',(self.created_tickets[-1],)).fetchone(),(self.users['alice'].id,A))

    def test_pagination_and_status_filters_have_explicit_bounds(self):
        client=self.client('alice')
        for _ in range(2):self.assertEqual(self.call(client,'POST',collection(A),{'title':'Page probe'}).status_code,201)
        first=self.call(client,'GET',collection(A)+'?limit=1').json();second=self.call(client,'GET',collection(A)+'?limit=1&offset=1').json()
        self.assertTrue(first['has_more']);self.assertEqual(first['next_offset'],1);self.assertNotEqual(first['items'][0]['id'],second['items'][0]['id'])
        for suffix in ('?limit=0','?limit=101','?offset=-1','?offset=10001','?limit=1&limit=2','?status=unknown','?sql=SELECT','?tenant_id='+str(B)):
            self.assertEqual(self.call(client,'GET',collection(A)+suffix).status_code,400)
        self.assertEqual(self.call(client,'GET',collection(A)+'?status=closed').json()['items'],[])

    def test_export_contains_only_selected_tenant_and_refuses_truncation(self):
        client=self.client('sam');response=self.call(client,'GET',export(A));value=response.json()
        self.assertEqual(response.status_code,200);self.assertEqual(response['Content-Disposition'],'attachment; filename="tenant-export.json"')
        self.assertEqual({row['tenant_id'] for row in value['tickets']},{str(A)});self.assertNotIn(str(TB),response.content.decode())
        for constant,limit,code in [('MAX_EXPORT_TICKETS',0,'export_row_limit'),('MAX_EXPORT_COMMENTS',0,'export_row_limit'),('MAX_EXPORT_BYTES',1,'export_byte_limit')]:
            with patch('tickets.api.'+constant,limit):response=self.call(client,'GET',export(A))
            self.assertEqual(response.status_code,413);self.assertEqual(response.json(),{'error':code})
            self.assertNotIn('Content-Disposition',response)

    def test_context_is_cleared_between_http_requests_on_same_connection(self):
        client=self.client('sam')
        self.assertEqual(self.call(client,'GET',detail(A,TA)).status_code,200)
        self.assertEqual(Ticket.objects.count(),0)
        self.assertEqual(self.call(client,'GET',detail(B,TB)).status_code,200)
        self.assertEqual(Ticket.objects.count(),0)
        self.assertEqual(self.call(client,'GET',detail(B,TA)).status_code,404)
        self.assertEqual(Ticket.objects.count(),0)

    def test_revocation_is_observed_without_relogin(self):
        client=self.client('alice');self.assertEqual(self.call(client,'GET',collection(A)).status_code,200)
        with privileged() as admin:admin.execute('UPDATE tickets_membership SET active=false WHERE user_id=%s AND tenant_id=%s',(self.users['alice'].id,A))
        try:
            self.assertEqual(self.call(client,'GET',collection(A)).status_code,403)
            self.assertEqual(self.call(client,'GET','/api/tenants/').json()['tenants'],[])
        finally:
            with privileged() as admin:admin.execute('UPDATE tickets_membership SET active=true WHERE user_id=%s AND tenant_id=%s',(self.users['alice'].id,A))

    def test_inactive_user_session_is_rejected_without_relogin(self):
        client=self.client('alice')
        with privileged() as admin:admin.execute('UPDATE auth_user SET is_active=false WHERE id=%s',(self.users['alice'].id,))
        try:self.assertEqual(self.call(client,'GET',collection(A)).status_code,401)
        finally:
            with privileged() as admin:admin.execute('UPDATE auth_user SET is_active=true WHERE id=%s',(self.users['alice'].id,))

    def test_origin_host_and_configuration_fail_closed_before_api_access(self):
        client=self.client('alice')
        for headers in ({'HTTP_ORIGIN':'https://attacker.invalid'},{'HTTP_SEC_FETCH_SITE':'cross-site'}):
            response=self.call(client,'GET',collection(A),**headers);self.assertEqual(response.status_code,403)
        self.assertEqual(self.call(client,'GET',collection(A),HTTP_HOST='attacker.invalid').status_code,400)
        with patch('tickets.http.verify_request_connection',side_effect=ImproperlyConfigured('private-marker')):
            response=self.call(client,'GET','/api/session/')
        self.assertEqual(response.status_code,503);self.assertNotIn('private-marker',response.content.decode())

    def test_strict_json_unknown_fields_and_text_bounds(self):
        client=self.client('alice')
        for raw in ('{"title":"a","title":"b"}','{"title":NaN}','{"title":1e999}','[]','{"title":"x","unknown":1}'):
            response=client.generic('POST',collection(A),data=raw,content_type='application/json',HTTP_X_CSRFTOKEN=client.csrf)
            self.assertEqual(response.status_code,400)
        for value in ('','x'*201,'bad\x00value','bad\ud800value',True):self.assertEqual(self.call(client,'POST',collection(A),{'title':value}).status_code,400)
        self.assertEqual(self.call(client,'PATCH',detail(A,TA),{}).status_code,400)
        self.assertEqual(self.call(client,'PATCH',detail(A,TA),{'status':'invalid'}).status_code,400)
        self.assertEqual(self.call(client,'POST',comments(A,TA),{'body':'x'*2001}).status_code,400)
        response=client.generic('POST',collection(A),data='{"title":"x"}',content_type='text/plain',HTTP_X_CSRFTOKEN=client.csrf)
        self.assertEqual(response.status_code,415)
        self.assertEqual(self.call(client,'POST',collection(A),{'title':'x'*65536}).status_code,413)

    def test_valid_edits_comments_and_literal_html_remain_json_data(self):
        client=self.client('alice');label='<img src=x onerror=alert(1)>'
        response=self.call(client,'POST',collection(A),{'title':label});self.assertEqual(response.status_code,201)
        identifier=response.json()['ticket']['id'];self.assertEqual(response.json()['ticket']['title'],label)
        response=self.call(client,'PATCH',detail(A,identifier),{'status':'closed'});self.assertEqual(response.json()['ticket']['status'],'closed')
        response=self.call(client,'POST',comments(A,identifier),{'body':'First line\n'+label});self.assertEqual(response.status_code,201)
        self.assertEqual(self.call(client,'GET',comments(A,identifier)).json()['items'][0]['body'],'First line\n'+label)

    def test_errors_and_reads_have_no_store_security_headers_and_no_cors(self):
        client=self.client('alice')
        for path in ('/api/session/',collection(A),detail(A,TB),'/api/not-a-route/'):
            response=self.call(client,'GET',path)
            self.assertEqual(response['Cache-Control'],'no-store');self.assertEqual(response['X-Content-Type-Options'],'nosniff')
            self.assertIn("frame-ancestors 'none'",response['Content-Security-Policy']);self.assertNotIn('Access-Control-Allow-Origin',response)
            self.assertTrue(response['Content-Type'].startswith('application/json'))
        self.assertEqual(self.call(client,'GET','/api/logout/').status_code,405)
        self.assertEqual(self.call(client,'DELETE',detail(A,TA)).status_code,405)
