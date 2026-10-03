# coding=utf-8
import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from basedata.models import Employee, Material
from cnc.models import Drawing, FaceSample, Fixture, Machine, Tool, WorkOperation, WorkOrder
from cnc.qrutil import find_by_token
from cnc.trainer import (
    complete_samples, match_employee, match_material, refresh_profile_face,
    refresh_profile_object, train_faces, train_objects,
)
from cnc.vision import decode_texts, read_image, token_from_text


def locate(text):
    token = token_from_text(text)
    if not token:
        return None
    found = find_by_token(token)
    if found is not None:
        return found
    material = Material.objects.filter(barcode=token).exclude(barcode__isnull=True).exclude(barcode='').first()
    if material is not None:
        return material
    for model in (Material, Employee, Machine, Tool, Fixture, Drawing, WorkOrder):
        found = model.objects.filter(code=token).first()
        if found is not None:
            return found
    return None


def recognize(data):
    image = read_image(data)
    unknown = ''
    for text in decode_texts(image):
        found = locate(text)
        if found is not None:
            return found, ''
        unknown = token_from_text(text)
    person = match_employee(image)
    if person is not None:
        return person, ''
    material = match_material(image)
    if material is not None:
        return material, ''
    return None, unknown


def owner_of(user):
    person = Employee.objects.filter(user=user).first()
    if person is None:
        return user.username, user.username
    owner_id = person.qr_token or person.code or str(person.pk)
    return owner_id, person.name or user.username


def remember_shot(request, found, unknown):
    owner_id, owner_name = owner_of(request.user)
    shot_at = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    token = getattr(found, 'qr_token', None) or ''
    label = str(found) if found is not None else (unknown or '\u672a\u8bc6\u522b')
    request.session['shot'] = {
        'token': token,
        'object': label[:80],
        'owner_id': owner_id,
        'owner': owner_name,
        'at': shot_at,
    }
    request.session.modified = True
    return token, shot_at, owner_id


def save_input(request, token, owner_id, shot_at):
    from cnc.models import Handoff
    from cnc.qrutil import log_event
    body = (request.POST.get('body') or '').strip()[:160]
    place = (request.POST.get('place') or '').strip()[:40]
    qty = (request.POST.get('qty') or '').strip()[:20]
    if not token or not (body or place or qty):
        return
    text = ' '.join(part for part in (place, qty, body) if part)[:200]
    Handoff.objects.create(
        token=token, kind='data', sender=request.user, receiver=None,
        place=place, qty=qty, body=text)
    log_event(token[:32], 'data', '\u673a\u4e3b%s %s %s' % (owner_id, shot_at, text), request.user)


def open_shot(request):
    from urllib.parse import quote
    from cnc.qrutil import log_event
    upload = request.FILES.get('image')
    if not upload:
        last = request.session.get('shot') or {}
        token = last.get('token') or ''
        filled = request.POST.get('body') or request.POST.get('place') or request.POST.get('qty')
        if token and filled:
            save_input(request, token, last.get('owner_id') or '', last.get('at') or '')
            messages.success(request, '\u6570\u636e\u5df2\u8bb0\u5230\u4e0a\u4e00\u6b21\u62cd\u6444\u7684\u5bf9\u8c61')
            return redirect('cnc_open', token=token)
        messages.error(request, '\u8bf7\u5148\u62cd\u7167')
        return redirect('cnc_home')
    found, unknown = recognize(upload.read())
    token, shot_at, owner_id = remember_shot(request, found, unknown)
    if token:
        log_event(
            token[:32], 'shot',
            '\u673a\u4e3b%s \u4e8e%s \u62cd\u6444 %s' % (owner_id, shot_at, request.session['shot']['object']),
            request.user)
        save_input(request, token, owner_id, shot_at)
        messages.success(request, '\u5df2\u6309\u62cd\u6444\u5bf9\u8c61\u6253\u5f00\u4e0b\u4e00\u9875')
        return redirect('cnc_open', token=token)
    if found is not None:
        messages.success(request, '\u5df2\u6309\u62cd\u6444\u5bf9\u8c61\u6253\u5f00\u4e0b\u4e00\u9875')
        return redirect('cnc_doc', token=getattr(found, 'code', '') or found.pk)
    if unknown:
        messages.warning(request, '\u8fd9\u4e2a\u7801\u8fd8\u6ca1\u5efa\u6863')
        return redirect('/m/entry/material/?code=%s' % quote(unknown))
    messages.error(request, '\u6ca1\u6709\u8bc6\u522b\u5230\u62cd\u6444\u5bf9\u8c61')
    return redirect('cnc_home')


@login_required
def identify(request):
    if request.method == 'POST':
        return open_shot(request)
    return redirect('cnc_home')


@login_required
def employee_page(request, pk):
    item = get_object_or_404(Employee.objects.select_related('position', 'user'), pk=pk)
    if request.method == 'POST':
        phone = (request.POST.get('phone') or '').strip()[:20]
        if phone != (item.phone or ''):
            item.phone = phone
            item.save(update_fields=['phone', 'modification'])
        photo = request.FILES.get('photo')
        if photo:
            if not item.photo:
                item.photo = photo
                item.save()
                status = refresh_profile_face(item)
            else:
                sample = FaceSample(employee=item, origin='train')
                sample.photo = photo
                sample.save()
                complete_samples()
                status = 'ok'
            train_faces()
            if status == 'empty':
                messages.warning(request, '\u7167\u7247\u91cc\u6ca1\u6709\u6b63\u8138')
            else:
                messages.success(request, '\u4eba\u8138\u5df2\u8865\u5145\u5e76\u5b8c\u6210\u8bad\u7ec3')
        else:
            messages.success(request, '\u804c\u5458\u8d44\u6599\u5df2\u66f4\u65b0')
        return redirect('cnc_employee', pk=item.pk)
    jobs = []
    if item.user_id:
        jobs = WorkOperation.objects.filter(
            operator=item.user, status__in=['ready', 'running']
        ).select_related('work_order')[:12]
    return render(request, 'cnc/mobile/employee.html', {
        'item': item,
        'faces': item.faces.count(),
        'jobs': jobs,
    })


@login_required
def material_page(request, pk):
    from cnc.intake import SUPPLY
    from cnc.models import MaterialLot
    item = get_object_or_404(Material, pk=pk)
    if request.method == 'POST':
        item.barcode = (request.POST.get('barcode') or '').strip()[:40]
        kind = request.POST.get('supply_kind') or ''
        if kind in dict(SUPPLY) or kind == '':
            item.supply_kind = kind
        if request.FILES.get('photo'):
            item.photo = request.FILES['photo']
        if request.FILES.get('drawing_file'):
            item.drawing_file = request.FILES['drawing_file']
        if request.FILES.get('model_file'):
            item.model_file = request.FILES['model_file']
        item.save()
        if request.FILES.get('photo'):
            refresh_profile_object(item)
            train_objects()
        messages.success(request, '\u7269\u6599\u8d44\u6599\u5df2\u4f20\u8f93')
        return redirect('cnc_material', pk=item.pk)
    lots = MaterialLot.objects.filter(material=item).order_by('-id')[:8]
    drawings = Drawing.objects.filter(material=item).order_by('-id')[:6]
    return render(request, 'cnc/mobile/material.html', {
        'item': item,
        'lots': lots,
        'drawings': drawings,
    })
