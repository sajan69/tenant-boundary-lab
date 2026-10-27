import uuid
from django.conf import settings
from django.db import models
from django.db.models import Q

class Organization(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    name=models.CharField(max_length=100)

class Membership(models.Model):
    tenant=models.ForeignKey(Organization,on_delete=models.CASCADE)
    user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE)
    role=models.CharField(max_length=10,choices=[('viewer','Viewer'),('editor','Editor')])
    active=models.BooleanField(default=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['tenant','user'],name='one_membership_per_tenant_user'),
                     models.CheckConstraint(condition=Q(role__in=['viewer','editor']),name='valid_membership_role')]

class Ticket(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    tenant=models.ForeignKey(Organization,on_delete=models.CASCADE)
    created_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    title=models.CharField(max_length=200)
    status=models.CharField(max_length=10,default='open',choices=[('open','Open'),('closed','Closed')])
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['tenant','id'],name='ticket_tenant_identity'),
                     models.CheckConstraint(condition=Q(status__in=['open','closed']),name='valid_ticket_status')]

class Comment(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    tenant=models.ForeignKey(Organization,on_delete=models.CASCADE)
    ticket=models.ForeignKey(Ticket,on_delete=models.CASCADE)
    author=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    body=models.CharField(max_length=2000)
    created_at=models.DateTimeField(auto_now_add=True)
