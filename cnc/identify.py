# coding=utf-8
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from basedata.models import Employee, Material
from cnc.models import Drawing, Fixture, Machine, Tool, WorkOperation, WorkOrder
from cnc.qrutil import find_by_token
from cnc.trainer import match_employee, match_material, status_text
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


@login_required
def identify(request):
    unknown = ''
    if request.method == 'POST' and request.FILES.get('image'):
        upload = request.FILES['image']
        data = upload.read()
        found, unknown = recognize(data)
        if found is not None and getattr(found, 'qr_token', None):
            messages.success(request, '\u5df2\u8bc6\u522b %s' % found)
            return redirect('cnc_open', token=found.qr_token)
        if found is not None:
            messages.success(request, '\u5df2\u8bc6\u522b %s' % found)
            return redirect('cnc_doc', token=getattr(found, 'code', '') or found.pk)
        messages.error(request, '\u6ca1\u6709\u8bc6\u522b\u5230\u5df2\u5efa\u6863\u7684\u4e8c\u7ef4\u7801\u3001\u6761\u7801\u3001\u4eba\u8138\u6216\u7269\u4f53')
    people = Employee.objects.order_by('code')[:40]
    return render(request, 'cnc/mobile/identify.html', {
        'unknown': unknown,
        'people': people,
        'trained': status_text(),
    })


@login_required
def employee_page(request, pk):
    item = get_object_or_404(Employee.objects.select_related('position', 'user'), pk=pk)
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
    from cnc.models import MaterialLot
    item = get_object_or_404(Material, pk=pk)
    lots = MaterialLot.objects.filter(material=item).order_by('-id')[:8]
    drawings = Drawing.objects.filter(material=item).order_by('-id')[:6]
    return render(request, 'cnc/mobile/material.html', {
        'item': item,
        'lots': lots,
        'drawings': drawings,
    })
