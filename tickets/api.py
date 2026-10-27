"""Bounded tenant-domain API; all database results materialize inside scope."""
import json
from django.http import HttpResponse,JsonResponse
from .boundary import tenant_scope
from .models import Ticket,Comment
from .http import ApiError,body,endpoint,query,text

PAGE_SIZE=25
MAX_PAGE=100
MAX_OFFSET=10000
MAX_EXPORT_TICKETS=1000
MAX_EXPORT_COMMENTS=2000
MAX_EXPORT_BYTES=1024*1024


def pagination(request,*,status=False):
    query(request,('limit','offset','status') if status else ('limit','offset'))
    values=[]
    for key,default,maximum in [('limit',PAGE_SIZE,MAX_PAGE),('offset',0,MAX_OFFSET)]:
        raw=request.GET.get(key,str(default))
        if not raw.isascii() or not raw.isdecimal() or len(raw)>5:raise ApiError('invalid_pagination')
        value=int(raw)
        if not (1 if key=='limit' else 0)<=value<=maximum:raise ApiError('invalid_pagination')
        values.append(value)
    if status and request.GET.get('status') not in (None,'open','closed'):raise ApiError('invalid_status')
    return values


def page(rows,limit,offset,serialize):
    more=len(rows)>limit
    return {'items':[serialize(row) for row in rows[:limit]],'limit':limit,'offset':offset,'has_more':more,
            'next_offset':offset+limit if more and offset+limit<=MAX_OFFSET else None,
            'pagination_limit_reached':more and offset+limit>MAX_OFFSET}


def ticket_json(row):
    return {'id':str(row.id),'tenant_id':str(row.tenant_id),'title':row.title,'status':row.status,'created_at':row.created_at.isoformat()}


def comment_json(row):
    return {'id':str(row.id),'ticket_id':str(row.ticket_id),'body':row.body,'created_at':row.created_at.isoformat()}


def get_ticket(tenant_id,ticket_id):
    row=Ticket.objects.filter(tenant_id=tenant_id,id=ticket_id).first()
    if row is None:raise ApiError('not_found',404)
    return row


def ticket_fields(value,*,create=False):
    if not value or (create and 'title' not in value):raise ApiError('invalid_fields')
    result={}
    if 'title' in value:result['title']=text(value['title'],200)
    if 'status' in value:
        if value['status'] not in ('open','closed'):raise ApiError('invalid_status')
        result['status']=value['status']
    return result


@endpoint(('GET','POST'))
def tickets(request,tenant_id):
    if request.method=='GET':
        limit,offset=pagination(request,status=True)
        with tenant_scope(request.user.id,tenant_id) as grant:
            rows=Ticket.objects.filter(tenant_id=grant.tenant_id)
            if request.GET.get('status'):rows=rows.filter(status=request.GET['status'])
            rows=list(rows.order_by('id')[offset:offset+limit+1])
            return JsonResponse(page(rows,limit,offset,ticket_json))
    value=ticket_fields(body(request,('title','status'),('title',)),create=True)
    with tenant_scope(request.user.id,tenant_id,write=True) as grant:
        row=Ticket.objects.create(tenant_id=grant.tenant_id,created_by_id=grant.user_id,**value)
        return JsonResponse({'ticket':ticket_json(row)},status=201)


@endpoint(('GET','PATCH'))
def ticket(request,tenant_id,ticket_id):
    if request.method=='GET':
        query(request)
        with tenant_scope(request.user.id,tenant_id) as grant:
            return JsonResponse({'ticket':ticket_json(get_ticket(grant.tenant_id,ticket_id))})
    value=ticket_fields(body(request,('title','status')))
    with tenant_scope(request.user.id,tenant_id,write=True) as grant:
        row=get_ticket(grant.tenant_id,ticket_id)
        updated=Ticket.objects.filter(tenant_id=grant.tenant_id,id=row.id).update(**value)
        if updated!=1:raise ApiError('write_conflict',409)
        return JsonResponse({'ticket':ticket_json(get_ticket(grant.tenant_id,row.id))})


@endpoint(('GET','POST'))
def comments(request,tenant_id,ticket_id):
    if request.method=='GET':
        limit,offset=pagination(request)
        with tenant_scope(request.user.id,tenant_id) as grant:
            row=get_ticket(grant.tenant_id,ticket_id)
            rows=list(Comment.objects.filter(tenant_id=grant.tenant_id,ticket_id=row.id).order_by('id')[offset:offset+limit+1])
            return JsonResponse(page(rows,limit,offset,comment_json))
    value=body(request,('body',),('body',));content=text(value['body'],2000,multiline=True)
    with tenant_scope(request.user.id,tenant_id,write=True) as grant:
        row=get_ticket(grant.tenant_id,ticket_id)
        comment=Comment.objects.create(tenant_id=grant.tenant_id,ticket_id=row.id,author_id=grant.user_id,body=content)
        return JsonResponse({'comment':comment_json(comment)},status=201)


@endpoint(('GET',))
def export(request,tenant_id):
    query(request)
    with tenant_scope(request.user.id,tenant_id) as grant:
        tickets=list(Ticket.objects.filter(tenant_id=grant.tenant_id).order_by('id')[:MAX_EXPORT_TICKETS+1])
        comments=list(Comment.objects.filter(tenant_id=grant.tenant_id).order_by('id')[:MAX_EXPORT_COMMENTS+1])
        if len(tickets)>MAX_EXPORT_TICKETS or len(comments)>MAX_EXPORT_COMMENTS:raise ApiError('export_row_limit',413)
        result={'tenant_id':str(grant.tenant_id),'tickets':[ticket_json(row) for row in tickets],
                'comments':[comment_json(row) for row in comments],
                'limitations':['Current records; not an event history or atomic multi-query snapshot.']}
        payload=(json.dumps(result,ensure_ascii=True,allow_nan=False)+'\n').encode('utf-8')
        if len(payload)>MAX_EXPORT_BYTES:raise ApiError('export_byte_limit',413)
        response=HttpResponse(payload,content_type='application/json')
        response['Content-Disposition']='attachment; filename="tenant-export.json"'
        return response
