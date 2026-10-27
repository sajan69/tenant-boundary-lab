"""Small JSON boundary shared by the session and tenant APIs."""
from functools import wraps
import json
import math
import unicodedata
from django.core.exceptions import ImproperlyConfigured,PermissionDenied,RequestDataTooBig,SuspiciousOperation
from django.db import DatabaseError,IntegrityError
from django.http import JsonResponse
from .boundary import verify_request_connection

MAX_BODY=65536

class ApiError(Exception):
    def __init__(self,code,status=400):self.code=code;self.status=status


def error(code,status):return JsonResponse({'error':code},status=status)


def csrf_failure(request,reason=''):return error('csrf_failed',403)


def endpoint(methods,*,authenticated=True):
    def decorate(view):
        @wraps(view)
        def wrapped(request,*args,**kwargs):
            if request.method not in methods:
                response=error('method_not_allowed',405);response['Allow']=', '.join(methods);return response
            if authenticated and not request.user.is_authenticated:return error('authentication_required',401)
            try:return view(request,*args,**kwargs)
            except ApiError as failure:return error(failure.code,failure.status)
            except PermissionDenied:return error('tenant_access_denied',403)
            except IntegrityError:return error('write_conflict',409)
            except (DatabaseError,ImproperlyConfigured):return error('service_unavailable',503)
        return wrapped
    return decorate


def query(request,allowed=()):
    if any(key not in allowed or len(request.GET.getlist(key))!=1 for key in request.GET):raise ApiError('invalid_query')


def body(request,allowed,required=()):
    query(request)
    if request.content_type!='application/json' or request.content_params.get('charset','utf-8').lower() not in ('utf-8','utf8'):
        raise ApiError('json_content_type_required',415)
    try:
        declared=request.META.get('CONTENT_LENGTH','')
        if declared and (not declared.isascii() or not declared.isdecimal() or len(declared)>10):raise ApiError('invalid_content_length')
        if declared and int(declared)>MAX_BODY:raise ApiError('body_too_large',413)
        raw=request.body
        if len(raw)>MAX_BODY:raise ApiError('body_too_large',413)
        def pairs(items):
            value={}
            for key,item in items:
                if key in value:raise ValueError('duplicate key')
                value[key]=item
            return value
        def constant(value):raise ValueError('nonfinite')
        def number(value):
            result=float(value)
            if not math.isfinite(result):raise ValueError('nonfinite')
            return result
        value=json.loads(raw.decode('utf-8'),object_pairs_hook=pairs,parse_constant=constant,parse_float=number)
    except RequestDataTooBig:raise ApiError('body_too_large',413) from None
    except (ValueError,UnicodeError,RecursionError):raise ApiError('invalid_json') from None
    if not isinstance(value,dict) or not set(required)<=value.keys() or not value.keys()<=set(allowed):raise ApiError('invalid_fields')
    return value


def text(value,maximum,*,multiline=False,strip=True):
    if not isinstance(value,str):raise ApiError('invalid_text')
    if strip:value=value.strip()
    if not value or len(value)>maximum:raise ApiError('invalid_text')
    for character in value:
        if unicodedata.category(character) in ('Cc','Cs') and not (multiline and character in '\n\r\t'):raise ApiError('invalid_text')
    return value


class ApiBoundaryMiddleware:
    def __init__(self,get_response):self.get_response=get_response
    def __call__(self,request):
        if not request.path.startswith('/api/'):return self.get_response(request)
        try:
            host=request.get_host()
            origin=request.headers.get('Origin')
            if (origin is not None and origin!=f'{request.scheme}://{host}') or request.headers.get('Sec-Fetch-Site')=='cross-site':
                response=error('origin_not_allowed',403)
            else:
                # Runs before session/auth middleware, including anonymous API paths.
                verify_request_connection()
                response=self.get_response(request)
        except SuspiciousOperation:response=error('invalid_request',400)
        except (DatabaseError,ImproperlyConfigured):response=error('service_unavailable',503)
        if response.status_code>=400 and not response.get('Content-Type','').startswith('application/json'):
            response=error('request_failed',response.status_code)
        response['Cache-Control']='no-store'
        response['Referrer-Policy']='no-referrer'
        response['Content-Security-Policy']="default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
        return response
