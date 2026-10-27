"""Exercise a running loopback lab over real HTTP using only synthetic seed users."""
import argparse
from http.cookiejar import CookieJar
import json
import os
import sys
from time import monotonic,sleep
from urllib.error import HTTPError,URLError
from urllib.request import build_opener,Request,ProxyHandler,HTTPCookieProcessor,HTTPRedirectHandler

A='11111111-1111-4111-8111-111111111111'
B='22222222-2222-4222-8222-222222222222'
TA='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
TB='bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'

class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self,*args):return None


def run(port):
    if not 1<=port<=65535:raise ValueError('invalid_port')
    password=os.environ['BOUNDARY_DEMO_PASSWORD'];cookies=CookieJar()
    opener=build_opener(ProxyHandler({}),HTTPCookieProcessor(cookies),NoRedirects())
    base=f'http://127.0.0.1:{port}';csrf=None
    def call(method,path,data=None,expected=200):
        nonlocal csrf
        headers={}
        if data is not None:headers={'Content-Type':'application/json','X-CSRFToken':csrf or ''}
        request=Request(base+path,data=json.dumps(data).encode() if data is not None else None,headers=headers,method=method)
        try:response=opener.open(request,timeout=2)
        except HTTPError as error:response=error
        with response:
            payload=response.read(1024*1024+1)
            if response.status!=expected or len(payload)>1024*1024:raise ValueError('unexpected_response')
            value=json.loads(payload)
        if isinstance(value,dict) and 'csrf_token' in value:csrf=value['csrf_token']
        return value
    deadline=monotonic()+10
    while True:
        try:call('GET','/api/session/');break
        except URLError:
            if monotonic()>=deadline:raise
            sleep(.2)
    call('POST','/api/login/',{'username':'alice','password':password})
    alice=call('GET','/api/tenants/')['tenants']
    if {row['id'] for row in alice}!={A}:raise ValueError('wrong_tenant_scope')
    call('GET',f'/api/tenants/{A}/tickets/{TA}/')
    call('GET',f'/api/tenants/{B}/tickets/',expected=403)
    call('GET',f'/api/tenants/{A}/tickets/{TB}/',expected=404)
    report=call('GET',f'/api/tenants/{A}/export/')
    if any(row['tenant_id']!=A for row in report['tickets']):raise ValueError('wrong_export_scope')
    call('POST','/api/logout/',{})
    call('GET',f'/api/tenants/{A}/tickets/',expected=401)
    call('POST','/api/login/',{'username':'bob','password':password})
    if {row['id'] for row in call('GET','/api/tenants/')['tenants']}!={B}:raise ValueError('wrong_tenant_scope')
    call('GET',f'/api/tenants/{B}/tickets/{TB}/')
    call('POST',f'/api/tenants/{B}/tickets/',{'title':'Viewer must not create'},expected=403)
    call('POST','/api/logout/',{})
    return {'source':'synthetic_seed','transport':'loopback HTTP with database-backed sessions and CSRF',
            'alice_tenants':len(alice),'cross_tenant_status':403,'foreign_object_status':404,
            'logged_out_status':401,'viewer_write_status':403,'export_scope_verified':True,
            'domain_mutations':0,'limitations':'Functional checks on a seeded local lab, not a production security or load evaluation.'}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Verify a running synthetic lab over loopback HTTP')
    parser.add_argument('--port',type=int,default=8000);args=parser.parse_args()
    try:print(json.dumps(run(args.port),indent=2))
    except (URLError,OSError,ValueError,KeyError):
        print('HTTP demo failed; check the running local server and synthetic seed configuration.',file=sys.stderr);sys.exit(1)
