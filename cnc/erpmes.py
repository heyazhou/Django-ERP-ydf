# coding=utf-8
"""销售、仓库和车间工单的闭环。审批不改车间状态，库存仍由入库单和领料单过账。"""
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from basedata.models import Measure, Warehouse
from cnc.models import JobLog, MaterialLot, Routing, WorkMaterial, WorkOrder
from cnc.qrutil import log_event


def orders_from_sale(sale, user):
    """按销售订单生成车间工单和装配任务。已有的不重复建。"""
    from cnc.assembly import AssemblyBom, AssemblyOrder

    made = []
    for item in sale.saleitem_set.select_related('material').all():
        material = item.material
        if material is None:
            continue
        qty = item.cnt or Decimal('0')
        if qty <= 0:
            continue
        order, created = _work_order(sale, material, qty, user)
        if created:
            made.append(order)
        bom = AssemblyBom.objects.filter(product=material, is_active=True).order_by('-id').first()
        if bom is None:
            expand_materials(order) if order else None
            continue
        assembly = _assembly_order(sale, item, bom, qty)
        if assembly is not None:
            made.append(assembly)
        for line in bom.lines.select_related('material').all():
            part_qty = (line.qty or Decimal('0')) * qty
            if part_qty <= 0 or line.material_id == material.id:
                continue
            child, child_new = _work_order(sale, line.material, part_qty, user)
            if child_new:
                made.append(child)
            if child:
                expand_materials(child)
        if order:
            expand_materials(order)
    if not made:
        raise ValueError('这张销售订单没有新的生产任务。物料要有工艺路线，或者已经生成过工单。')
    return made


def _work_order(sale, material, qty, user):
    routing = Routing.objects.filter(material=material, is_active=True).order_by('-id').first()
    if routing is None:
        return None, False
    found = WorkOrder.objects.filter(sale_order=sale, material=material).exclude(status='cancelled').first()
    if found:
        return found, False
    order = WorkOrder.objects.create(
        title=(material.name or '')[:80],
        material=material,
        customer=sale.partner,
        sale_order=sale,
        routing=routing,
        qty=qty,
        due_date=sale.deliver_date,
        drawing_no=(material.code or '')[:40],
        blank_spec=(material.spec or '')[:80],
        creator=(getattr(user, 'username', '') or '')[:20],
    )
    log_event(order.qr_token, 'plan', '销售订单生成工单 %s' % (sale.code or sale.pk), user)
    return order, True


def _assembly_order(sale, item, bom, qty):
    from cnc.assembly import AssemblyOrder

    mark = '销售%s' % (sale.code or sale.pk)
    if AssemblyOrder.objects.filter(product=item.material, note__contains=mark).exclude(status='cancelled').exists():
        return None
    sets = int(qty)
    if sets < 1:
        sets = 1
    return AssemblyOrder.objects.create(
        title=(item.material.name or '装配')[:80],
        bom=bom,
        product=item.material,
        customer=sale.partner,
        qty=sets,
        due_date=sale.deliver_date,
        note=mark,
    )


def expand_materials(order):
    """用物料的装配清单展开工单用料。"""
    from cnc.assembly import AssemblyBom

    if not order or not order.material_id:
        return 0
    bom = AssemblyBom.objects.filter(product=order.material, is_active=True).order_by('-id').first()
    if bom is None:
        return 0
    count = 0
    for line in bom.lines.all():
        need = (line.qty or Decimal('0')) * (order.qty or Decimal('0'))
        row, created = WorkMaterial.objects.get_or_create(
            work_order=order, material=line.material,
            defaults={'need_qty': need, 'note': (line.note or '')[:120]},
        )
        if not created and not row.issued_qty:
            row.need_qty = need
            row.save(update_fields=['need_qty'])
        count += 1
    return count


def issue_materials(order, user):
    """按库存生成领料单并过账。库存不够时只领现有数量。"""
    from invent.models import Inventory, OutItem, StockOut

    lines = list(order.materials.select_related('material'))
    if not lines:
        raise ValueError('请先按清单展开用料，或手工添加工单用料')
    pending = [(line, line.left_qty()) for line in lines if line.left_qty() > 0]
    if not pending:
        raise ValueError('用料已经领完')
    with transaction.atomic():
        sheet = StockOut.objects.create(
            title=('领料%s' % (order.code or order.pk))[:40],
            description='生产工单 %s' % (order.code or order.pk),
            user=user if getattr(user, 'is_authenticated', False) else None,
        )
        taken = {}
        reserved = {}
        for line, left in pending:
            rows = Inventory.objects.filter(material=line.material, cnt__gt=0).order_by('id')
            for row in rows:
                if left <= 0:
                    break
                available = row.cnt - reserved.get(row.pk, Decimal('0'))
                if available <= 0:
                    continue
                qty = left if left <= available else available
                OutItem.objects.create(master=sheet, inventory=row, cnt=qty)
                reserved[row.pk] = reserved.get(row.pk, Decimal('0')) + qty
                left -= qty
                taken[line.pk] = taken.get(line.pk, Decimal('0')) + qty
        if not taken:
            raise ValueError('仓库里没有这些用料的库存')
        try:
            sheet.action_out(None)
        except Exception:
            raise ValueError('库存数量不够，领料没有过账')
        for line, _left in pending:
            got = taken.get(line.pk)
            if not got:
                continue
            line.issued_qty = (line.issued_qty or Decimal('0')) + got
            line.save(update_fields=['issued_qty'])
            MaterialLot.objects.create(
                material=line.material, work_order=order, qty=got,
                status='issued', heat_no=(order.code or '')[:40],
            )
        _fill_cost(order)
        order.save(update_fields=['material_cost', 'labor_cost', 'modification'])
        log_event(order.qr_token, 'issue', '领料过账 %s' % (sheet.code or sheet.pk), user)
    return sheet


def receive_finished(order, user):
    """工序完工后把合格品写入库存。"""
    from invent.models import InItem, StockIn

    if order.status != 'done':
        raise ValueError('工序全部完工后才能入库')
    if order.stocked_at:
        raise ValueError('这张工单已经完工入库')
    if not order.material_id:
        raise ValueError('工单没有成品物料，不能入库')
    reported = [
        op for op in order.operations.order_by('seq', 'id')
        if (op.good_qty or 0) > 0 or (op.scrap_qty or 0) > 0
    ]
    good = reported[-1].good_qty if reported else order.qty
    if not good or good <= 0:
        raise ValueError('没有合格数量，不能入库')
    warehouse = order.material.warehouse or Warehouse.objects.order_by('id').first()
    if warehouse is None:
        raise ValueError('请先在基础数据里建一个仓库')
    measure = order.material.measure.order_by('id').first()
    if measure is None:
        measure, _created = Measure.objects.get_or_create(code='PCS', defaults={'name': '件'})
        order.material.measure.add(measure)
    _fill_cost(order)
    unit = Decimal('0')
    if good:
        unit = ((order.material_cost or Decimal('0')) + (order.labor_cost or Decimal('0'))) / Decimal(good)
    if unit <= 0:
        unit = order.material.stock_price or Decimal('0')
    with transaction.atomic():
        sheet = StockIn.objects.create(
            title=('入库%s' % (order.code or order.pk))[:40],
            warehouse=warehouse,
            user=user if getattr(user, 'is_authenticated', False) else None,
            batch=(order.code or '')[:20],
        )
        InItem.objects.create(
            master=sheet, material=order.material, measure=measure,
            warehouse=warehouse, cnt=good, price=unit,
        )
        try:
            sheet.action_entry(None)
        except Exception:
            raise ValueError('完工入库没有过账，请检查仓库和计量单位')
        order.stocked_at = timezone.now()
        order.save(update_fields=['stocked_at', 'material_cost', 'labor_cost', 'modification'])
        log_event(order.qr_token, 'stock', '完工入库 %s' % good, user)
    return sheet


def _fill_cost(order):
    material_cost = Decimal('0')
    for line in order.materials.select_related('material'):
        price = line.material.stock_price or Decimal('0')
        material_cost += (line.issued_qty or Decimal('0')) * price
    labor_cost = Decimal('0')
    logs = JobLog.objects.filter(operation__work_order=order).select_related('machine')
    for row in logs:
        rate = row.machine.hour_rate if row.machine_id else Decimal('0')
        labor_cost += (row.minutes or Decimal('0')) / Decimal('60') * (rate or Decimal('0'))
    order.material_cost = material_cost.quantize(Decimal('0.01'))
    order.labor_cost = labor_cost.quantize(Decimal('0.01'))


def shortage_lines(orders):
    """还没领、仓库也不够的用料。"""
    from invent.models import Inventory

    rows = []
    for order in orders:
        for line in order.materials.select_related('material'):
            left = line.left_qty()
            if left <= 0:
                continue
            onhand = Inventory.objects.filter(material=line.material).aggregate(total=Sum('cnt')).get('total') or Decimal('0')
            short = left - onhand
            if short > 0:
                rows.append((order, line, onhand, short))
    return rows
