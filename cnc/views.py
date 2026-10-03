import io
from decimal import Decimal, InvalidOperation

import segno
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from cnc import reports
from cnc.models import (
    MACHINE_STATUS, SCRAP_REASONS, Drawing, Fixture, Inspection, Machine,
    AssemblyOrder, AssemblyPart, AssemblyUnit, MaintainOrder, MaterialLot, NcProgram, OutsourceOrder,
    Routing, ShopArea, ShopEvent, Tool, WorkOperation, WorkOrder,
)
from cnc.qrutil import find_by_token, log_event, object_url


def _decimal(value):
    try:
        return Decimal(value or 0)
    except (InvalidOperation, TypeError):
        return None


def _events(token, limit=8):
    return ShopEvent.objects.filter(token=token).select_related('user')[:limit]


@login_required
def home(request):
    from cnc.identify import owner_of
    from cnc.mine import owner_feed
    owner_id, owner_name = owner_of(request.user)
    feed = owner_feed(request.user)
    feed.update({'owner_id': owner_id, 'owner_name': owner_name})
    return render(request, 'cnc/mobile/home.html', feed)


@login_required
def scan(request):
    return render(request, 'cnc/mobile/scan.html')


@login_required
def qr_image(request, token):
    obj = find_by_token(token)
    if obj is None:
        return HttpResponse(status=404)
    token_value = getattr(obj, 'qr_token', None) or token
    buffer = io.BytesIO()
    segno.make(object_url(request, token_value), error='h').save(buffer, kind='svg', scale=6, border=4)
    return HttpResponse(buffer.getvalue(), content_type='image/svg+xml')


@login_required
def open_token(request, token):
    obj = find_by_token(token)
    if obj is None:
        messages.error(request, '没有找到这个二维码')
        return redirect('cnc_home')
    routes = {
        WorkOrder: 'cnc_workorder',
        WorkOperation: 'cnc_operation',
        Machine: 'cnc_machine',
        Tool: 'cnc_tool',
        Fixture: 'cnc_fixture',
        MaterialLot: 'cnc_lot',
        Inspection: 'cnc_inspection',
        NcProgram: 'cnc_program',
        Drawing: 'cnc_drawing',
        OutsourceOrder: 'cnc_outsource',
        Routing: 'cnc_routing',
        ShopArea: 'cnc_board_area',
        AssemblyOrder: 'cnc_assembly',
        AssemblyUnit: 'cnc_assembly_unit',
        MaintainOrder: 'cnc_maintain',
    }
    from basedata.models import Employee, Material
    from quality.models import CheckRecord, Standard
    routes[Employee] = 'cnc_employee'
    routes[Material] = 'cnc_material'
    routes[CheckRecord] = 'quality_check'
    routes[Standard] = 'quality_standard'
    from django.urls import reverse
    log_event(getattr(obj, 'qr_token', None) or token, 'scan', '扫码查看 %s' % obj, request.user)
    name = routes.get(obj.__class__)
    if not name:
        return redirect('cnc_doc', token=token)
    return redirect(reverse(name, args=[obj.pk]))


@login_required
def workorder(request, pk):
    order = get_object_or_404(WorkOrder.objects.select_related('customer', 'material', 'routing'), pk=pk)
    if request.method == 'POST' and request.POST.get('action') == 'release':
        try:
            order.release(request.user)
            messages.success(request, '工单已下达')
        except ValueError as exc:
            messages.error(request, str(exc))
        return redirect('cnc_workorder', pk=order.pk)
    from quality.services import gaps_for_order
    return render(request, 'cnc/mobile/workorder.html', {
        'order': order,
        'operations': order.operations.select_related('machine'),
        'gaps': gaps_for_order(order),
        'checks': order.quality_checks.all()[:8],
        'drawings': order.drawing_set.all()[:8] if hasattr(order, 'drawing_set') else [],
        'events': _events(order.qr_token),
    })


@login_required
def traveler(request, pk):
    order = get_object_or_404(WorkOrder, pk=pk)
    return render(request, 'cnc/mobile/traveler.html', {
        'order': order,
        'operations': order.operations.all(),
    })


@login_required
@require_http_methods(['GET', 'POST'])
def operation(request, pk):
    op = get_object_or_404(
        WorkOperation.objects.select_related('work_order', 'machine', 'operator', 'program'), pk=pk)
    if request.method == 'POST':
        action = request.POST.get('action')
        try:
            if action == 'start':
                machine = None
                machine_id = request.POST.get('machine')
                if machine_id:
                    machine = Machine.objects.filter(pk=machine_id).first()
                op.start(request.user, machine)
                messages.success(request, '已开工')
            elif action == 'report':
                good = _decimal(request.POST.get('good'))
                scrap = _decimal(request.POST.get('scrap'))
                minutes = _decimal(request.POST.get('minutes'))
                if None in (good, scrap, minutes):
                    raise ValueError('请填写数字')
                op.report(
                    request.user, good, scrap,
                    request.POST.get('reason') or '',
                    minutes, request.POST.get('note') or '')
                messages.success(request, '报工已记录')
            elif action == 'finish':
                op.finish(request.user)
                messages.success(request, '工序已完工')
            elif action == 'bind_program':
                program = NcProgram.objects.filter(pk=request.POST.get('program')).first()
                if program is None:
                    raise ValueError('请选择数控程序')
                op.program = program
                op.setup_note = request.POST.get('setup_note') or op.setup_note
                op.save()
                log_event(op.qr_token, 'program', '使用程序 %s' % program, request.user)
                log_event(program.qr_token, 'program', '用于工序 %s' % op, request.user)
                messages.success(request, '已绑定数控程序')
            elif action == 'new_program':
                name = (request.POST.get('name') or '').strip()
                if not name:
                    raise ValueError('请填写程序名')
                program = NcProgram.objects.create(
                    name=name,
                    material=op.work_order.material,
                    operation_name=op.name,
                    version=request.POST.get('version') or 'A',
                    note=request.POST.get('note') or '',
                )
                op.program = program
                op.save()
                log_event(op.qr_token, 'program', '新建程序 %s' % program.name, request.user)
                messages.success(request, '加工程序已建立')
            elif action == 'inspect':
                check_qty = _decimal(request.POST.get('check_qty')) or Decimal('0')
                fail_qty = _decimal(request.POST.get('fail_qty')) or Decimal('0')
                sheet = Inspection.objects.create(
                    work_order=op.work_order,
                    operation=op,
                    kind=request.POST.get('kind') or 'first',
                    result=request.POST.get('result') or 'pass',
                    check_qty=check_qty,
                    fail_qty=fail_qty,
                    inspector=request.user,
                    note=request.POST.get('note') or '',
                )
                log_event(op.qr_token, 'inspect', '质检 %s' % sheet.get_result_display(), request.user)
                log_event(sheet.qr_token, 'inspect', '来自工序 %s' % op.name, request.user)
                from quality.services import open_check
                stage = {'first': 'first', 'patrol': 'patrol', 'final': 'final'}.get(sheet.kind, 'process')
                if op.machine_type == 'QC':
                    stage = 'process'
                record = open_check(
                    stage, request.user,
                    work_order=op.work_order,
                    operation=op,
                    inspection=sheet,
                    result=sheet.result,
                    check_qty=check_qty,
                    fail_qty=fail_qty,
                    note=sheet.note,
                )
                messages.success(request, '质检单已生成，请填写实测')
                return redirect('quality_check', pk=record.pk)
        except ValueError as exc:
            messages.error(request, str(exc))
        return redirect('cnc_operation', pk=op.pk)
    if op.machine_type == 'SETUP':
        machines = Machine.objects.filter(machine_type='MC')
    elif op.machine_type == 'MANUAL':
        machines = Machine.objects.filter(machine_type='MANUAL')
    elif op.machine_type == 'PROG':
        machines = Machine.objects.none()
    else:
        machines = Machine.objects.filter(machine_type=op.machine_type)
        if not machines.exists() and op.machine_type in ('QC', 'PACK', 'OUT', 'SAW'):
            machines = Machine.objects.all()
    machines = machines.exclude(status__in=['down', 'maintain'])
    programs = NcProgram.objects.all()
    if op.work_order.material_id:
        scoped = programs.filter(material=op.work_order.material)
        if scoped.exists():
            programs = scoped
    programs = programs.order_by('-id')[:12]
    linked = NcProgram.objects.filter(operation_name=op.name)[:5]
    drawings = Drawing.objects.filter(work_order=op.work_order)[:5]
    return render(request, 'cnc/mobile/operation.html', {
        'op': op,
        'machines': machines,
        'reasons': SCRAP_REASONS,
        'programs': list(programs) or list(linked),
        'drawings': drawings,
        'checks': op.quality_checks.all()[:6],
        'events': _events(op.qr_token),
    })


@login_required
@require_http_methods(['GET', 'POST'])
def machine(request, pk):
    item = get_object_or_404(Machine, pk=pk)
    if request.method == 'POST':
        status = request.POST.get('status')
        if request.FILES.get('photo'):
            item.photo = request.FILES['photo']
            item.save()
            messages.success(request, '设备照片已保存')
        elif status in dict(MACHINE_STATUS):
            item.set_status(status, request.user)
            messages.success(request, '设备状态已更新')
        return redirect('cnc_machine', pk=item.pk)
    jobs = WorkOperation.objects.filter(machine=item, status='running').select_related('work_order')
    maintains = MaintainOrder.objects.filter(machine=item).exclude(status__in=['done', 'cancelled'])
    return render(request, 'cnc/mobile/machine.html', {
        'item': item,
        'jobs': jobs,
        'maintains': maintains,
        'statuses': MACHINE_STATUS,
        'events': _events(item.qr_token),
    })


@login_required
@require_http_methods(['GET', 'POST'])
def maintain(request, pk):
    item = get_object_or_404(MaintainOrder.objects.select_related('machine', 'technician'), pk=pk)
    if request.method == 'POST':
        action = request.POST.get('action')
        try:
            if action == 'start':
                item.start(request.user)
                messages.success(request, '已开工')
            elif action == 'finish':
                item.finish(request.user, request.POST.get('work_done') or '')
                if request.POST.get('spare'):
                    item.spare = request.POST.get('spare')
                    item.save(update_fields=['spare', 'modification'])
                messages.success(request, '维修保养已完成')
            else:
                raise ValueError('无法识别的操作')
        except ValueError as exc:
            messages.error(request, str(exc))
        return redirect('cnc_maintain', pk=item.pk)
    return render(request, 'cnc/mobile/maintain.html', {
        'item': item,
        'events': _events(item.qr_token),
    })


@login_required
def tool(request, pk):
    item = get_object_or_404(Tool.objects.select_related('machine'), pk=pk)
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'photo' and request.FILES.get('photo'):
            item.photo = request.FILES['photo']
            item.save()
            messages.success(request, '刀具照片已保存')
        elif action == 'use':
            machine = Machine.objects.filter(pk=request.POST.get('machine')).first()
            item.machine = machine
            item.status = 'using'
            item.save()
            log_event(item.qr_token, 'tool', '领用到 %s' % (machine or ''), request.user)
            messages.success(request, '刀具已领用')
        elif action == 'return':
            minutes = _decimal(request.POST.get('minutes')) or Decimal('0')
            item.used_minutes = int(item.used_minutes + minutes)
            item.status = 'stock'
            item.machine = None
            item.save()
            log_event(item.qr_token, 'tool', '归还，本次 %s 分钟' % minutes, request.user)
            messages.success(request, '刀具已归还')
        elif action == 'scrap':
            item.status = 'scrap'
            item.save()
            log_event(item.qr_token, 'tool', '刀具报废', request.user)
            messages.success(request, '已报废')
        return redirect('cnc_tool', pk=item.pk)
    return render(request, 'cnc/mobile/tool.html', {
        'item': item,
        'machines': Machine.objects.all(),
        'events': _events(item.qr_token),
    })


@login_required
def fixture(request, pk):
    item = get_object_or_404(Fixture, pk=pk)
    if request.method == 'POST':
        if request.POST.get('action') == 'photo' and request.FILES.get('photo'):
            item.photo = request.FILES['photo']
            item.save()
            messages.success(request, '夹具照片已保存')
            return redirect('cnc_fixture', pk=item.pk)
        status = request.POST.get('status')
        if status in ('stock', 'using', 'repair'):
            item.status = status
            item.save()
            log_event(item.qr_token, 'fixture', '夹具改为%s' % item.get_status_display(), request.user)
            messages.success(request, '状态已更新')
        return redirect('cnc_fixture', pk=item.pk)
    return render(request, 'cnc/mobile/sheet.html', {
        'title': '夹具',
        'item': item,
        'rows': [('编号', item.code), ('名称', item.name), ('规格', item.spec), ('状态', item.get_status_display())],
        'events': _events(item.qr_token),
        'buttons': [('stock', '在库'), ('using', '在用'), ('repair', '送修')],
        'photo_form': True,
    })


@login_required
def lot(request, pk):
    item = get_object_or_404(MaterialLot.objects.select_related('material', 'work_order', 'warehouse'), pk=pk)
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'incoming':
            from quality.services import open_check
            record = open_check(
                'incoming', request.user, lot=item, work_order=item.work_order,
                check_qty=item.qty,
            )
            messages.success(request, '已开来料检验')
            return redirect('quality_check', pk=record.pk)
        if action == 'bind':
            order = WorkOrder.objects.filter(code=request.POST.get('wo_code')).first()
            if not order:
                messages.error(request, '没有这张工单')
            else:
                item.work_order = order
                item.status = 'issued'
                item.save()
                log_event(item.qr_token, 'issue', '发料到 %s' % order.code, request.user)
                log_event(order.qr_token, 'issue', '领用批次 %s' % item.code, request.user)
                messages.success(request, '已绑定工单')
        elif action in dict(item._meta.get_field('status').choices):
            item.status = action
            item.save()
            log_event(item.qr_token, 'lot', '批次改为%s' % item.get_status_display(), request.user)
            messages.success(request, '状态已更新')
        return redirect('cnc_lot', pk=item.pk)
    return render(request, 'cnc/mobile/lot.html', {
        'item': item,
        'incoming': item.quality_checks.filter(stage='incoming').order_by('-id').first(),
        'events': _events(item.qr_token),
    })


@login_required
def inspection(request, pk):
    item = get_object_or_404(Inspection.objects.select_related('work_order', 'operation', 'inspector'), pk=pk)
    return render(request, 'cnc/mobile/sheet.html', {
        'title': '质检单',
        'item': item,
        'rows': [
            ('编号', item.code),
            ('工单', item.work_order),
            ('工序', item.operation or ''),
            ('类型', item.get_kind_display()),
            ('结论', item.get_result_display()),
            ('检验数量', item.check_qty),
            ('不合格', item.fail_qty),
            ('检验员', item.inspector or ''),
            ('说明', item.note),
        ],
        'events': _events(item.qr_token),
    })


@login_required
def program(request, pk):
    item = get_object_or_404(NcProgram.objects.select_related('material'), pk=pk)
    return render(request, 'cnc/mobile/filecard.html', {
        'title': '数控程序',
        'item': item,
        'rows': [
            ('编号', item.code), ('程序名', item.name), ('工序', item.operation_name),
            ('版本', item.version), ('物料', item.material or ''), ('说明', item.note),
        ],
        'file': item.program_file,
        'events': _events(item.qr_token),
    })


@login_required
def drawing(request, pk):
    item = get_object_or_404(Drawing.objects.select_related('material', 'work_order'), pk=pk)
    return render(request, 'cnc/mobile/filecard.html', {
        'title': '图纸',
        'item': item,
        'rows': [
            ('编号', item.code), ('图号', item.drawing_no), ('名称', item.name),
            ('版本', item.version), ('工单', item.work_order or ''),
        ],
        'file': item.drawing_file,
        'model_file': item.model_file,
        'events': _events(item.qr_token),
    })


@login_required
def outsource(request, pk):
    item = get_object_or_404(OutsourceOrder.objects.select_related('work_order', 'vendor', 'operation'), pk=pk)
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'send':
            item.send_out(request.user)
            messages.success(request, '已发出')
        elif action == 'back':
            from quality.services import ensure_outsource_check
            if item.status == 'sent':
                item.receive(request.user)
            record = ensure_outsource_check(item, request.user)
            messages.success(request, '已回厂，请做回厂检验')
            return redirect('quality_check', pk=record.pk)
        return redirect('cnc_outsource', pk=item.pk)
    return render(request, 'cnc/mobile/outsource.html', {
        'item': item,
        'check': item.quality_checks.filter(stage='outsource').order_by('-id').first(),
        'events': _events(item.qr_token),
    })


@login_required
def routing(request, pk):
    item = get_object_or_404(Routing.objects.select_related('material'), pk=pk)
    return render(request, 'cnc/mobile/routing.html', {
        'item': item,
        'steps': item.steps.all(),
        'events': _events(item.qr_token),
    })


REPORTS = (
    ('progress', '在制进度'),
    ('due', '交期预警'),
    ('machine', '设备负荷'),
    ('quality', '质量报废'),
    ('operator', '员工产量'),
    ('outsource', '外协在途'),
    ('tool', '刀具寿命'),
)


@login_required
def document(request, token):
    obj = find_by_token(token)
    if obj is None:
        messages.error(request, '没有找到这个二维码')
        return redirect('cnc_home')
    rows = []
    skip = {'password', 'creator', 'modifier', 'begin', 'end'}
    for field in obj._meta.fields:
        if field.name in skip or field.primary_key:
            continue
        value = getattr(obj, field.name)
        if value in (None, ''):
            continue
        if field.choices:
            display = getattr(obj, 'get_%s_display' % field.name, None)
            value = display() if display else value
        rows.append((str(field.verbose_name), value))
        if len(rows) >= 10:
            break
    from django.urls import NoReverseMatch, reverse
    try:
        admin_url = reverse(
            'admin:%s_%s_change' % (obj._meta.app_label, obj._meta.model_name),
            args=[obj.pk])
    except NoReverseMatch:
        admin_url = ''
    return render(request, 'cnc/mobile/doc.html', {
        'title': str(obj._meta.verbose_name),
        'headline': str(obj),
        'token': token,
        'rows': rows,
        'admin_url': admin_url,
        'events': _events(token),
    })


@login_required
def assembly(request, pk):
    order = get_object_or_404(
        AssemblyOrder.objects.select_related('bom', 'product', 'customer', 'station'), pk=pk)
    if request.method == 'POST':
        action = request.POST.get('action')
        try:
            if action == 'release':
                order.release(request.user)
                messages.success(request, '装配工单已下达')
            elif action == 'issue':
                part = order.parts.get(pk=request.POST.get('part'))
                part.issue(_decimal(request.POST.get('qty')), request.POST.get('lot') or '', request.user)
                messages.success(request, '配料已登记')
            else:
                raise ValueError('无法识别的操作')
        except (ValueError, AssemblyPart.DoesNotExist) as exc:
            messages.error(request, str(exc))
        return redirect('cnc_assembly', pk=order.pk)
    return render(request, 'cnc/mobile/assembly.html', {
        'order': order,
        'parts': order.parts.select_related('material'),
        'units': order.units.select_related('station', 'assembler'),
        'components': order.component_jobs(),
        'events': _events(order.qr_token),
    })


@login_required
def assembly_unit(request, pk):
    unit = get_object_or_404(
        AssemblyUnit.objects.select_related('order', 'station', 'assembler'), pk=pk)
    if request.method == 'POST':
        action = request.POST.get('action')
        try:
            if action == 'start':
                station = Machine.objects.filter(pk=request.POST.get('station')).first()
                unit.start(request.user, station)
                messages.success(request, '已开始装配')
            elif action == 'finish':
                unit.finish(request.user)
                messages.success(request, '已装完，等待检验')
            elif action == 'inspect':
                result = request.POST.get('result') or ''
                unit.inspect(request.user, result, request.POST.get('note') or '')
                from quality.services import open_check
                record = open_check(
                    'assembly', request.user,
                    assembly_unit=unit,
                    result=result,
                    check_qty=1,
                    note=request.POST.get('note') or '',
                )
                messages.success(request, '装配检验已记录，请填写实测')
                return redirect('quality_check', pk=record.pk)
            elif action == 'fit':
                from basedata.models import Material
                material = Material.objects.filter(pk=request.POST.get('material')).first()
                if material is None:
                    raise ValueError('请选择零件')
                unit.fit(material, request.POST.get('lot') or '', _decimal(request.POST.get('qty')) or 1, request.user)
                messages.success(request, '装入记录已保存')
            else:
                raise ValueError('无法识别的操作')
        except ValueError as exc:
            messages.error(request, str(exc))
        return redirect('cnc_assembly_unit', pk=unit.pk)
    return render(request, 'cnc/mobile/assembly_unit.html', {
        'unit': unit,
        'stations': Machine.objects.filter(machine_type='ASSEM'),
        'parts': unit.order.parts.select_related('material'),
        'fits': unit.fits.select_related('material'),
        'check': unit.quality_checks.order_by('-id').first(),
        'events': _events(unit.qr_token),
    })


@login_required
def board_index(request):
    from cnc.boards import board_snapshot, ensure_shop_areas
    ensure_shop_areas()
    areas = []
    for area in ShopArea.objects.order_by('seq', 'id'):
        areas.append(board_snapshot(area))
    return render(request, 'cnc/mobile/board_index.html', {'areas': areas})


@login_required
def board_area(request, pk):
    from cnc.boards import board_snapshot, ensure_shop_areas
    ensure_shop_areas()
    area = get_object_or_404(ShopArea, pk=pk)
    snapshot = board_snapshot(area)
    snapshot['wall'] = request.GET.get('wall') == '1'
    snapshot['areas'] = ShopArea.objects.order_by('seq', 'id')
    return render(request, 'cnc/mobile/board.html', snapshot)


@login_required
def report_index(request):
    return render(request, 'cnc/mobile/report_index.html', {'reports': REPORTS})


@login_required
def report(request, name):
    titles = dict(REPORTS)
    if name not in titles:
        return redirect('cnc_reports')
    context = {'title': titles[name], 'name': name}
    if name == 'progress':
        context['rows'] = reports.progress_rows()
    elif name == 'due':
        context['rows'] = reports.due_rows()
    elif name == 'machine':
        context['rows'] = reports.machine_rows()
    elif name == 'quality':
        context['quality'] = reports.quality_rows()
    elif name == 'operator':
        context['rows'] = reports.operator_rows()
    elif name == 'outsource':
        context['rows'] = reports.outsource_rows()
    elif name == 'tool':
        context['rows'] = reports.tool_rows()
    return render(request, 'cnc/mobile/report.html', context)
