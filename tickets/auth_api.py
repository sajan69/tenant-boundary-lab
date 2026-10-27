"""Django sessions, current membership discovery and bounded local login throttling."""
from threading import Lock
from time import monotonic
from django.contrib.auth import authenticate,login,logout
from django.http import JsonResponse
from django.middleware.csrf import get_token
from .models import Membership
from .http import ApiError,body,endpoint,query,text


class LoginLimiter:
    """Process-local fixed window, capped keys; not a distributed abuse defense."""
    def __init__(self,*,attempts=10,window=60,capacity=1024,clock=monotonic):
        self.attempts=attempts;self.window=window;self.capacity=capacity;self.clock=clock
        self.entries={};self.lock=Lock()
    def allow(self,key):
        with self.lock:
            now=self.clock()
            self.entries={key:value for key,value in self.entries.items() if now<value[0]+self.window}
            if key not in self.entries:
                if len(self.entries)>=self.capacity:return False
                self.entries[key]=(now,0)
            started,count=self.entries[key]
            if count>=self.attempts:return False
            self.entries[key]=(started,count+1);return True


login_limiter=LoginLimiter()


def session_payload(request):
    return {'user':{'username':request.user.username} if request.user.is_authenticated else None,'csrf_token':get_token(request)}


@endpoint(('GET',),authenticated=False)
def session(request):
    query(request)
    return JsonResponse(session_payload(request))


@endpoint(('POST',),authenticated=False)
def sign_in(request):
    value=body(request,('username','password'),('username','password'))
    username=text(value['username'],150);password=text(value['password'],256,strip=False)
    # Never trust X-Forwarded-For to select a quota bucket.
    if not login_limiter.allow(request.META.get('REMOTE_ADDR','unknown')):
        response=JsonResponse({'error':'login_rate_limited'},status=429);response['Retry-After']='60';return response
    user=authenticate(request,username=username,password=password)
    if user is None:raise ApiError('invalid_credentials',401)
    login(request,user)  # Rotates the session key and CSRF secret.
    return JsonResponse(session_payload(request))


@endpoint(('POST',))
def sign_out(request):
    body(request,())
    logout(request)  # Deletes the server-side session, not only the browser cookie.
    return JsonResponse(session_payload(request))


@endpoint(('GET',))
def tenants(request):
    query(request)
    rows=list(Membership.objects.filter(user_id=request.user.id,active=True,user__is_active=True)
              .select_related('tenant').order_by('tenant_id')[:101])
    if len(rows)>100:raise ApiError('membership_limit_exceeded',413)
    return JsonResponse({'tenants':[{'id':str(row.tenant_id),'name':row.tenant.name,'role':row.role} for row in rows]})
