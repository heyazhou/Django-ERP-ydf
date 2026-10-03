import datetime
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

from basedata.models import Material, Partner
from cnc.models import (
    Drawing, Fixture, Inspection, Machine, MaintainOrder, MaterialLot, NcProgram, OutsourceOrder,
    Routing, RoutingStep, Tool, WorkOrder,
)


MARK = '模拟'


class Command(BaseCommand):
    help = '写入一套可重复执行的 CNC 生产模拟数据'

    def handle(self, *args, **options):
        WorkOrder.objects.filter(drawing_no__startswith=MARK).delete()
        Drawing.objects.filter(drawing_no__startswith=MARK).delete()
        NcProgram.objects.filter(name__startswith=MARK).delete()
        MaterialLot.objects.filter(heat_no__startswith=MARK).delete()
        OutsourceOrder.objects.filter(note__startswith=MARK).delete()
        Routing.objects.filter(name__startswith=MARK).delete()
        MaintainOrder.objects.filter(machine__name__startswith=MARK).delete()
        MaintainOrder.objects.filter(note__startswith=MARK).delete()
        Machine.objects.filter(name__startswith=MARK).delete()
        Tool.objects.filter(name__startswith=MARK).delete()
        Fixture.objects.filter(name__startswith=MARK).delete()

        user = User.objects.filter(is_superuser=True).first() or User.objects.first()
        customer, _created = Partner.objects.get_or_create(
            code='模拟客户',
            defaults={'name': '模拟机加客户', 'partner_type': 'C'},
        )
        vendor, _created = Partner.objects.get_or_create(
            code='模拟外协',
            defaults={'name': '模拟热处理厂', 'partner_type': 'S'},
        )
        material, _created = Material.objects.get_or_create(
            code='模拟物料',
            defaults={'name': '法兰盘', 'spec': '45# φ80×20', 'can_sale': True},
        )
        lathe = Machine.objects.create(
            name='%s车床' % MARK, machine_type='MANUAL', brand='国产', hour_rate=Decimal('80'))
        center = Machine.objects.create(
            name='%s加工中心' % MARK, machine_type='MC', brand='国产', hour_rate=Decimal('120'))
        Machine.objects.create(
            name='%s铣床' % MARK, machine_type='MANUAL', brand='国产', status='maintain', hour_rate=Decimal('70'))
        Tool.objects.create(
            name='%s面铣刀' % MARK, spec='直径80', life_minutes=100, used_minutes=86, status='using', machine=center)
        Tool.objects.create(
            name='%s外圆刀' % MARK, spec='刀片', life_minutes=200, used_minutes=30, machine=lathe, status='using')
        Fixture.objects.create(name='%s三爪卡盘' % MARK, spec='卡盘', status='using')
        from cnc.boards import ensure_shop_areas
        ensure_shop_areas()

        routing = Routing.objects.create(name='%s法兰工艺' % MARK, material=material, version='A')
        RoutingStep.objects.create(routing=routing, seq=10, name='车削', machine_type='MANUAL', setup_min=20, unit_min=8)
        RoutingStep.objects.create(routing=routing, seq=20, name='加工中心', machine_type='MC', setup_min=30, unit_min=12)
        RoutingStep.objects.create(
            routing=routing, seq=30, name='热处理', machine_type='OUT', outsource=True, unit_min=0)
        RoutingStep.objects.create(routing=routing, seq=40, name='检验', machine_type='QC', unit_min=3)

        today = datetime.date.today()
        running = self._order(user, material, customer, routing, '法兰-在制', 5, today + datetime.timedelta(days=2))
        self._order(user, material, customer, routing, '轴套-待开工', 10, today + datetime.timedelta(days=1))
        late = self._order(user, material, customer, routing, '端盖-延期', 4, today - datetime.timedelta(days=2))
        finished = self._order(user, material, customer, routing, '法兰-完工', 3, today)

        self._start_report(running, user, lathe, Decimal('2'), Decimal('0'), Decimal('40'))
        Inspection.objects.create(
            work_order=running, operation=running.operations.order_by('seq').first(),
            kind='first', result='pass', check_qty=1, inspector=user, note='首件尺寸合格')
        MaterialLot.objects.create(
            material=material, work_order=running, heat_no='模拟批次',
            qty=5, status='issued')
        Drawing.objects.create(
            name='法兰盘零件图', drawing_no='模拟图号', material=material, work_order=running)
        NcProgram.objects.create(
            name='%s法兰铣程序' % MARK, material=material, operation_name='加工中心', version='A')

        late_op = late.operations.order_by('seq').first()
        late_op.start(user, lathe)
        late_op.report(user, Decimal('1'), Decimal('1'), 'size', Decimal('25'), '一件超差')

        self._finish_order(finished, user, lathe, center, vendor)

        self.stdout.write('模拟生产数据已写入，图号前缀 %s' % MARK)

    def _order(self, user, material, customer, routing, title, qty, due):
        order = WorkOrder.objects.create(
            title=title, material=material, customer=customer, routing=routing,
            qty=qty, due_date=due, drawing_no='%s-%s' % (MARK, title), blank_spec='45#圆钢')
        order.release(user)
        return order

    def _start_report(self, order, user, machine, good, scrap, minutes):
        operation = order.operations.order_by('seq').first()
        operation.start(user, machine)
        operation.report(user, good, scrap, '', minutes, MARK)

    def _finish_order(self, order, user, lathe, center, vendor):
        ops = list(order.operations.order_by('seq', 'id'))
        machines = {'MANUAL': lathe, 'MC': center}
        for operation in ops:
            operation.refresh_from_db()
            if operation.outsource:
                sheet = OutsourceOrder.objects.create(
                    work_order=order, operation=operation, vendor=vendor,
                    qty=order.qty, note=MARK)
                sheet.send_out(user)
                sheet.receive(user)
                operation.refresh_from_db()
            if operation.machine_type == 'QC' and not Inspection.objects.filter(
                    operation=operation, result__in=('pass', 'concession')).exists():
                Inspection.objects.create(
                    work_order=order, operation=operation, kind='final', result='pass',
                    check_qty=order.qty, inspector=user, note='终检合格')
            if operation.status == 'ready':
                operation.start(user, machines.get(operation.machine_type))
            operation.refresh_from_db()
            if operation.status == 'running':
                operation.report(user, order.qty, Decimal('0'), '', Decimal('15'), MARK)
            operation.refresh_from_db()
            if operation.status != 'done':
                operation.finish(user)
        order.refresh_from_db()
        if order.status != 'done':
            order.status = 'done'
            order.finished_at = timezone.now()
            order.save(update_fields=['status', 'finished_at', 'modification'])
