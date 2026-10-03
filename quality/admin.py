# coding=utf-8
from django.contrib import admin

from cnc.admin import CncAdmin
from quality import models


class StandardItemInline(admin.TabularInline):
    model = models.StandardItem
    extra = 1


class MeasureInline(admin.TabularInline):
    model = models.Measure
    extra = 0


class DefectInline(admin.TabularInline):
    model = models.Defect
    extra = 0


@admin.register(models.ControlPoint)
class ControlPointAdmin(admin.ModelAdmin):
    list_display = ('stage', 'process_name', 'required', 'note')
    list_filter = ('stage', 'required')
    search_fields = ('process_name', 'note')


@admin.register(models.Standard)
class StandardAdmin(CncAdmin):
    CODE_PREFIX = 'QS'
    list_display = ('code', 'name', 'stage', 'process_name', 'material', 'version', 'active')
    list_filter = ('stage', 'active')
    search_fields = ('code', 'name', 'process_name')
    raw_id_fields = ('material',)
    inlines = (StandardItemInline,)


@admin.register(models.StandardItem)
class StandardItemAdmin(admin.ModelAdmin):
    list_display = ('standard', 'seq', 'name', 'nominal', 'lower_limit', 'upper_limit', 'method', 'key_size')
    list_filter = ('key_size',)
    search_fields = ('name', 'standard__name')
    raw_id_fields = ('standard',)


@admin.register(models.CheckRecord)
class CheckRecordAdmin(CncAdmin):
    CODE_PREFIX = 'QM'
    list_display = ('code', 'stage', 'result', 'disposition', 'work_order', 'operation', 'check_qty', 'fail_qty', 'status')
    list_filter = ('stage', 'result', 'status')
    search_fields = ('code', 'note', 'work_order__code', 'operation__name')
    raw_id_fields = ('standard', 'work_order', 'operation', 'lot', 'assembly_unit', 'outsource', 'inspection', 'inspector')
    inlines = (MeasureInline, DefectInline)


@admin.register(models.Measure)
class MeasureAdmin(admin.ModelAdmin):
    list_display = ('record', 'name', 'nominal', 'lower_limit', 'upper_limit', 'measured', 'result', 'key_size')
    list_filter = ('result', 'key_size')
    search_fields = ('name', 'record__code')
    raw_id_fields = ('record',)


@admin.register(models.Defect)
class DefectAdmin(admin.ModelAdmin):
    list_display = ('record', 'qty', 'reason', 'disposition', 'closed', 'note')
    list_filter = ('disposition', 'closed', 'reason')
    search_fields = ('note', 'record__code')
    raw_id_fields = ('record',)
