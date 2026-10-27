from django.http import JsonResponse
from django.urls import path
from tickets import auth_api,api

def health(request):
    return JsonResponse({'status':'ok'})

urlpatterns=[path('health/',health),path('api/session/',auth_api.session),
    path('api/login/',auth_api.sign_in),path('api/logout/',auth_api.sign_out),path('api/tenants/',auth_api.tenants),
    path('api/tenants/<uuid:tenant_id>/tickets/',api.tickets),
    path('api/tenants/<uuid:tenant_id>/tickets/<uuid:ticket_id>/',api.ticket),
    path('api/tenants/<uuid:tenant_id>/tickets/<uuid:ticket_id>/comments/',api.comments),
    path('api/tenants/<uuid:tenant_id>/export/',api.export)]
