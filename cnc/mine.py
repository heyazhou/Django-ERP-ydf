# coding=utf-8
"""Information the phone may show for its owner."""
from django.db.models import Q


def employee_for(user):
    from basedata.models import Employee
    if not getattr(user, 'is_authenticated', False):
        return None
    return Employee.objects.filter(user=user).first()


def concerns(obj, user):
    """The document names this person as operator, technician, assembler or inspector."""
    if obj is None or user is None:
        return False
    for name in ('operator_id', 'technician_id', 'assembler_id', 'inspector_id'):
        if getattr(obj, name, None) == user.id:
            return True
    meta = getattr(obj, '_meta', None)
    if meta is not None and meta.label_lower == 'basedata.employee':
        return getattr(obj, 'user_id', None) == user.id
    operations = getattr(obj, 'operations', None)
    if operations is not None:
        try:
            if operations.filter(operator_id=user.id).exists():
                return True
        except Exception:
            pass
    units = getattr(obj, 'units', None)
    if units is not None:
        try:
            if units.filter(assembler_id=user.id).exists():
                return True
        except Exception:
            pass
    return False


def _document(app_name, model_name, object_id):
    from django.apps import apps
    try:
        model = apps.get_model(app_name, model_name)
    except Exception:
        return None
    if model is None:
        return None
    return model.objects.filter(pk=object_id).first()


def personal_notices(user, limit=8):
    from workflow.models import Notice
    found = []
    rows = Notice.objects.filter(user=user, is_read=False).select_related('inst', 'inst__modal')[:80]
    for note in rows:
        modal = note.inst.modal
        obj = _document(modal.app_name, modal.model_name, note.inst.object_id)
        if concerns(obj, user):
            found.append(note)
        if len(found) >= limit:
            break
    return found


def owner_feed(user):
    from cnc.assembly import AssemblyUnit
    from cnc.models import Handoff, MaintainOrder, WorkOperation
    jobs = list(WorkOperation.objects.filter(
        operator=user, status__in=['ready', 'running']
    ).select_related('work_order')[:8])
    fixes = list(MaintainOrder.objects.filter(
        technician=user).exclude(status__in=['done', 'cancelled']).select_related('machine')[:8])
    units = list(AssemblyUnit.objects.filter(
        assembler=user).exclude(status__in=['pass', 'fail']).select_related('order')[:8])
    hands = list(Handoff.objects.filter(receiver=user, is_read=False).select_related('sender')[:8])
    notes = personal_notices(user)
    return {
        'jobs': jobs,
        'fixes': fixes,
        'units': units,
        'hands': hands,
        'notices': notes,
        'empty': not (jobs or fixes or units or hands or notes),
    }


def owner_count(user):
    feed = owner_feed(user)
    return len(feed['jobs']) + len(feed['fixes']) + len(feed['units']) + len(feed['hands']) + len(feed['notices'])


def order_ids(user):
    from cnc.models import WorkOperation
    return WorkOperation.objects.filter(operator=user).values_list('work_order_id', flat=True)


def owned_moves(user):
    from cnc.models import Handoff, MaterialLot, OutsourceOrder, ShopEvent
    orders = order_ids(user)
    return {
        'hands': Handoff.objects.filter(kind='move').filter(Q(sender=user) | Q(receiver=user)).select_related('sender', 'receiver')[:40],
        'events': ShopEvent.objects.filter(user=user).select_related('user')[:30],
        'lots': MaterialLot.objects.filter(status__in=['issued', 'wip'], work_order_id__in=orders).select_related('material', 'work_order')[:20],
        'outside': OutsourceOrder.objects.filter(status='sent', work_order_id__in=orders).select_related('work_order', 'vendor')[:20],
    }
