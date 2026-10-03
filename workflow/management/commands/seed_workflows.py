# coding=utf-8
import datetime

from django.apps import apps
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.utils import timezone

from workflow.models import History, Instance, Modal, Node, TodoList


# 库存、导入和车间单据的“已执行”要走各自的过账按钮，审批节点不改这些状态。
WORKFLOWS = (
    {
        'app': 'purchase', 'model': 'purchaseorder', 'name': '采购订单审批',
        'description': '主管审核后进入在处理，批准后为已批准。入库仍由入库单过账，过账后采购单才会变成已入库。',
        'status': 'status',
        'steps': (
            ('N01', '主管审核', '01'),
            ('N02', '批准', '09'),
            ('N03', '归档', None),
        ),
        'place': {'00': 'N01', '0': 'N01', '01': 'N02', '09': 'done', '99': 'done', '04': 'drop'},
    },
    {
        'app': 'purchase', 'model': 'invoice', 'name': '采购发票确认',
        'description': '发票登记后由财务确认。确认不改发票金额。',
        'steps': (('N01', '财务审核', None), ('N02', '确认', None), ('N03', '归档', None)),
        'default': 'done',
    },
    {
        'app': 'purchase', 'model': 'payment', 'name': '采购付款确认',
        'description': '付款登记后由财务确认。',
        'steps': (('N01', '财务审核', None), ('N02', '确认', None), ('N03', '归档', None)),
        'default': 'done',
    },
    {
        'app': 'sale', 'model': 'saleorder', 'name': '销售订单审批',
        'description': '业务提交后主管审核，批准后为已批准。出库仍由领料单过账。',
        'status': 'status',
        'steps': (('N01', '主管审核', '1'), ('N02', '批准', '9'), ('N03', '归档', None)),
        'place': {'0': 'N01', '1': 'N02', '9': 'done', '99': 'done', '4': 'drop'},
    },
    {
        'app': 'sale', 'model': 'offersheet', 'name': '报价单审批',
        'description': '报价提交后由主管批准。批准不直接改报价单的执行标记。',
        'steps': (('N01', '主管审核', None), ('N02', '批准', None), ('N03', '归档', None)),
        'boolean': True,
    },
    {
        'app': 'sale', 'model': 'paymentcollection', 'name': '销售回款确认',
        'description': '回款登记后由财务确认。',
        'steps': (('N01', '财务审核', None), ('N02', '确认', None), ('N03', '归档', None)),
        'default': 'done',
    },
    {
        'app': 'invent', 'model': 'initialinventory', 'name': '期初库存审批',
        'description': '仓管提交，主管批准。批准后仍要点执行，才会写入实时库存。',
        'steps': (('N01', '主管审核', None), ('N02', '批准', None), ('N03', '归档', None)),
        'status': 'status',
        'place': {'0': 'N01', '9': 'done'},
    },
    {
        'app': 'invent', 'model': 'stockin', 'name': '入库审批',
        'description': '入库单先审批，再点执行入库过账。审批不会把单据改成已执行。',
        'steps': (('N01', '仓管审核', None), ('N02', '批准', None), ('N03', '归档', None)),
        'status': 'status',
        'place': {'0': 'N01', '1': 'N02', '9': 'done'},
    },
    {
        'app': 'invent', 'model': 'stockout', 'name': '领料审批',
        'description': '领料单先审批，再点执行出库。审批不会把单据改成已执行。',
        'steps': (('N01', '仓管审核', None), ('N02', '批准', None), ('N03', '归档', None)),
        'status': 'status',
        'place': {'0': 'N01', '1': 'N02', '9': 'done'},
    },
    {
        'app': 'invent', 'model': 'warereturn', 'name': '返库审批',
        'description': '返库单先审批，再点执行返库。',
        'steps': (('N01', '仓管审核', None), ('N02', '批准', None), ('N03', '归档', None)),
        'status': 'status',
        'place': {'0': 'N01', '1': 'N02', '9': 'done'},
    },
    {
        'app': 'invent', 'model': 'wareadjust', 'name': '库存调整审批',
        'description': '调整单先审批，再点执行调整。',
        'steps': (('N01', '主管审核', None), ('N02', '批准', None), ('N03', '归档', None)),
        'status': 'status',
        'place': {'0': 'N01', '1': 'N02', '9': 'done'},
    },
    {
        'app': 'selfhelp', 'model': 'workorder', 'name': '服务工单处理',
        'description': '提交后进入处理，批准后进入调度。关闭仍在工单上操作。',
        'status': 'status',
        'steps': (('N01', '受理', 'PROC'), ('N02', '调度', 'SCHE'), ('N03', '归档', None)),
        'place': {'NEW': 'N01', 'PROC': 'N02', 'SCHE': 'N02', 'CLOSE': 'done'},
    },
    {
        'app': 'selfhelp', 'model': 'loan', 'name': '借款审批',
        'description': '主管审核后为在处理，批准后为已批准。付款仍用借款单上的支付。',
        'status': 'status',
        'steps': (('N01', '主管审核', 'I'), ('N02', '批准', 'A'), ('N03', '归档', None)),
        'place': {'N': 'N01', 'I': 'N02', 'A': 'done', 'P': 'done'},
    },
    {
        'app': 'selfhelp', 'model': 'reimbursement', 'name': '费用报销审批',
        'description': '主管审核后为在处理，批准后为已批准。付款仍用报销单上的支付。',
        'status': 'status',
        'steps': (('N01', '主管审核', 'I'), ('N02', '批准', 'A'), ('N03', '归档', None)),
        'place': {'N': 'N01', 'I': 'N02', 'A': 'done', 'P': 'done'},
    },
    {
        'app': 'selfhelp', 'model': 'activity', 'name': '活动发布审批',
        'description': '活动提交后由主管批准再发布。批准不直接改发布标记。',
        'steps': (('N01', '主管审核', None), ('N02', '批准', None), ('N03', '归档', None)),
        'boolean': True,
    },
    {
        'app': 'hr', 'model': 'entry', 'name': '入职审批',
        'description': '入职申请由主管批准。已有入职单按已审批补记。',
        'steps': (('N01', '主管审核', None), ('N02', '批准', None), ('N03', '归档', None)),
        'default': 'done',
    },
    {
        'app': 'basedata', 'model': 'dataimport', 'name': '数据导入审批',
        'description': '导入任务先审批，再点执行导入。审批不会把任务改成已执行。',
        'steps': (('N01', '主管审核', None), ('N02', '批准', None), ('N03', '归档', None)),
        'status': 'status',
        'place': {'0': 'N01', '1': 'done'},
    },
    {
        'app': 'cnc', 'model': 'workorder', 'name': '生产工单审批',
        'description': '草稿提交审批。已下达和在制的工单按已审批补记，审批不改车间状态，下达和报工仍走车间页面。',
        'steps': (('N01', '计划审核', None), ('N02', '批准下达', None), ('N03', '归档', None)),
        'status': 'status',
        'place': {
            'draft': 'N01', 'released': 'done', 'running': 'done',
            'done': 'done', 'closed': 'done', 'cancelled': 'drop',
        },
    },
    {
        'app': 'cnc', 'model': 'outsourceorder', 'name': '外协审批',
        'description': '外协发出前先审批。已回厂的外协单按已审批补记，不改外协状态。',
        'steps': (('N01', '计划审核', None), ('N02', '批准', None), ('N03', '归档', None)),
        'status': 'status',
        'place': {'draft': 'N01', 'sent': 'N02', 'back': 'done', 'closed': 'done'},
    },
    {
        'app': 'cnc', 'model': 'maintainorder', 'name': '维修保养审批',
        'description': '维修保养单提交后由主管批准。批准不改设备状态，开工和完工仍在维修单上操作。',
        'steps': (('N01', '主管审核', None), ('N02', '批准', None), ('N03', '归档', None)),
        'status': 'status',
        'place': {'open': 'N01', 'doing': 'N02', 'done': 'done', 'cancelled': 'drop'},
    },
    {
        'app': 'cnc', 'model': 'assemblyorder', 'name': '部件装配审批',
        'description': '装配工单下达前先审批。已展开的装配单按审批中补记，不改装配进度。',
        'steps': (('N01', '计划审核', None), ('N02', '批准', None), ('N03', '归档', None)),
        'status': 'status',
        'place': {
            'draft': 'N01', 'kitting': 'N02', 'assembling': 'N02', 'qc': 'N02',
            'done': 'done', 'cancelled': 'drop',
        },
    },
    {
        'app': 'basedata', 'model': 'project', 'name': '项目审批流程',
        'description': '项目从跟踪、合同、交付到关闭。沿用原有节点，补上办理人、起始和结束。',
        'keep_nodes': True,
        'status': 'status',
        'place': {'00': 'N01', '01': 'N01', '02': 'N02', '03': 'N03', '04': 'done', '99': 'done'},
    },
    {
        'app': 'basedata', 'model': 'employee', 'name': '新员工入职流程',
        'description': '新员工由薪酬、合同岗位办理。已在册人员按已审批补记。',
        'keep_nodes': True,
        'status': 'status',
        'place': {'10': 'done', '11': 'done'},
        'fallback': 'done',
    },
)


class Command(BaseCommand):
    help = '补齐工作流模型，并按单据现状建立实例'

    def handle(self, *args, **options):
        approvers = list(User.objects.filter(username__in=['admin', 'chengcai'], is_active=True))
        actor = User.objects.filter(username='admin').first() or User.objects.filter(is_superuser=True).first()
        if actor is None:
            self.stdout.write('没有可用的审批人')
            return
        if not approvers:
            approvers = [actor]
        created_models = 0
        created_instances = 0
        for spec in WORKFLOWS:
            modal, made = self.ensure_modal(spec)
            if made:
                created_models += 1
            if spec.get('keep_nodes'):
                self.repair_existing(modal, approvers)
            else:
                self.ensure_steps(modal, spec, approvers)
            created_instances += self.backfill(modal, spec, actor)
        from workflow.notify import deliver_open
        pushed = deliver_open()
        self.stdout.write('models+%s instances+%s pushed+%s modals=%s instances=%s' % (
            created_models, created_instances, pushed, Modal.objects.count(), Instance.objects.count()))

    def ensure_modal(self, spec):
        content_type = ContentType.objects.get(app_label=spec['app'], model=spec['model'])
        modal = Modal.objects.filter(app_name=spec['app'], model_name=spec['model']).first()
        made = False
        if modal is None:
            modal = Modal.objects.create(
                name=spec['name'],
                description=spec['description'],
                content_type=content_type,
                app_name=spec['app'],
                model_name=spec['model'],
                begin=datetime.date.today(),
                end=datetime.date(9999, 12, 31),
            )
            modal.code = 'WF%03d' % modal.id
            modal.save(update_fields=['code'])
            made = True
        elif not spec.get('keep_nodes'):
            modal.name = spec['name']
            modal.description = spec['description']
            modal.content_type = content_type
            modal.save(update_fields=['name', 'description', 'content_type'])
        return modal, made

    def ensure_steps(self, modal, spec, approvers):
        if modal.node_set.exists():
            self.rewire(modal, approvers)
            return
        nodes = []
        steps = spec['steps']
        for index, (code, name, status_value) in enumerate(steps):
            last = index == len(steps) - 1
            first = index == 0
            node = Node.objects.create(
                modal=modal,
                code=code,
                name=name,
                start=first,
                stop=last,
                can_deny=not last,
                can_terminate=not last,
                can_edit=first,
                approve_node=(index == 1),
                email_notice=False,
                handler_type=4 if last else 1,
                status_field='status' if status_value else None,
                status_value=status_value,
            )
            if not last:
                node.users.set(approvers)
            nodes.append(node)
        for previous, nxt in zip(nodes, nodes[1:]):
            previous.next.add(nxt)

    def rewire(self, modal, approvers):
        """已有节点时补上批准和归档，保证同意后能写到批准状态。"""
        nodes = list(modal.node_set.order_by('id'))
        if len(nodes) >= 3 and any(item.stop for item in nodes):
            return
        if len(nodes) < 2:
            return
        first, second = nodes[0], nodes[1]
        if first.name in ('提交', ''):
            first.name = '主管审核'
        if second.name in ('结束', ''):
            second.name = '批准'
        first.start = True
        first.handler_type = 1
        first.can_deny = True
        first.save()
        first.users.add(*approvers)
        second.stop = False
        second.approve_node = True
        second.can_deny = True
        second.can_terminate = True
        second.handler_type = 1
        if second.status_field is None and first.status_field:
            second.status_field = first.status_field
        if not second.status_value and first.status_value == '01':
            second.status_value = '09'
        second.save()
        second.users.add(*approvers)
        end = modal.node_set.filter(code='N03').first()
        if end is None:
            end = Node.objects.create(
                modal=modal, code='N03', name='归档', stop=True,
                can_deny=False, can_terminate=False, handler_type=4, email_notice=False,
            )
        first.next.add(second)
        second.next.add(end)

    def repair_existing(self, modal, approvers):
        nodes = list(modal.node_set.order_by('id'))
        if not nodes:
            return
        nodes[0].start = True
        nodes[0].handler_type = 1
        nodes[0].save()
        nodes[0].users.add(*approvers)
        for previous, nxt in zip(nodes, nodes[1:]):
            previous.next.add(nxt)
        last = nodes[-1]
        last.stop = True
        if last.handler_type != 1 or not last.users.exists():
            last.handler_type = 1
            last.save()
            last.users.add(*approvers)
        else:
            last.save()

    def backfill(self, modal, spec, actor):
        model = apps.get_model(spec['app'], spec['model'])
        nodes = {item.code: item for item in modal.node_set.all()}
        added = 0
        for obj in model.objects.all().order_by('id'):
            if Instance.objects.filter(modal=modal, object_id=obj.pk).exists():
                continue
            target = self.target_of(obj, spec)
            starter = self.starter_of(obj, actor)
            inst = Instance.objects.create(modal=modal, object_id=obj.pk, starter=starter, status=2)
            self.remember(inst, starter, spec['app'], spec['model'], target, nodes)
            added += 1
        return added

    def target_of(self, obj, spec):
        if spec.get('boolean'):
            return 'done' if getattr(obj, 'status', False) else 'N01'
        if 'place' not in spec:
            return spec.get('default', 'done')
        value = getattr(obj, spec.get('status') or 'status', None)
        text = '' if value is None else str(value)
        return spec['place'].get(text, spec.get('fallback', 'N01'))

    def starter_of(self, obj, actor):
        user = getattr(obj, 'user', None)
        if isinstance(user, User):
            return user
        creator = getattr(obj, 'creator', None)
        if creator:
            found = User.objects.filter(username=creator).first()
            if found:
                return found
        return actor

    def remember(self, inst, starter, app, model, target, nodes):
        History.objects.create(inst=inst, user=starter, pro_type=0, memo='按单据现状补记')
        TodoList.objects.create(
            inst=inst, user=starter, app_name=app, model_name=model,
            is_read=True, read_time=timezone.now(), status=True)
        if target == 'drop':
            inst.status = 4
            inst.save(update_fields=['status'])
            History.objects.create(inst=inst, user=starter, pro_type=4, memo='单据已作废')
            return
        if target == 'done' or target not in nodes:
            inst.status = 99
            inst.approved_time = timezone.now()
            inst.save(update_fields=['status', 'approved_time'])
            History.objects.create(inst=inst, user=starter, pro_type=1, memo='单据已审批')
            return
        node = nodes[target]
        if target != 'N01' and 'N01' in nodes:
            History.objects.create(inst=inst, user=starter, node=nodes['N01'], pro_type=1, memo='前序已通过')
        inst.current_nodes.add(node)
        TodoList.objects.create(
            inst=inst, node=node, user=self.approver(), app_name=app, model_name=model)
        inst.status = 2
        inst.save(update_fields=['status'])

    def approver(self):
        return User.objects.filter(username='admin').first() or User.objects.filter(is_superuser=True).first()
