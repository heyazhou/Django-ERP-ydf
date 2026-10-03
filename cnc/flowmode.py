# coding=utf-8
"""Phone execution for every document: logistics, data and information."""
from django.apps import apps
from django.contrib.auth.models import User

from cnc.qrutil import ensure_token, find_by_token

PAGES = {
    'cnc_workorder': 'cnc.WorkOrder',
    'cnc_operation': 'cnc.WorkOperation',
    'cnc_machine': 'cnc.Machine',
    'cnc_maintain': 'cnc.MaintainOrder',
    'cnc_tool': 'cnc.Tool',
    'cnc_fixture': 'cnc.Fixture',
    'cnc_lot': 'cnc.MaterialLot',
    'cnc_inspection': 'cnc.Inspection',
    'cnc_program': 'cnc.NcProgram',
    'cnc_drawing': 'cnc.Drawing',
    'cnc_outsource': 'cnc.OutsourceOrder',
    'cnc_routing': 'cnc.Routing',
    'cnc_assembly': 'cnc.AssemblyOrder',
    'cnc_assembly_unit': 'cnc.AssemblyUnit',
    'cnc_board_area': 'cnc.ShopArea',
    'cnc_employee': 'basedata.Employee',
    'cnc_material': 'basedata.Material',
    'quality_check': 'quality.CheckRecord',
    'quality_standard': 'quality.Standard',
}

KIND_LABEL = {
    'move': '\u7269\u6d41',
    'data': '\u6570\u636e',
    'info': '\u4fe1\u606f',
}


def object_on_page(request):
    match = getattr(request, 'resolver_match', None)
    if match is None:
        return None
    if match.url_name in ('cnc_doc', 'cnc_open'):
        return find_by_token(match.kwargs.get('token'))
    label = PAGES.get(match.url_name)
    if not label:
        return None
    pk = match.kwargs.get('pk')
    if not pk:
        return None
    model = apps.get_model(label)
    return model.objects.filter(pk=pk).first()


def unread_count(user):
    from cnc.mine import owner_count
    if not user.is_authenticated:
        return 0
    return owner_count(user)


def mark_seen(user, obj):
    from cnc.models import Handoff
    from workflow.models import Instance, Modal, Notice, TodoList
    import datetime
    token = ensure_token(obj)
    Handoff.objects.filter(token=token, receiver=user, is_read=False).update(is_read=True)
    modal = Modal.objects.filter(
        app_name=obj._meta.app_label, model_name=obj._meta.model_name).first()
    if modal is None:
        return
    inst = Instance.objects.filter(modal=modal, object_id=obj.pk).first()
    if inst is None:
        return
    Notice.objects.filter(inst=inst, user=user, is_read=False).update(is_read=True)
    TodoList.objects.filter(inst=inst, user=user, status=False, is_read=False).update(
        is_read=True, read_time=datetime.datetime.now())


def bundle(request, obj):
    from workflow.phoneflow import describe
    token = ensure_token(obj)
    state = describe(obj, request.user)
    people = User.objects.filter(is_active=True).order_by('username')[:60]
    state.update({
        'token': token,
        'title': str(obj),
        'people': people,
    })
    return state


def inject(request):
    if not request.path.startswith('/m/'):
        return {}
    user = getattr(request, 'user', None)
    shot = {}
    try:
        shot = request.session.get('shot') or {}
    except Exception:
        shot = {}
    if user is None or not user.is_authenticated:
        return {'shot': shot}
    try:
        count = unread_count(user)
    except Exception:
        return {'shot': shot}
    obj = object_on_page(request)
    if obj is None:
        return {'flow_count': count, 'shot': shot}
    try:
        if request.method == 'GET':
            mark_seen(user, obj)
        return {'flow': bundle(request, obj), 'flow_count': unread_count(user), 'shot': shot}
    except Exception:
        return {'flow_count': count, 'shot': shot}
