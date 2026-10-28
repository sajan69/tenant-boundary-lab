"""Bounded synthetic loopback measurements on a fresh disposable lab."""
import argparse
from datetime import datetime,timezone
import hashlib
from http.cookiejar import CookieJar
import json
import os
import platform
from statistics import median
import sys
from time import perf_counter
from urllib.error import HTTPError,URLError
from urllib.request import Request,build_opener,ProxyHandler,HTTPCookieProcessor,HTTPRedirectHandler
from uuid import UUID,uuid5,NAMESPACE_URL
import django
import psycopg

A=UUID('11111111-1111-4111-8111-111111111111');B=UUID('22222222-2222-4222-8222-222222222222')
TA=UUID('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa');TB=UUID('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb')
CA=UUID('cccccccc-cccc-4ccc-8ccc-cccccccccccc')


def validate(rows,repeats,requests,port,disposable):
    if disposable is not True:raise ValueError('disposable_lab_confirmation_required')
    for value,minimum,maximum in [(rows,10,200),(repeats,1,5),(requests,1,25),(port,1,65535)]:
        if type(value) is not int or not minimum<=value<=maximum:raise ValueError('invalid_workload_bounds')
    if os.environ.get('PGHOST','127.0.0.1') not in ('127.0.0.1','localhost'):raise ValueError('loopback_database_required')


def dataset(rows):
    return [{'id':str(uuid5(NAMESPACE_URL,f'tenant-boundary-benchmark-v1:{tenant}:{i}')),
             'tenant_id':str(tenant),'created_by':author,'title':f'Benchmark synthetic {tenant.hex[:4]} {i:03}',
             'status':'open' if i%2==0 else 'closed','created_at':'2026-10-01T00:00:00+00:00'}
            for tenant,author in [(A,'alice'),(B,'sam')] for i in range(rows)]


def fingerprint(rows):return hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def preflight(admin):
    users=admin.execute('SELECT username,id,is_active FROM auth_user ORDER BY username').fetchall()
    if [row[0] for row in users]!=['alice','bob','sam'] or not all(row[2] for row in users):raise ValueError('fresh_synthetic_users_required')
    if admin.execute('SELECT count(*) FROM tickets_organization').fetchone()[0]!=2:raise ValueError('fresh_synthetic_organizations_required')
    memberships=admin.execute('SELECT u.username,m.tenant_id,m.role,m.active FROM tickets_membership m JOIN auth_user u ON u.id=m.user_id ORDER BY u.username,m.tenant_id').fetchall()
    if memberships!=[('alice',A,'editor',True),('bob',B,'viewer',True),('sam',A,'viewer',True),('sam',B,'editor',True)]:raise ValueError('fresh_synthetic_memberships_required')
    tickets=admin.execute('SELECT id,tenant_id,title,status,created_at FROM tickets_ticket ORDER BY id').fetchall()
    if [(r[0],r[1],r[2],r[3]) for r in tickets]!=[(TA,A,'Synthetic Cedar request','open'),(TB,B,'Synthetic Harbor request','open')]:raise ValueError('fresh_seed_tickets_required')
    comments=admin.execute('SELECT id,tenant_id,ticket_id,body FROM tickets_comment').fetchall()
    if comments!=[(CA,A,TA,'Synthetic local comment')]:raise ValueError('fresh_seed_comment_required')
    return {name:identifier for name,identifier,_ in users},[{'id':str(r[0]),'tenant_id':str(r[1]),'title':r[2],'status':r[3],'created_at':r[4].isoformat()} for r in tickets]


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self,*args):return None

class Client:
    def __init__(self,port):
        self.base=f'http://127.0.0.1:{port}';self.csrf=''
        self.opener=build_opener(ProxyHandler({}),HTTPCookieProcessor(CookieJar()),NoRedirects())
    def call(self,path,expected=200,data=None):
        headers={'Connection':'close'}
        if data is not None:headers.update({'Content-Type':'application/json','X-CSRFToken':self.csrf})
        request=Request(self.base+path,data=json.dumps(data).encode() if data is not None else None,headers=headers,method='POST' if data is not None else 'GET')
        try:response=self.opener.open(request,timeout=2)
        except HTTPError as error:response=error
        with response:
            payload=response.read(1024*1024+1)
            if response.status!=expected or len(payload)>1024*1024:raise ValueError('unexpected_http_response')
            value=json.loads(payload)
        if isinstance(value,dict) and 'csrf_token' in value:self.csrf=value['csrf_token']
        return value


def verify(name,value,own_ids,total):
    if name=='list':
        if len(value['items'])!=min(100,total) or any(row['tenant_id']!=str(A) or row['id'] not in own_ids for row in value['items']):raise ValueError('list_scope_or_count_mismatch')
        if value['has_more']!=(total>100):raise ValueError('pagination_mismatch')
    elif name=='detail':
        if value['ticket']['id']!=str(TA) or value['ticket']['tenant_id']!=str(A):raise ValueError('detail_scope_mismatch')
    elif name=='export':
        if value['tenant_id']!=str(A) or {row['id'] for row in value['tickets']}!=own_ids:raise ValueError('export_scope_or_count_mismatch')
        if [row['id'] for row in value['comments']]!=[str(CA)]:raise ValueError('export_comment_mismatch')
    elif value!={'error':'tenant_access_denied'}:raise ValueError('denial_mismatch')


def run(rows=100,repeats=3,requests=10,port=8000,*,disposable=False):
    validate(rows,repeats,requests,port,disposable)
    generated=dataset(rows);client=None;inserted=False;results=[]
    with psycopg.connect(host=os.environ.get('PGHOST','127.0.0.1'),port=os.environ.get('PGPORT','5432'),dbname='boundary_lab',
        user=os.environ.get('PGADMIN_USER','postgres'),password=os.environ['PGADMIN_PASSWORD'],autocommit=True,connect_timeout=5) as admin:
        users,base_rows=preflight(admin)
        postgres=admin.execute('SHOW server_version').fetchone()[0]
        expected_ids={str(TA)}|{row['id'] for row in generated if row['tenant_id']==str(A)}
        try:
            with admin.transaction(),admin.cursor() as cursor:
                cursor.executemany('INSERT INTO tickets_ticket(id,tenant_id,created_by_id,title,status,created_at) VALUES(%s,%s,%s,%s,%s,%s)',
                    [(UUID(row['id']),UUID(row['tenant_id']),users[row['created_by']],row['title'],row['status'],datetime.fromisoformat(row['created_at'])) for row in generated])
            inserted=True
            client=Client(port);client.call('/api/session/');client.call('/api/login/',data={'username':'alice','password':os.environ['BOUNDARY_DEMO_PASSWORD']})
            operations=[('list',f'/api/tenants/{A}/tickets/?limit=100',200),('detail',f'/api/tenants/{A}/tickets/{TA}/',200),
                        ('export',f'/api/tenants/{A}/export/',200),('cross_tenant_denial',f'/api/tenants/{B}/tickets/',403)]
            for repeat in range(repeats):
                samples={name:[] for name,_,_ in operations}
                # Round-robin operations, one outstanding request; no warmup/cache reset.
                for _ in range(requests):
                    for name,path,status in operations:
                        started=perf_counter();value=client.call(path,expected=status);elapsed=(perf_counter()-started)*1000
                        verify(name,value,expected_ids,rows+1)
                        samples[name].append(round(elapsed,3))
                results.append({'repeat':repeat+1,'samples_ms':samples,'median_ms':{name:median(values) for name,values in samples.items()}})
        finally:
            try:
                if client is not None:client.call('/api/logout/',data={})
            finally:
                if inserted:
                    with admin.transaction(),admin.cursor() as cursor:
                        for row in generated:
                            cursor.execute('''DELETE FROM tickets_ticket t WHERE id=%s AND tenant_id=%s AND created_by_id=%s AND title=%s AND status=%s
                                AND NOT EXISTS(SELECT 1 FROM tickets_comment c WHERE c.ticket_id=t.id)''',
                                (UUID(row['id']),UUID(row['tenant_id']),users[row['created_by']],row['title'],row['status']))
                            if cursor.rowcount!=1:raise ValueError('fixture_changed_cleanup_refused')
                    preflight(admin)
    return {'schema_version':1,'source':'synthetic_disposable_lab','workload':{'generated_tickets_per_tenant':rows,'generated_ticket_count':len(generated),
        'total_tickets':2+len(generated),'total_comments':1,'tenants':2,'generated_fixture_sha256':fingerprint(generated),
        'base_seed_projection_sha256':fingerprint(base_rows),'repeats':repeats,'requests_per_operation_per_repeat':requests,
        'measured_requests':repeats*requests*4,'list_page_limit':100,'client_concurrency':1},
        'method':{'timer':'time.perf_counter wall milliseconds','transport':'IPv4 loopback HTTP; Connection: close; Python urllib; Django development server',
            'included':'request construction, HTTP, authentication/session lookup, database connection/queries/RLS, serialization, response read and client JSON decoding',
            'excluded':'fixture insertion/cleanup, login/logout/password hashing, correctness assertions, TLS, cloud network, Vite/React/browser rendering',
            'order':'round-robin list/detail/export/denial; no dedicated warmup or cache reset; setup HTTP smoke and authentication precede timing','aggregate':'median of all raw samples per operation; no baseline comparison'},
        'environment':{'python':platform.python_version(),'django':django.get_version(),'psycopg':psycopg.__version__,'postgresql':postgres,
            'recorded_at_utc':datetime.now(timezone.utc).isoformat(),'run_url':f"https://github.com/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{os.environ['GITHUB_RUN_ID']}" if os.environ.get('GITHUB_RUN_ID') else None,
            'platform':platform.platform(),'machine':platform.machine(),'logical_cpus_reported':os.cpu_count(),'code_revision':os.environ.get('GITHUB_SHA','local_unrecorded')},
        'results':results,'median_ms':{name:median(value for result in results for value in result['samples_ms'][name]) for name in results[0]['samples_ms']},
        'cleanup_verified':True,'limitations':['Single-client synthetic lab; not production throughput, load capacity or a comparative performance improvement.',
            'Shared host, development server, caches and storage affect timings; no controlled-hardware guarantee.',
            'Hash of generated rows is deterministic; base seed creation timestamps depend on setup.']}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Measure bounded authenticated reads on a fresh disposable loopback lab')
    parser.add_argument('--rows',type=int,default=100);parser.add_argument('--repeats',type=int,default=3)
    parser.add_argument('--requests',type=int,default=10);parser.add_argument('--port',type=int,default=8000)
    parser.add_argument('--disposable-lab',action='store_true');args=parser.parse_args()
    try:print(json.dumps(run(args.rows,args.repeats,args.requests,args.port,disposable=args.disposable_lab),separators=(',',':'),allow_nan=False))
    except (OSError,ValueError,KeyError,psycopg.Error,URLError):
        print('Benchmark failed; check the disposable seed, local server and workload bounds. No measurements claimed.',file=sys.stderr);sys.exit(1)
