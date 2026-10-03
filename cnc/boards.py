AREA_SEED = (
    (10, '备料区', 'SAW', '毛坯、下料和发料'),
    (15, '编程区', 'PROG', '设计数控加工程序'),
    (18, '调机区', 'SETUP', '按数控程序对刀、补偿和试切'),
    (35, '手动加工区', 'MANUAL', '车削、铣削、线切割、电火花、手工焊接、钻孔、攻丝、打磨清洗'),
    (40, '加工中心区', 'MC', '加工中心工序'),
    (50, '外协区', 'OUT', '热处理、表面处理等厂外工序'),
    (55, '部件装配工段', 'ASSEM', '零件配装、拧紧和总成'),
    (60, '质检区', 'QC', '首件、巡检和终检'),
    (70, '成品区', 'PACK', '包装和完工入库'),
    (80, '维修保养', 'MAINT', '设备故障维修和计划保养'),
)


def area_types(area):
    return [item.strip() for item in (area.machine_types or '').split(',') if item.strip()]


def area_for_type(machine_type):
    from cnc.models import ShopArea
    for area in ShopArea.objects.order_by('seq', 'id'):
        if machine_type in area_types(area):
            return area
    return None


RETIRED_AREAS = ('车削区', '铣削区')


def ensure_shop_areas():
    from cnc.models import Machine, ShopArea
    ShopArea.objects.filter(name__in=RETIRED_AREAS).delete()
    for seq, name, types, note in AREA_SEED:
        area, created = ShopArea.objects.get_or_create(
            name=name,
            defaults={'seq': seq, 'machine_types': types, 'note': note},
        )
        if not created and not area.machine_types:
            area.machine_types = types
            area.seq = seq
            area.note = note
            area.save(update_fields=['machine_types', 'seq', 'note'])
    for machine in Machine.objects.filter(area__isnull=True):
        area = area_for_type(machine.machine_type)
        if area:
            Machine.objects.filter(pk=machine.pk).update(area=area)
    ensure_assembly_section()
    merge_into_manual()


def ensure_assembly_section():
    """补齐装配工位。没有装配工单时放一张待开工的部件总成。"""
    import datetime
    from decimal import Decimal

    from django.contrib.auth.models import User

    from basedata.models import Material, Partner
    from cnc.models import Machine, Routing, RoutingStep, WorkOrder

    if not Machine.objects.filter(machine_type='ASSEM').exists():
        Machine.objects.create(
            name='装配工位', machine_type='ASSEM', brand='装配台', hour_rate=Decimal('60'))
        area = area_for_type('ASSEM')
        if area:
            Machine.objects.filter(machine_type='ASSEM', area__isnull=True).update(area=area)
    if not WorkOrder.objects.filter(drawing_no='模拟-装配').exists():
        user = User.objects.filter(is_superuser=True).first() or User.objects.first()
        if user is None:
            return
        material = Material.objects.filter(code='模拟物料').first()
        customer = Partner.objects.filter(code='模拟客户').first()
        routing, created = Routing.objects.get_or_create(
            name='部件装配工艺',
            defaults={'material': material, 'version': 'A'},
        )
        if created or not routing.steps.exists():
            RoutingStep.objects.get_or_create(
                routing=routing, seq=10, name='部件装配',
                defaults={'machine_type': 'ASSEM', 'setup_min': Decimal('10'), 'unit_min': Decimal('15')},
            )
            RoutingStep.objects.get_or_create(
                routing=routing, seq=20, name='检验',
                defaults={'machine_type': 'QC', 'unit_min': Decimal('5')},
            )
        order = WorkOrder.objects.create(
            title='阀体部件', material=material, customer=customer, routing=routing,
            qty=Decimal('4'), due_date=datetime.date.today() + datetime.timedelta(days=3),
            drawing_no='模拟-装配', blank_spec='机加零件配装',
        )
        order.release(user)
    from cnc.assembly import ensure_demo_assembly
    ensure_demo_assembly()
    ensure_machine_work()


MANUAL_PROCESSES = (
    '车削', '铣削', '线切割', '电火花', '手工焊接', '钻孔', '攻丝', '打磨清洗',
)
MERGED_MACHINE_TYPES = ('LATHE', 'MILL', 'WIRE', 'EDM', 'DRILL')


def merge_into_manual():
    """车削、铣削、线切割、电火花、钻孔并入手动设备，并补上焊接、攻丝、打磨清洗。"""
    from decimal import Decimal

    from cnc.models import Machine, Process, RoutingStep, ShopArea, WorkOperation

    for index, name in enumerate(MANUAL_PROCESSES, start=20):
        process, created = Process.objects.get_or_create(
            name=name,
            defaults={'machine_type': 'MANUAL', 'seq': index, 'std_minutes': Decimal('10')},
        )
        if not created and process.machine_type != 'MANUAL':
            process.machine_type = 'MANUAL'
            process.save(update_fields=['machine_type'])
    RoutingStep.objects.filter(machine_type__in=MERGED_MACHINE_TYPES).update(machine_type='MANUAL')
    WorkOperation.objects.filter(machine_type__in=MERGED_MACHINE_TYPES).update(machine_type='MANUAL')
    area = ShopArea.objects.filter(name='手动加工区').first()
    note = next(item[3] for item in AREA_SEED if item[1] == '手动加工区')
    if area and area.note != note:
        area.note = note
        area.save(update_fields=['note'])
    Machine.objects.filter(machine_type__in=MERGED_MACHINE_TYPES).update(
        machine_type='MANUAL', area=area)
    if area:
        Machine.objects.filter(machine_type='MANUAL', area__isnull=True).update(area=area)


def ensure_machine_work():
    """补齐加工程序、调机、手动加工和维修保养的示例。"""
    import datetime
    from decimal import Decimal

    from django.contrib.auth.models import User
    from django.utils import timezone

    from basedata.models import Material
    from cnc.models import (
        Machine, MaintainOrder, NcProgram, Process, Routing, RoutingStep, WorkOrder,
    )

    for name, machine_type, seq in (
        ('加工程序', 'PROG', 4),
        ('调机', 'SETUP', 5),
        ('手动加工', 'MANUAL', 8),
    ):
        Process.objects.get_or_create(
            name=name,
            defaults={'machine_type': machine_type, 'seq': seq, 'std_minutes': Decimal('20')},
        )
    if not Machine.objects.filter(machine_type='MANUAL').exists():
        Machine.objects.create(name='手动铣床', machine_type='MANUAL', brand='X5032手动', hour_rate=Decimal('50'))
    area = area_for_type('MANUAL')
    if area:
        Machine.objects.filter(machine_type='MANUAL', area__isnull=True).update(area=area)
    user = User.objects.filter(is_superuser=True).first() or User.objects.first()
    mill = Machine.objects.filter(name__contains='铣床').exclude(name__contains='手动').order_by('id').first()
    if mill is None:
        mill = Machine.objects.filter(machine_type='MILL').first()
    if mill and not MaintainOrder.objects.filter(note='模拟-保养').exists():
        MaintainOrder.objects.create(
            machine=mill, kind='maintain', title='主轴定期保养',
            symptom='按周期检查主轴和润滑', status='doing',
            plan_date=datetime.date.today(), technician=user,
            started_at=timezone.now(), note='模拟-保养',
        )
    center = Machine.objects.filter(machine_type='MC').first()
    if center and not MaintainOrder.objects.filter(note='模拟-维修').exists():
        MaintainOrder.objects.create(
            machine=center, kind='repair', title='刀库卡顿',
            symptom='换刀时偶发卡滞', status='open',
            plan_date=datetime.date.today(), note='模拟-维修',
        )
    material = Material.objects.filter(code='模拟物料').first()
    program = NcProgram.objects.order_by('id').first()
    if user and material and not WorkOrder.objects.filter(drawing_no='模拟-程序').exists():
        routing, created = Routing.objects.get_or_create(
            name='程序调机工艺', defaults={'material': material, 'version': 'A'})
        if created or not routing.steps.exists():
            RoutingStep.objects.get_or_create(
                routing=routing, seq=10, name='加工程序',
                defaults={'machine_type': 'PROG', 'unit_min': Decimal('30')})
            RoutingStep.objects.get_or_create(
                routing=routing, seq=20, name='调机',
                defaults={'machine_type': 'SETUP', 'setup_min': Decimal('20'), 'unit_min': Decimal('5')})
            RoutingStep.objects.get_or_create(
                routing=routing, seq=30, name='加工中心',
                defaults={'machine_type': 'MC', 'unit_min': Decimal('12')})
        order = WorkOrder.objects.create(
            title='法兰程序与调机', material=material, routing=routing, qty=Decimal('2'),
            due_date=datetime.date.today() + datetime.timedelta(days=2),
            drawing_no='模拟-程序', blank_spec='先编程再调机',
        )
        order.release(user)
        first = order.operations.order_by('seq').first()
        if program and first:
            first.program = program
            first.save()
    manual = Machine.objects.filter(machine_type='MANUAL').first()
    if user and material and manual and not WorkOrder.objects.filter(drawing_no='模拟-手动').exists():
        routing, created = Routing.objects.get_or_create(
            name='手动铣工艺', defaults={'material': material, 'version': 'A'})
        if created or not routing.steps.exists():
            RoutingStep.objects.get_or_create(
                routing=routing, seq=10, name='手动加工',
                defaults={'machine_type': 'MANUAL', 'setup_min': Decimal('15'), 'unit_min': Decimal('10')})
        order = WorkOrder.objects.create(
            title='法兰手动铣外形', material=material, routing=routing, qty=Decimal('2'),
            due_date=datetime.date.today() + datetime.timedelta(days=2),
            drawing_no='模拟-手动', blank_spec='手动铣床',
        )
        order.release(user)
        step = order.operations.order_by('seq').first()
        if step:
            step.machine = manual
            step.save()


def board_snapshot(area):
    from cnc.models import AssemblyOrder, Machine, MaintainOrder, MaterialLot, WorkOperation, WorkOrder
    types = area_types(area)
    assembly_lanes = []
    if 'ASSEM' in types:
        orders = AssemblyOrder.objects.exclude(status__in=['draft', 'cancelled']).select_related('station', 'customer')
        assembly_lanes = [
            ('ready', '待配料', list(orders.filter(status='kitting').order_by('due_date', 'id'))),
            ('running', '装配中', list(orders.filter(status='assembling').order_by('due_date', 'id'))),
            ('out', '待检', list(orders.filter(status='qc').order_by('due_date', 'id'))),
            ('done', '装配完工', list(orders.filter(status='done').order_by('-finished_at', '-id')[:8])),
        ]
    maintain_lanes = []
    if 'MAINT' in types:
        sheets = MaintainOrder.objects.exclude(status='cancelled').select_related('machine', 'technician')
        maintain_lanes = [
            ('ready', '待处理', list(sheets.filter(status='open').order_by('plan_date', 'id'))),
            ('running', '进行中', list(sheets.filter(status='doing').order_by('started_at', 'id'))),
            ('done', '已完成', list(sheets.filter(status='done').order_by('-finished_at', '-id')[:8])),
        ]
    op_types = [item for item in types if item != 'MAINT']
    lanes = []
    if op_types:
        operations = WorkOperation.objects.filter(machine_type__in=op_types).exclude(
            work_order__status__in=['draft', 'cancelled', 'closed'],
        ).select_related('work_order', 'work_order__customer', 'machine', 'operator')
        lanes = [
            ('coming', '即将到达', list(operations.filter(status='wait').order_by('work_order__due_date', 'seq', 'id')[:12])),
            ('ready', '待开工', list(operations.filter(status='ready').order_by('work_order__due_date', 'seq', 'id'))),
            ('running', '加工中', list(operations.filter(status='running').order_by('started_at', 'id'))),
        ]
        if 'OUT' in op_types or operations.filter(status='out').exists():
            lanes.append(('out', '外协中', list(operations.filter(status='out').order_by('seq', 'id'))))
        lanes.append(('done', '本区完工', list(operations.filter(status='done').order_by('-finished_at', '-id')[:8])))
    lots = []
    if 'SAW' in types:
        lots = list(MaterialLot.objects.exclude(status='done').select_related('material', 'work_order')[:12])
    finished = []
    if 'PACK' in types:
        finished = list(WorkOrder.objects.filter(status='done').select_related('customer')[:8])
    return {
        'area': area,
        'lanes': lanes,
        'lots': lots,
        'finished': finished,
        'machines': list(Machine.objects.filter(area=area)),
        'assembly_lanes': assembly_lanes,
        'maintain_lanes': maintain_lanes,
        'ready_count': (
            (len(lanes[1][2]) if len(lanes) > 1 else 0)
            + (len(assembly_lanes[0][2]) if assembly_lanes else 0)
            + (len(maintain_lanes[0][2]) if maintain_lanes else 0)
        ),
        'running_count': (
            (len(lanes[2][2]) if len(lanes) > 2 else 0)
            + (len(assembly_lanes[1][2]) if assembly_lanes else 0)
            + (len(maintain_lanes[1][2]) if maintain_lanes else 0)
        ),
    }
