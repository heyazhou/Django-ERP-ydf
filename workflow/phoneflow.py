# coding=utf-8
"""Advance a workflow from the phone without posting inventory or shop status."""
import datetime

from workflow.models import History, Instance, Modal, Node, TodoList
from workflow.notify import deliver

SKIP_STATUS = ('cnc', 'invent', 'quality')


def describe(obj, user):
    today = datetime.date.today()
    modal = Modal.objects.filter(
        app_name=obj._meta.app_label,
        model_name=obj._meta.model_name,
        end__gt=today,
    ).order_by('-end').first()
    blank = {'node': '', 'can_start': False, 'can_decide': False, 'modal_name': ''}
    if modal is None:
        return blank
    inst = Instance.objects.filter(modal=modal, object_id=obj.pk).first()
    blank['modal_name'] = modal.name
    if inst is None:
        blank['can_start'] = True
        return blank
    if inst.status in (3, 4, 99):
        current = inst.current_nodes.first()
        blank['node'] = current.name if current else '\u5df2\u7ed3\u675f'
        return blank
    todo = TodoList.objects.filter(inst=inst, user=user, status=False).select_related('node').first()
    current = inst.current_nodes.first()
    blank['node'] = current.name if current else ''
    blank['can_decide'] = todo is not None
    return blank


def apply_document_status(obj, node):
    """审批只改采购、销售等单据状态。车间、库存、质量和导入仍走各自的执行按钮。"""
    if obj._meta.app_label in SKIP_STATUS:
        return
    if obj._meta.model_name == 'dataimport':
        return
    if not node or not node.status_field or not node.status_value:
        return
    try:
        setattr(obj, node.status_field, node.status_value)
        obj.save()
    except Exception:
        return


def start_flow(request, obj):
    today = datetime.date.today()
    modal = Modal.objects.filter(
        app_name=obj._meta.app_label,
        model_name=obj._meta.model_name,
        end__gt=today,
    ).order_by('-end').first()
    if modal is None:
        return '\u8fd9\u5f20\u5355\u6ca1\u6709\u6d41\u7a0b'
    if Instance.objects.filter(modal=modal, object_id=obj.pk).exists():
        return '\u6d41\u7a0b\u5df2\u7ecf\u5728\u8fdb\u884c'
    node = modal.node_set.filter(start=1).first() or modal.node_set.order_by('id').first()
    if node is None:
        return '\u6d41\u7a0b\u6ca1\u6709\u8282\u70b9'
    inst = Instance.objects.create(modal=modal, object_id=obj.pk, starter=request.user)
    inst.current_nodes.add(node)
    History.objects.create(inst=inst, user=request.user, pro_type=0, node=node, memo='\u624b\u673a\u63d0\u4ea4')
    TodoList.objects.create(
        inst=inst, user=request.user, app_name=obj._meta.app_label, model_name=obj._meta.model_name,
        is_read=True, read_time=datetime.datetime.now(), status=True)
    deliver(inst, node, kind='arrive')
    apply_document_status(obj, node)
    return '\u5df2\u63d0\u4ea4\uff0c\u4e0b\u4e00\u73af\u8282\u4f1a\u6536\u5230\u4fe1\u606f'


def decide_flow(request, obj, operation, memo):
    if operation not in ('1', '3', '4'):
        return '\u65e0\u6cd5\u8bc6\u522b\u7684\u529e\u7406'
    today = datetime.date.today()
    modal = Modal.objects.filter(
        app_name=obj._meta.app_label,
        model_name=obj._meta.model_name,
        end__gt=today,
    ).order_by('-end').first()
    if modal is None:
        return '\u8fd9\u5f20\u5355\u6ca1\u6709\u6d41\u7a0b'
    inst = Instance.objects.filter(modal=modal, object_id=obj.pk).first()
    if inst is None:
        return '\u8bf7\u5148\u63d0\u4ea4\u6d41\u7a0b'
    todo = TodoList.objects.filter(inst=inst, user=request.user, status=False).first()
    if todo is None:
        return '\u5f53\u524d\u4e0d\u8f6e\u5230\u4f60\u529e\u7406'
    current = list(inst.current_nodes.all())
    if not current:
        return '\u6d41\u7a0b\u6ca1\u6709\u5f53\u524d\u73af\u8282'
    current_node = current[0]
    all_nodes = list(Node.objects.filter(modal=modal).order_by('-id'))
    is_stop = operation in ('3', '4')
    next_node = None
    if not is_stop:
        if current_node.stop or (all_nodes and current_node == all_nodes[0]):
            is_stop = True
        elif current_node.next.exists():
            next_node = current_node.next.first()
        else:
            try:
                position = all_nodes.index(current_node)
            except ValueError:
                position = 0
            next_node = all_nodes[position - 1] if position else None
            if next_node is None:
                is_stop = True
    memo = (memo or '')[:40]
    if is_stop:
        inst.status = 99 if operation == '1' else int(operation)
        if operation == '1' and not inst.approved_time:
            inst.approved_time = datetime.datetime.now()
        inst.current_nodes.clear()
        inst.save()
        kind = {'1': 'finish', '3': 'deny', '4': 'stop'}.get(operation, 'finish')
        deliver(inst, current_node, kind=kind, create_todo=False)
    else:
        if next_node is None:
            return '\u6d41\u7a0b\u6ca1\u6709\u4e0b\u4e00\u73af\u8282'
        inst.current_nodes.clear()
        inst.current_nodes.add(next_node)
        apply_document_status(obj, current_node)
        extra = request.POST.getlist('receiver')
        deliver(inst, next_node, kind='arrive', extra_ids=extra)
    History.objects.create(
        inst=inst, user=request.user, pro_type=int(operation), memo=memo, node=current_node)
    TodoList.objects.filter(inst=inst, node=current_node, status=False).update(status=True)
    from plugin.wfactions import WorkflowAction, WorkflowActionManager
    if current_node.action:
        action = WorkflowActionManager().actions.get(current_node.action)
        if action and isinstance(action, WorkflowAction):
            action.action(request, obj, current_node, operation)
    return '\u5df2\u529e\u7406\uff0c\u4fe1\u606f\u5df2\u4f20\u7ed9\u4e0b\u4e00\u73af\u8282'
