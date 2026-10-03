from django.contrib import admin
from django.contrib import messages
from django.utils.html import format_html

from common import generic
from cnc import models


class CncAdmin(generic.BOAdmin):
    exclude = ['creator', 'modifier', 'creation', 'modification', 'begin', 'end', 'qr_token']
    readonly_fields = ('qr_preview',)

    def qr_preview(self, obj):
        if not obj or not obj.pk or not obj.qr_token:
            return '保存后生成二维码'
        return format_html(
            '<img src="/m/qr/{}/" alt="二维码" width="180" height="180">'
            '<div><a href="/m/q/{}/">手机打开</a></div>',
            obj.qr_token, obj.qr_token,
        )
    qr_preview.short_description = '二维码'


class RoutingStepInline(admin.TabularInline):
    model = models.RoutingStep
    extra = 1


class WorkOperationInline(admin.TabularInline):
    model = models.WorkOperation
    extra = 1
    exclude = ['creator', 'modifier', 'creation', 'modification', 'begin', 'end', 'qr_token', 'operator', 'code']
    readonly_fields = ('good_qty', 'scrap_qty', 'status')


@admin.register(models.ShopArea)
class ShopAreaAdmin(CncAdmin):
    CODE_PREFIX = 'AR'
    list_display = ('code', 'name', 'seq', 'machine_types', 'note')
    list_editable = ('seq',)
    search_fields = ('code', 'name')


@admin.register(models.Machine)
class MachineAdmin(CncAdmin):
    CODE_PREFIX = 'MC'
    list_display = ('code', 'name', 'machine_type', 'area', 'workshop', 'status', 'hour_rate')
    list_filter = ('machine_type', 'status', 'workshop', 'area')
    search_fields = ('code', 'name', 'brand')


@admin.register(models.Tool)
class ToolAdmin(CncAdmin):
    CODE_PREFIX = 'TL'
    list_display = ('code', 'name', 'spec', 'life_minutes', 'used_minutes', 'machine', 'status')
    list_filter = ('status',)
    search_fields = ('code', 'name', 'spec')
    raw_id_fields = ('machine',)


@admin.register(models.Fixture)
class FixtureAdmin(CncAdmin):
    CODE_PREFIX = 'FX'
    list_display = ('code', 'name', 'spec', 'status')
    search_fields = ('code', 'name')


@admin.register(models.Process)
class ProcessAdmin(admin.ModelAdmin):
    list_display = ('name', 'seq', 'machine_type', 'outsource', 'std_minutes')
    list_display_links = ('name',)
    list_editable = ('seq', 'std_minutes')


@admin.register(models.Routing)
class RoutingAdmin(CncAdmin):
    CODE_PREFIX = 'RT'
    list_display = ('code', 'name', 'material', 'version', 'is_active')
    search_fields = ('code', 'name')
    raw_id_fields = ('material',)
    inlines = [RoutingStepInline]


@admin.register(models.WorkOrder)
class WorkOrderAdmin(CncAdmin):
    CODE_PREFIX = 'WO'
    list_display = ('code', 'title', 'drawing_no', 'qty', 'due_date', 'status', 'progress', 'late_flag')
    list_filter = ('status',)
    search_fields = ('code', 'title', 'drawing_no')
    raw_id_fields = ('material', 'customer', 'sale_order', 'routing')
    inlines = [WorkOperationInline]
    actions = ['release_selected', 'export_selected_data']

    def progress(self, obj):
        return obj.progress_text()
    progress.short_description = '工序进度'

    def late_flag(self, obj):
        return '延期' if obj.is_late() else ''
    late_flag.short_description = '交期'

    def release_selected(self, request, queryset):
        ok = 0
        for order in queryset:
            try:
                order.release(request.user)
                ok += 1
            except ValueError as exc:
                self.message_user(request, '%s：%s' % (order, exc), level=messages.ERROR)
        if ok:
            self.message_user(request, '已下达 %s 张工单' % ok)
    release_selected.short_description = '下达所选工单'


@admin.register(models.WorkOperation)
class WorkOperationAdmin(CncAdmin):
    CODE_PREFIX = 'OP'
    list_display = ('code', 'work_order', 'seq', 'name', 'machine_type', 'machine', 'program', 'plan_qty', 'good_qty', 'scrap_qty', 'status')
    list_filter = ('status', 'machine_type', 'outsource')
    search_fields = ('code', 'name', 'work_order__code', 'work_order__title', 'program__name')
    raw_id_fields = ('work_order', 'machine', 'operator', 'program')


@admin.register(models.JobLog)
class JobLogAdmin(admin.ModelAdmin):
    list_display = ('created', 'operation', 'user', 'machine', 'good_qty', 'scrap_qty', 'minutes')
    list_filter = ('scrap_reason',)
    date_hierarchy = 'created'


@admin.register(models.Inspection)
class InspectionAdmin(CncAdmin):
    CODE_PREFIX = 'QC'
    list_display = ('code', 'work_order', 'operation', 'kind', 'result', 'check_qty', 'fail_qty', 'inspector')
    list_filter = ('kind', 'result')
    raw_id_fields = ('work_order', 'operation', 'inspector')


@admin.register(models.MaterialLot)
class MaterialLotAdmin(CncAdmin):
    CODE_PREFIX = 'LT'
    list_display = ('code', 'material', 'heat_no', 'qty', 'warehouse', 'work_order', 'status')
    list_filter = ('status',)
    raw_id_fields = ('material', 'work_order', 'warehouse')


@admin.register(models.NcProgram)
class NcProgramAdmin(CncAdmin):
    CODE_PREFIX = 'NC'
    list_display = ('code', 'name', 'operation_name', 'version', 'material')
    search_fields = ('code', 'name', 'operation_name')
    raw_id_fields = ('material',)


@admin.register(models.Drawing)
class DrawingAdmin(CncAdmin):
    CODE_PREFIX = 'DR'
    list_display = ('code', 'drawing_no', 'name', 'version', 'work_order')
    search_fields = ('code', 'drawing_no', 'name')
    raw_id_fields = ('material', 'work_order')


@admin.register(models.OutsourceOrder)
class OutsourceOrderAdmin(CncAdmin):
    CODE_PREFIX = 'OS'
    list_display = ('code', 'work_order', 'operation', 'vendor', 'qty', 'status', 'sent_at', 'back_at')
    list_filter = ('status',)
    raw_id_fields = ('work_order', 'operation', 'vendor')
    actions = ['mark_sent', 'mark_back']

    def mark_sent(self, request, queryset):
        for item in queryset:
            item.send_out(request.user)
        self.message_user(request, '已标记发出')
    mark_sent.short_description = '外协发出'

    def mark_back(self, request, queryset):
        for item in queryset:
            item.receive(request.user)
        self.message_user(request, '已标记回厂')
    mark_back.short_description = '外协回厂'


class AssemblyBomLineInline(admin.TabularInline):
    model = models.AssemblyBomLine
    extra = 1
    raw_id_fields = ('material',)


class AssemblyPartInline(admin.TabularInline):
    model = models.AssemblyPart
    extra = 0
    raw_id_fields = ('material',)
    fields = ('seq', 'material', 'per_qty', 'need_qty', 'issued_qty', 'lot_no', 'critical', 'status', 'note')
    readonly_fields = ('per_qty', 'need_qty', 'status')


class AssemblyUnitInline(admin.TabularInline):
    model = models.AssemblyUnit
    extra = 0
    fields = ('seq', 'code', 'status', 'station', 'assembler', 'result', 'note')
    readonly_fields = ('code', 'status')


class AssemblyFitInline(admin.TabularInline):
    model = models.AssemblyFit
    extra = 1
    raw_id_fields = ('material',)


@admin.register(models.AssemblyBom)
class AssemblyBomAdmin(CncAdmin):
    CODE_PREFIX = 'AB'
    list_display = ('code', 'name', 'product', 'version', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('code', 'name')
    raw_id_fields = ('product',)
    inlines = [AssemblyBomLineInline]


@admin.register(models.AssemblyOrder)
class AssemblyOrderAdmin(CncAdmin):
    CODE_PREFIX = 'AO'
    list_display = (
        'code', 'title', 'product', 'qty', 'due_date', 'station', 'status',
        'kit_progress', 'unit_progress', 'part_process',
    )
    list_filter = ('status',)
    search_fields = ('code', 'title', 'product__name', 'parts__material__name')
    raw_id_fields = ('bom', 'product', 'customer')
    readonly_fields = ('qr_preview', 'status', 'component_process')
    inlines = [AssemblyPartInline, AssemblyUnitInline]
    actions = ['release_selected', 'export_selected_data']

    def kit_progress(self, obj):
        return obj.kit_text()
    kit_progress.short_description = '齐套'

    def unit_progress(self, obj):
        return obj.unit_text()
    unit_progress.short_description = '合格套数'

    def part_process(self, obj):
        return obj.process_brief()
    part_process.short_description = '零部件工序'

    def component_process(self, obj):
        if not obj or not obj.pk:
            return '保存后可查询零部件工序'
        rows = []
        for item in obj.component_jobs():
            if not item['jobs']:
                rows.append(format_html(
                    '<tr><td>{}</td><td colspan="4">无生产工单</td></tr>',
                    item['material'],
                ))
                continue
            for job in item['jobs']:
                order = job['order']
                if not job['operations']:
                    rows.append(format_html(
                        '<tr><td>{}</td><td><a href="/admin/cnc/workorder/{}/change/">{}</a></td>'
                        '<td colspan="3">{}，还没有工序</td></tr>',
                        item['material'], order.pk, order.code, order.get_status_display(),
                    ))
                for operation in job['operations']:
                    rows.append(format_html(
                        '<tr><td>{}</td><td><a href="/admin/cnc/workorder/{}/change/">{} {}</a></td>'
                        '<td>{} {}</td><td>{}</td><td>{}/{}</td></tr>',
                        item['material'], order.pk, order.code, order.title,
                        operation.seq, operation.name, operation.get_status_display(),
                        operation.good_qty, operation.plan_qty,
                    ))
        if not rows:
            return '这张装配单还没有零部件'
        body = format_html('{}' * len(rows), *rows)
        return format_html(
            '<table style="width:100%"><thead><tr><th>零件</th><th>生产工单</th><th>工序</th>'
            '<th>状态</th><th>合格/计划</th></tr></thead><tbody>{}</tbody></table>',
            body,
        )
    component_process.short_description = '零部件工序状态'

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'station':
            kwargs['queryset'] = models.Machine.objects.filter(machine_type='ASSEM')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def release_selected(self, request, queryset):
        ok = 0
        for order in queryset:
            try:
                order.release(request.user)
                ok += 1
            except ValueError as exc:
                self.message_user(request, '%s：%s' % (order, exc), level=messages.ERROR)
        if ok:
            self.message_user(request, '已下达 %s 张装配工单' % ok)
    release_selected.short_description = '下达所选装配工单'


@admin.register(models.AssemblyUnit)
class AssemblyUnitAdmin(CncAdmin):
    CODE_PREFIX = 'AU'
    list_display = ('code', 'order', 'seq', 'station', 'assembler', 'status', 'result')
    list_filter = ('status', 'result')
    search_fields = ('code', 'order__code', 'order__title')
    raw_id_fields = ('order', 'assembler')
    readonly_fields = ('qr_preview', 'status')
    inlines = [AssemblyFitInline]


@admin.register(models.AssemblyPart)
class AssemblyPartAdmin(admin.ModelAdmin):
    list_display = ('order', 'material', 'need_qty', 'issued_qty', 'lot_no', 'critical', 'status')
    list_filter = ('status', 'critical')
    search_fields = ('order__code', 'order__title', 'material__name', 'lot_no')
    raw_id_fields = ('order', 'material')


@admin.register(models.MaintainOrder)
class MaintainOrderAdmin(CncAdmin):
    CODE_PREFIX = 'MN'
    list_display = ('code', 'machine', 'kind', 'title', 'status', 'plan_date', 'technician')
    list_filter = ('kind', 'status')
    search_fields = ('code', 'title', 'machine__name', 'symptom')
    raw_id_fields = ('machine', 'technician')
    readonly_fields = ('qr_preview', 'status')
    actions = ['start_selected', 'finish_selected']

    def start_selected(self, request, queryset):
        ok = 0
        for item in queryset:
            try:
                item.start(request.user)
                ok += 1
            except ValueError as exc:
                self.message_user(request, '%s：%s' % (item, exc), level=messages.ERROR)
        if ok:
            self.message_user(request, '已开工 %s 张维修保养单' % ok)
    start_selected.short_description = '开始维修或保养'

    def finish_selected(self, request, queryset):
        ok = 0
        for item in queryset:
            try:
                item.finish(request.user)
                ok += 1
            except ValueError as exc:
                self.message_user(request, '%s：%s' % (item, exc), level=messages.ERROR)
        if ok:
            self.message_user(request, '已完成 %s 张维修保养单' % ok)
    finish_selected.short_description = '完成维修或保养'


@admin.register(models.ShopEvent)
class ShopEventAdmin(admin.ModelAdmin):
    list_display = ('created', 'token', 'action', 'summary', 'user')
    search_fields = ('token', 'summary')
    date_hierarchy = 'created'
