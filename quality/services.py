# coding=utf-8
from decimal import Decimal, InvalidOperation

from cnc.qrutil import log_event
from quality.models import STAGES, CheckRecord, ControlPoint, Defect, Measure, Standard


def pick_standard(stage, material=None, process_name=''):
    found = _match_standard(stage, material, process_name)
    if found:
        return found
    if stage in ('first', 'patrol', 'final', 'ship'):
        return _match_standard('process' if stage != 'ship' else 'final', material, '') or _match_standard('process', material, '')
    if stage == 'assembly':
        return _match_standard('process', material, '')
    return None


def _match_standard(stage, material, process_name):
    base = Standard.objects.filter(stage=stage, active=True)
    if material is not None:
        scoped = base.filter(material=material)
        if process_name:
            named = scoped.filter(process_name=process_name)
            if named.exists():
                return named.order_by('-id').first()
        general = scoped.filter(process_name='')
        if general.exists():
            return general.order_by('-id').first()
    common = base.filter(material__isnull=True)
    if process_name:
        named = common.filter(process_name=process_name)
        if named.exists():
            return named.order_by('-id').first()
    return common.filter(process_name='').order_by('-id').first()


def open_check(stage, user, work_order=None, operation=None, lot=None, assembly_unit=None,
               outsource=None, inspection=None, result='pending', check_qty=0, fail_qty=0, note=''):
    if inspection is not None:
        existing = CheckRecord.objects.filter(inspection=inspection).first()
        if existing:
            return existing
    if operation is not None and work_order is None:
        work_order = operation.work_order
    material = None
    process_name = ''
    if operation is not None:
        process_name = operation.name or ''
    if work_order is not None and getattr(work_order, 'material_id', None):
        material = work_order.material
    if lot is not None and getattr(lot, 'material_id', None):
        material = lot.material
    standard = pick_standard(stage, material, process_name)
    record = CheckRecord.objects.create(
        stage=stage,
        standard=standard,
        work_order=work_order,
        operation=operation,
        lot=lot,
        assembly_unit=assembly_unit,
        outsource=outsource,
        inspection=inspection,
        check_qty=check_qty or 0,
        fail_qty=fail_qty or 0,
        result=result or 'pending',
        inspector=user if getattr(user, 'is_authenticated', False) else None,
        note=note or '',
    )
    if standard is not None:
        for item in standard.items.all():
            Measure.objects.create(
                record=record,
                seq=item.seq,
                name=item.name,
                nominal=item.nominal,
                lower_limit=item.lower_limit,
                upper_limit=item.upper_limit,
                unit=item.unit,
                method=item.method,
                key_size=item.key_size,
            )
    if result == 'fail':
        Defect.objects.create(
            record=record,
            qty=fail_qty or 0,
            note=note or '',
        )
    log_event(record.qr_token, 'inspect', '建立%s' % record.get_stage_display(), user)
    return record


def ensure_outsource_check(order, user):
    found = CheckRecord.objects.filter(outsource=order, stage='outsource').order_by('-id').first()
    if found:
        return found
    return open_check(
        'outsource', user,
        work_order=order.work_order,
        operation=order.operation,
        outsource=order,
        check_qty=order.qty,
    )


def operation_cleared(operation):
    if CheckRecord.objects.filter(operation=operation, result__in=('pass', 'concession')).exists():
        return True
    from cnc.models import Inspection
    return Inspection.objects.filter(operation=operation, result__in=('pass', 'concession')).exists()


def judge_text(measured, lower, upper):
    text = (measured or '').strip()
    if not text:
        return ''
    if text in ('合格', '通过', 'ok', 'OK'):
        return 'pass'
    if text in ('不合格', '超差'):
        return 'fail'
    try:
        value = Decimal(text)
    except (InvalidOperation, ValueError):
        return ''
    try:
        if (lower or '').strip() and value < Decimal(lower):
            return 'fail'
        if (upper or '').strip() and value > Decimal(upper):
            return 'fail'
    except (InvalidOperation, ValueError):
        return ''
    if (lower or '').strip() or (upper or '').strip():
        return 'pass'
    return ''


def save_measures(record, posted):
    failed = False
    for measure in record.measures.all():
        key = 'm%s' % measure.pk
        if key not in posted:
            continue
        measure.measured = (posted.get(key) or '').strip()[:40]
        measure.result = judge_text(measure.measured, measure.lower_limit, measure.upper_limit)
        measure.save(update_fields=['measured', 'result'])
        if measure.result == 'fail':
            failed = True
    return failed


def gaps_for_order(order):
    rows = []
    points = ControlPoint.objects.filter(required=True).exclude(stage__in=('incoming', 'ship', 'assembly'))
    for point in points:
        if point.stage == 'outsource' and not order.operations.filter(outsource=True).exists():
            continue
        operations = order.operations.all()
        if point.process_name:
            operations = operations.filter(name=point.process_name)
            if not operations.exists():
                continue
        checks = CheckRecord.objects.filter(work_order=order, stage=point.stage, result__in=('pass', 'concession'))
        if point.process_name:
            checks = checks.filter(operation__name=point.process_name)
        if point.stage in ('first', 'patrol', 'process', 'final') and point.process_name:
            from cnc.models import Inspection
            if Inspection.objects.filter(
                    work_order=order, operation__name=point.process_name,
                    result__in=('pass', 'concession')).exists():
                continue
        if not checks.exists() and point.stage in ('first', 'patrol', 'final'):
            from cnc.models import Inspection
            kind = {'first': 'first', 'patrol': 'patrol', 'final': 'final'}.get(point.stage)
            if Inspection.objects.filter(work_order=order, kind=kind, result__in=('pass', 'concession')).exists():
                continue
        if not checks.exists():
            rows.append(point)
    return rows


def stage_label(stage):
    return dict(STAGES).get(stage, stage)
