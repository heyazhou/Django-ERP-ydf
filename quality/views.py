# coding=utf-8
from django.contrib import messages
from django.db.models import Q
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from cnc.models import ShopEvent
from cnc.qrutil import log_event
from quality.models import DISPOSITIONS, RESULTS, CheckRecord, Defect, Standard
from quality.services import save_measures


def _events(token):
    return ShopEvent.objects.filter(token=token).select_related('user')[:8]


@login_required
def open_list(request):
    records = CheckRecord.objects.filter(status='open').filter(
        Q(inspector=request.user) | Q(operation__operator=request.user)
    ).select_related('work_order', 'operation')[:30]
    return render(request, 'quality/mobile/open.html', {'records': records})


@login_required
def standard_page(request, pk):
    item = get_object_or_404(Standard.objects.prefetch_related('items'), pk=pk)
    return render(request, 'quality/mobile/standard.html', {
        'item': item,
        'events': _events(item.qr_token),
    })


@login_required
def check_page(request, pk):
    record = get_object_or_404(
        CheckRecord.objects.select_related(
            'work_order', 'operation', 'lot', 'standard', 'inspector', 'assembly_unit', 'outsource'
        ).prefetch_related('measures', 'defects'),
        pk=pk,
    )
    if request.method == 'POST':
        action = request.POST.get('action') or 'save'
        failed = save_measures(record, request.POST)
        record.note = (request.POST.get('note') or record.note or '')[:200]
        record.disposition = request.POST.get('disposition') or record.disposition
        if action == 'close':
            record.result = request.POST.get('result') or record.result
            if failed and record.result == 'pass':
                record.result = 'fail'
            if record.result == 'pending':
                messages.error(request, '请先给出检验结论')
                return redirect('quality_check', pk=record.pk)
            record.status = 'closed'
            record.save()
            if record.result == 'fail' and not record.defects.exists():
                Defect.objects.create(
                    record=record,
                    qty=record.fail_qty or 0,
                    disposition=record.disposition,
                    note=record.note,
                )
            log_event(record.qr_token, 'inspect', '检验关闭 %s' % record.get_result_display(), request.user)
            messages.success(request, '检验已关闭')
        else:
            result = request.POST.get('result') or record.result
            if failed and result == 'pass':
                result = 'fail'
            record.result = result
            record.save()
            log_event(record.qr_token, 'inspect', '填写实测', request.user)
            messages.success(request, '实测已保存')
        return redirect('quality_check', pk=record.pk)
    return render(request, 'quality/mobile/check.html', {
        'record': record,
        'results': RESULTS,
        'dispositions': DISPOSITIONS,
        'events': _events(record.qr_token),
    })
