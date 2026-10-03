# coding=utf-8
import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from basedata.models import Employee, Material
from cnc.models import MACHINE_TYPES, Fixture, Machine, Tool
from cnc.qrutil import log_event
from cnc.trainer import refresh_profile_face, refresh_profile_object, train_faces, train_objects

KINDS = (
    ('face', '\u804c\u5458\u4eba\u8138', '\u62cd\u6b63\u8138\uff0c\u586b\u59d3\u540d\u548c\u7535\u8bdd\uff0c\u751f\u6210\u5de5\u724c\u4e8c\u7ef4\u7801'),
    ('material', '\u7269\u6599', '\u62cd\u5b9e\u7269\u6216\u6761\u7801\uff0c\u586b\u540d\u79f0\u3001\u89c4\u683c\u548c\u7c7b\u522b'),
    ('fixture', '\u5939\u5177', '\u62cd\u5939\u5177\uff0c\u586b\u540d\u79f0\u548c\u89c4\u683c\uff0c\u751f\u6210\u55b7\u7801'),
    ('machine', '\u8bbe\u5907', '\u62cd\u8bbe\u5907\uff0c\u586b\u540d\u79f0\u548c\u7c7b\u578b\uff0c\u751f\u6210\u8bbe\u5907\u7801'),
    ('tool', '\u5200\u5177', '\u62cd\u5200\u5177\uff0c\u586b\u540d\u79f0\u548c\u89c4\u683c'),
)

SUPPLY = (
    ('raw', '\u539f\u6750\u6599'),
    ('hardware', '\u4e94\u91d1'),
    ('cutter', '\u5200\u5177'),
    ('tool', '\u5de5\u5177'),
    ('aux', '\u8f85\u6599'),
    ('part', '\u52a0\u5de5\u4ef6'),
)


def _text(request, name, limit):
    return (request.POST.get(name) or '').strip()[:limit]


def _stamp(obj, user):
    today = datetime.date.today()
    obj.begin = today
    obj.end = datetime.date(9999, 12, 31)
    obj.creator = (user.username or '')[:20]
    obj.modifier = obj.creator


def _positions():
    from organ.models import Position
    return Position.objects.order_by('code')[:60]


@login_required
def entry_home(request):
    return render(request, 'cnc/mobile/entry.html', {'kinds': KINDS})


@login_required
def entry_form(request, kind):
    labels = dict((key, label) for key, label, _note in KINDS)
    if kind not in labels:
        return redirect('cnc_entry')
    code = (request.GET.get('code') or request.POST.get('barcode') or '').strip()
    if request.method == 'POST':
        made = _create(request, kind)
        if made is not None:
            return redirect('cnc_open', token=made.qr_token)
    return render(request, 'cnc/mobile/entry_form.html', {
        'kind': kind,
        'title': labels[kind],
        'code': code,
        'positions': _positions() if kind == 'face' else [],
        'supplies': SUPPLY,
        'machines': MACHINE_TYPES,
    })


def _create(request, kind):
    limits = {'face': 120, 'material': 120, 'fixture': 40, 'machine': 40, 'tool': 40}
    name = _text(request, 'name', limits[kind])
    if not name:
        messages.error(request, '\u8bf7\u586b\u5199\u540d\u79f0')
        return None
    if kind == 'face':
        return _create_face(request, name)
    if kind == 'material':
        return _create_material(request, name)
    if kind == 'fixture':
        item = Fixture(name=name, spec=_text(request, 'spec', 60))
    elif kind == 'machine':
        machine_type = request.POST.get('machine_type') or 'MANUAL'
        allowed = dict(MACHINE_TYPES)
        if machine_type not in allowed:
            machine_type = 'MANUAL'
        item = Machine(name=name, machine_type=machine_type, brand=_text(request, 'spec', 60))
    elif kind == 'tool':
        item = Tool(name=name, spec=_text(request, 'spec', 60))
    else:
        return None
    _stamp(item, request.user)
    if request.FILES.get('photo'):
        item.photo = request.FILES['photo']
    item.save()
    log_event(item.qr_token, 'entry', '\u624b\u673a\u5f55\u5165 %s' % item, request.user)
    messages.success(request, '\u5df2\u5efa\u6863\uff0c\u8bf7\u6253\u5370\u6216\u55b7\u6d82\u4e8c\u7ef4\u7801')
    return item


def _create_face(request, name):
    from organ.models import Position
    position = Position.objects.filter(pk=request.POST.get('position')).first()
    if position is None:
        position = Position.objects.order_by('id').first()
    if position is None:
        messages.error(request, '\u8fd8\u6ca1\u6709\u5c97\u4f4d\uff0c\u8bf7\u5148\u5728\u540e\u53f0\u5efa\u4e00\u4e2a\u5c97\u4f4d')
        return None
    person = Employee(
        name=name,
        phone=_text(request, 'phone', 20),
        idcard=_text(request, 'idcard', 20) or '\u672a\u91c7\u96c6',
        position=position,
    )
    _stamp(person, request.user)
    if request.FILES.get('photo'):
        person.photo = request.FILES['photo']
    person.save()
    if not person.code:
        person.code = '1%05d' % person.pk
        person.save(update_fields=['code'])
    if person.photo:
        status = refresh_profile_face(person)
        train_faces()
        if status == 'empty':
            messages.warning(request, '\u7167\u7247\u91cc\u6ca1\u6709\u6b63\u8138\uff0c\u4eba\u8138\u8fd8\u6ca1\u8fdb\u5165\u6a21\u578b')
    log_event(person.qr_token, 'entry', '\u624b\u673a\u5f55\u5165\u804c\u5458 %s' % person, request.user)
    messages.success(request, '\u804c\u5458\u5df2\u5efa\u6863\uff0c\u5de5\u724c\u4e8c\u7ef4\u7801\u53ef\u4ee5\u6253\u5370')
    return person


def _create_material(request, name):
    barcode = _text(request, 'barcode', 40)
    if barcode:
        existed = Material.objects.filter(barcode=barcode).exclude(barcode='').first()
        if existed is not None and existed.qr_token:
            messages.success(request, '\u8fd9\u4e2a\u6761\u7801\u5df2\u7ecf\u5efa\u6863')
            return existed
    allowed = dict(SUPPLY)
    kind = request.POST.get('supply_kind') or ''
    if kind not in allowed:
        kind = ''
    item = Material(name=name, spec=_text(request, 'spec', 120), barcode=barcode, supply_kind=kind)
    _stamp(item, request.user)
    if request.FILES.get('photo'):
        item.photo = request.FILES['photo']
    if request.FILES.get('drawing_file'):
        item.drawing_file = request.FILES['drawing_file']
    if request.FILES.get('model_file'):
        item.model_file = request.FILES['model_file']
    item.save()
    if not item.code:
        item.code = 'IT%05d' % item.pk
        item.save(update_fields=['code'])
    if item.photo:
        refresh_profile_object(item)
        train_objects()
    log_event(item.qr_token, 'entry', '\u624b\u673a\u5f55\u5165\u7269\u6599 %s' % item, request.user)
    messages.success(request, '\u7269\u6599\u5df2\u5efa\u6863\uff0c\u8bf7\u628a\u4e8c\u7ef4\u7801\u8d34\u5230\u7269\u6599\u4e0a')
    return item
