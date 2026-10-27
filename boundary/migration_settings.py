"""Explicit privileged management-command profile; never serve requests with it."""
from .settings import *
DATABASES['default']['USER']='boundary_owner'
DATABASES['default']['PASSWORD']=required('BOUNDARY_OWNER_PASSWORD')
