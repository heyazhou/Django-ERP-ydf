import datetime
from decimal import Decimal

from django.db.models import Sum
from django.db.models.functions import Coalesce

from cnc.models import SCRAP_REASONS, Inspection, JobLog, Machine, OutsourceOrder, Tool, WorkOrder


def _month_start():
    today = datetime.date.today()
    return datetime.datetime(today.year, today.month, 1)


def progress_rows():
    rows = []
    orders = WorkOrder.objects.exclude(status__in=['closed', 'cancelled', 'draft']).select_related('customer')
    for order in orders:
        rows.append({
            'code': order.code,
            'title': order.title,
            'qty': order.qty,
            'due': order.due_date,
            'status': order.get_status_display(),
            'progress': order.progress_text(),
            'late': order.is_late(),
            'url': order.qr_path,
        })
    return rows


def due_rows():
    today = datetime.date.today()
    horizon = today + datetime.timedelta(days=7)
    orders = WorkOrder.objects.exclude(
        status__in=['done', 'closed', 'cancelled']
    ).filter(due_date__isnull=False, due_date__lte=horizon).order_by('due_date')
    return [{
        'code': order.code,
        'title': order.title,
        'due': order.due_date,
        'status': order.get_status_display(),
        'progress': order.progress_text(),
        'late': order.due_date < today,
        'url': order.qr_path,
    } for order in orders]


def machine_rows():
    today = datetime.date.today()
    start = datetime.datetime.combine(today, datetime.time.min)
    rows = []
    for machine in Machine.objects.all():
        minutes = JobLog.objects.filter(machine=machine, created__gte=start).aggregate(
            total=Coalesce(Sum('minutes'), Decimal('0')))['total']
        rows.append({
            'code': machine.code,
            'name': machine.name,
            'type': machine.get_machine_type_display(),
            'status': machine.get_status_display(),
            'minutes': minutes,
            'url': machine.qr_path,
        })
    return rows


def quality_rows():
    start = _month_start()
    logs = JobLog.objects.filter(created__gte=start)
    total_good = logs.aggregate(v=Coalesce(Sum('good_qty'), Decimal('0')))['v']
    total_scrap = logs.aggregate(v=Coalesce(Sum('scrap_qty'), Decimal('0')))['v']
    denom = total_good + total_scrap
    rate = (total_scrap / denom * 100) if denom else Decimal('0')
    by_reason = []
    for key, label in SCRAP_REASONS:
        qty = logs.filter(scrap_reason=key).aggregate(v=Coalesce(Sum('scrap_qty'), Decimal('0')))['v']
        if qty:
            by_reason.append({'label': label, 'qty': qty})
    inspections = Inspection.objects.filter(creation__gte=start)
    from quality.models import STAGES, CheckRecord
    checks = CheckRecord.objects.filter(creation__gte=start)
    stages = []
    for key, label in STAGES:
        rows = checks.filter(stage=key)
        count = rows.count()
        if count:
            stages.append({
                'label': label,
                'total': count,
                'fail': rows.filter(result='fail').count(),
            })
    return {
        'good': total_good,
        'scrap': total_scrap,
        'rate': rate.quantize(Decimal('0.01')),
        'reasons': by_reason,
        'fail_sheets': inspections.exclude(result='pass').count(),
        'sheets': inspections.count(),
        'stages': stages,
        'open_checks': CheckRecord.objects.filter(status='open').count(),
    }


def operator_rows():
    start = _month_start()
    grouped = JobLog.objects.filter(created__gte=start, user__isnull=False).values(
        'user__username', 'user__first_name'
    ).annotate(
        good=Coalesce(Sum('good_qty'), Decimal('0')),
        scrap=Coalesce(Sum('scrap_qty'), Decimal('0')),
        minutes=Coalesce(Sum('minutes'), Decimal('0')),
    ).order_by('-good')
    rows = []
    for item in grouped:
        name = item['user__first_name'] or item['user__username']
        rows.append({
            'name': name,
            'good': item['good'],
            'scrap': item['scrap'],
            'minutes': item['minutes'],
        })
    return rows


def outsource_rows():
    orders = OutsourceOrder.objects.exclude(status__in=['closed', 'draft']).select_related('work_order', 'vendor')
    return [{
        'code': item.code,
        'title': item.work_order.title,
        'vendor': item.vendor,
        'qty': item.qty,
        'status': item.get_status_display(),
        'sent': item.sent_at,
        'url': item.qr_path,
    } for item in orders]


def tool_rows():
    rows = []
    for tool in Tool.objects.exclude(status='scrap'):
        ratio = tool.life_ratio
        if ratio is None or ratio < Decimal('0.8'):
            continue
        rows.append({
            'code': tool.code,
            'name': tool.name,
            'spec': tool.spec,
            'used': tool.used_minutes,
            'life': tool.life_minutes,
            'ratio': int(ratio * 100),
            'url': tool.qr_path,
        })
    return rows
