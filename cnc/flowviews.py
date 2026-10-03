# coding=utf-8
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import redirect, render

from cnc.flowmode import KIND_LABEL
from cnc.models import Handoff
from cnc.qrutil import find_by_token, log_event
from workflow.phoneflow import decide_flow, start_flow


@login_required
def flow_home(request):
    return redirect('cnc_home')


@login_required
def flow_moves(request):
    from cnc.mine import owned_moves
    return render(request, 'cnc/mobile/moves.html', owned_moves(request.user))


@login_required
def flow_send(request):
    if request.method != 'POST':
        return redirect('cnc_flow')
    token = (request.POST.get('token') or '').strip()
    obj = find_by_token(token)
    if obj is None:
        messages.error(request, '\u6ca1\u6709\u627e\u5230\u8fd9\u5f20\u5355')
        return redirect('cnc_home')
    kind = request.POST.get('kind') or 'info'
    if kind not in KIND_LABEL:
        kind = 'info'
    body = (request.POST.get('body') or '').strip()[:160]
    place = (request.POST.get('place') or '').strip()[:40]
    qty = (request.POST.get('qty') or '').strip()[:20]
    if not body and not place and not qty:
        messages.error(request, '\u8bf7\u586b\u5199\u8981\u4f20\u9012\u7684\u5185\u5bb9')
        return redirect('cnc_open', token=token)
    receiver = User.objects.filter(pk=request.POST.get('receiver') or 0, is_active=True).first()
    if kind == 'info' and receiver is None:
        messages.error(request, '\u4fe1\u606f\u8981\u9009\u62e9\u4ea4\u7ed9\u8c01')
        return redirect('cnc_open', token=token)
    parts = [KIND_LABEL[kind]]
    if place:
        parts.append(place)
    if qty:
        parts.append(qty)
    if body:
        parts.append(body)
    summary = ' '.join(parts)[:200]
    Handoff.objects.create(
        token=token, kind=kind, sender=request.user, receiver=receiver,
        place=place, qty=qty, body=body or summary)
    log_event(token, kind, summary, request.user)
    if receiver:
        messages.success(request, '\u5df2\u4f20\u7ed9 %s' % receiver.username)
    else:
        messages.success(request, '\u5df2\u8bb0\u5728\u8fd9\u5f20\u5355\u7684\u6d41\u8f6c\u4e0a')
    return redirect('cnc_open', token=token)


@login_required
def flow_decide(request):
    if request.method != 'POST':
        return redirect('cnc_flow')
    token = (request.POST.get('token') or '').strip()
    obj = find_by_token(token)
    if obj is None:
        messages.error(request, '\u6ca1\u6709\u627e\u5230\u8fd9\u5f20\u5355')
        return redirect('cnc_home')
    operation = request.POST.get('operation') or ''
    if operation == 'start':
        text = start_flow(request, obj)
    else:
        text = decide_flow(request, obj, operation, request.POST.get('memo') or '')
    if text.startswith('\u5df2'):
        messages.success(request, text)
        log_event(token, 'info', text, request.user)
    else:
        messages.error(request, text)
    return redirect('cnc_open', token=token)
