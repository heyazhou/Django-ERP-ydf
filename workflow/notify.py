# coding=utf-8
"""流程节点到达后，把节点信息推给这个节点的办理人。"""

from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType

from workflow.models import Instance, Notice, TodoList


def node_users(node, inst, extra_ids=None):
    """节点上指定的用户、岗位、角色或提交人，加上本次额外勾选的人。"""
    found = []
    if node is None:
        if inst.starter_id:
            found.append(inst.starter)
    elif node.handler_type == 4:
        if inst.starter_id:
            found.append(inst.starter)
    elif node.handler_type == 2:
        for position in node.positions.all():
            for employee in position.employee_set.all():
                if employee.user_id:
                    found.append(employee.user)
    elif node.handler_type == 3:
        for role in node.roles.all():
            found.extend(list(role.users.all()))
    else:
        found.extend(list(node.users.all()))
    if extra_ids:
        found.extend(list(User.objects.filter(id__in=extra_ids)))
    if not found and node is not None:
        found.extend(list(node.users.all()))
    if not found and inst.starter_id:
        found.append(inst.starter)
    unique = []
    seen = set()
    for user in found:
        if user and user.id not in seen:
            seen.add(user.id)
            unique.append(user)
    return unique


def document_label(inst):
    try:
        content_type = ContentType.objects.get(app_label=inst.modal.app_name, model=inst.modal.model_name)
        obj = content_type.get_object_for_this_type(pk=inst.object_id)
        return '%s' % obj
    except Exception:
        return inst.modal.name


def deliver(inst, node, kind='arrive', extra_ids=None, create_todo=None):
    """把当前节点推给相关人。待处理的同时写入待办，结果只写推送。"""
    if create_todo is None:
        create_todo = kind == 'arrive'
    users = node_users(node, inst, extra_ids)
    if kind != 'arrive' and inst.starter_id:
        users = node_users(node, inst, extra_ids)
        if inst.starter not in users:
            users = [inst.starter] + users
    label = document_label(inst)
    node_name = node.name if node else '结束'
    if kind == 'arrive':
        title = '%s · %s' % (inst.modal.name, node_name)
        body = '请处理 %s' % label
    elif kind == 'finish':
        title = '%s 已通过' % inst.modal.name
        body = label
    elif kind == 'deny':
        title = '%s 已拒绝' % inst.modal.name
        body = label
    else:
        title = '%s 已终止' % inst.modal.name
        body = label
    for user in users:
        if create_todo and node is not None:
            if not TodoList.objects.filter(inst=inst, node=node, user=user, status=False).exists():
                TodoList.objects.create(
                    inst=inst, node=node, user=user,
                    app_name=inst.modal.app_name, model_name=inst.modal.model_name)
        if Notice.objects.filter(user=user, inst=inst, node=node, kind=kind).exists():
            continue
        Notice.objects.create(
            user=user, inst=inst, node=node, kind=kind, title=title[:80], body=body[:200])
    return users


def deliver_open():
    """把还在处理中的节点补给尚未收到推送的办理人。"""
    count = 0
    pending = Instance.objects.filter(status__in=[1, 2]).prefetch_related('current_nodes')
    for inst in pending:
        for node in inst.current_nodes.all():
            before = Notice.objects.filter(inst=inst, node=node, kind='arrive').count()
            deliver(inst, node, kind='arrive')
            count += Notice.objects.filter(inst=inst, node=node, kind='arrive').count() - before
    return count
