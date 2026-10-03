# coding=utf-8
from django.contrib.auth.models import User
from django.db import models

from cnc.models import SCRAP_REASONS, Tracked

STAGES = (
    ('incoming', '来料检验'),
    ('first', '首件检验'),
    ('patrol', '巡检'),
    ('process', '工序检验'),
    ('outsource', '外协回厂检验'),
    ('assembly', '装配检验'),
    ('final', '终检'),
    ('ship', '出货检验'),
)

RESULTS = (
    ('pending', '待判定'),
    ('pass', '合格'),
    ('fail', '不合格'),
    ('concession', '让步接收'),
)

DISPOSITIONS = (
    ('', '未处置'),
    ('rework', '返工'),
    ('repair', '返修'),
    ('scrap', '报废'),
    ('concession', '让步接收'),
    ('isolate', '隔离'),
)

METHODS = (
    ('', '未指定'),
    ('caliper', '卡尺'),
    ('micrometer', '千分尺'),
    ('height', '高度尺'),
    ('gauge', '通止规'),
    ('visual', '目视'),
    ('rough', '粗糙度仪'),
    ('other', '其他'),
)


class ControlPoint(models.Model):
    """全流程里必须站住的质量关。"""

    index_weight = 1
    stage = models.CharField('环节', max_length=12, choices=STAGES)
    process_name = models.CharField('工序名称', max_length=40, blank=True, default='', help_text='留空表示这个环节都要检。填写后只针对同名工序')
    required = models.BooleanField('必检', default=True, help_text='工单、批次、外协和装配页面会标出还没完成的必检')
    note = models.CharField('说明', max_length=200, blank=True, default='')

    class Meta:
        verbose_name = '质量控制点'
        verbose_name_plural = '质量控制点'
        ordering = ['id']

    def __str__(self):
        if self.process_name:
            return '%s · %s' % (self.get_stage_display(), self.process_name)
        return self.get_stage_display()


class Standard(Tracked):
    TOKEN_PREFIX = 'QS'
    index_weight = 2
    name = models.CharField('标准名称', max_length=80)
    stage = models.CharField('环节', max_length=12, choices=STAGES, default='process')
    material = models.ForeignKey(
        'basedata.Material', verbose_name='物料', blank=True, null=True, on_delete=models.PROTECT,
        help_text='留空则作为该环节的通用标准')
    process_name = models.CharField('工序名称', max_length=40, blank=True, default='')
    version = models.CharField('版本', max_length=20, default='A')
    active = models.BooleanField('在用', default=True)
    note = models.CharField('说明', max_length=200, blank=True, default='')

    class Meta:
        verbose_name = '检验标准'
        verbose_name_plural = '检验标准'
        ordering = ['-id']

    def __unicode__(self):
        return '%s %s' % (self.code or '', self.name)


class StandardItem(models.Model):
    index_weight = 3
    standard = models.ForeignKey(Standard, verbose_name='检验标准', related_name='items', on_delete=models.CASCADE)
    seq = models.PositiveIntegerField('顺序', default=10)
    name = models.CharField('项目', max_length=60)
    nominal = models.CharField('公称值', max_length=40, blank=True, default='')
    lower_limit = models.CharField('下限', max_length=40, blank=True, default='')
    upper_limit = models.CharField('上限', max_length=40, blank=True, default='')
    unit = models.CharField('单位', max_length=20, blank=True, default='')
    method = models.CharField('检验方法', max_length=20, blank=True, default='')
    key_size = models.BooleanField('关键尺寸', default=False)

    class Meta:
        verbose_name = '检验项目'
        verbose_name_plural = '检验项目'
        ordering = ['standard', 'seq', 'id']

    def __str__(self):
        return self.name


class CheckRecord(Tracked):
    """一次具体检验。实测行从检验标准带出，结论和处置留在本单。"""

    TOKEN_PREFIX = 'QM'
    index_weight = 4
    stage = models.CharField('环节', max_length=12, choices=STAGES, default='process')
    standard = models.ForeignKey(
        Standard, verbose_name='检验标准', blank=True, null=True, on_delete=models.SET_NULL)
    work_order = models.ForeignKey(
        'cnc.WorkOrder', verbose_name='工单', blank=True, null=True,
        related_name='quality_checks', on_delete=models.SET_NULL)
    operation = models.ForeignKey(
        'cnc.WorkOperation', verbose_name='工序', blank=True, null=True,
        related_name='quality_checks', on_delete=models.SET_NULL)
    lot = models.ForeignKey(
        'cnc.MaterialLot', verbose_name='物料批次', blank=True, null=True,
        related_name='quality_checks', on_delete=models.SET_NULL)
    assembly_unit = models.ForeignKey(
        'cnc.AssemblyUnit', verbose_name='装配单件', blank=True, null=True,
        related_name='quality_checks', on_delete=models.SET_NULL)
    outsource = models.ForeignKey(
        'cnc.OutsourceOrder', verbose_name='外协单', blank=True, null=True,
        related_name='quality_checks', on_delete=models.SET_NULL)
    inspection = models.OneToOneField(
        'cnc.Inspection', verbose_name='质检单', blank=True, null=True,
        related_name='quality_check', on_delete=models.SET_NULL)
    check_qty = models.DecimalField('检验数量', max_digits=12, decimal_places=3, default=0)
    fail_qty = models.DecimalField('不合格数量', max_digits=12, decimal_places=3, default=0)
    result = models.CharField('结论', max_length=12, choices=RESULTS, default='pending')
    disposition = models.CharField('处置', max_length=12, choices=DISPOSITIONS, blank=True, default='')
    inspector = models.ForeignKey(
        User, verbose_name='检验员', blank=True, null=True, on_delete=models.SET_NULL)
    status = models.CharField('状态', max_length=12, choices=(('open', '进行中'), ('closed', '已关闭')), default='open')
    note = models.CharField('说明', max_length=200, blank=True, default='')

    class Meta:
        verbose_name = '检验记录'
        verbose_name_plural = '检验记录'
        ordering = ['-id']

    def __unicode__(self):
        return '%s %s' % (self.code or '', self.get_stage_display())


class Measure(models.Model):
    index_weight = 5
    record = models.ForeignKey(CheckRecord, verbose_name='检验记录', related_name='measures', on_delete=models.CASCADE)
    seq = models.PositiveIntegerField('顺序', default=10)
    name = models.CharField('项目', max_length=60)
    nominal = models.CharField('公称值', max_length=40, blank=True, default='')
    lower_limit = models.CharField('下限', max_length=40, blank=True, default='')
    upper_limit = models.CharField('上限', max_length=40, blank=True, default='')
    unit = models.CharField('单位', max_length=20, blank=True, default='')
    method = models.CharField('检验方法', max_length=20, blank=True, default='')
    key_size = models.BooleanField('关键尺寸', default=False)
    measured = models.CharField('实测', max_length=40, blank=True, default='')
    result = models.CharField('判定', max_length=12, choices=(
        ('', '未测'),
        ('pass', '合格'),
        ('fail', '不合格'),
    ), blank=True, default='')

    class Meta:
        verbose_name = '实测'
        verbose_name_plural = '实测'
        ordering = ['record', 'seq', 'id']

    def __str__(self):
        return self.name


class Defect(models.Model):
    index_weight = 6
    record = models.ForeignKey(CheckRecord, verbose_name='检验记录', related_name='defects', on_delete=models.CASCADE)
    qty = models.DecimalField('数量', max_digits=12, decimal_places=3, default=0)
    reason = models.CharField('原因', max_length=20, choices=SCRAP_REASONS, blank=True, default='')
    disposition = models.CharField('处置', max_length=12, choices=DISPOSITIONS, blank=True, default='')
    closed = models.BooleanField('已关闭', default=False)
    note = models.CharField('说明', max_length=200, blank=True, default='')

    class Meta:
        verbose_name = '不合格处置'
        verbose_name_plural = '不合格处置'
        ordering = ['-id']

    def __str__(self):
        return self.get_disposition_display() or '未处置'
