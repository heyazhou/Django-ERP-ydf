# coding=utf-8
import datetime
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone

from common import generic

MACHINE_TYPES = (
    ('MC', '加工中心'),
    ('LATHE', '车床'),
    ('MILL', '铣床'),
    ('GRIND', '磨床'),
    ('DRILL', '钻床'),
    ('WIRE', '线切割'),
    ('EDM', '电火花'),
    ('SAW', '锯床'),
    ('BENCH', '钳工'),
    ('ASSEM', '装配'),
    ('PROG', '编程'),
    ('SETUP', '调机'),
    ('MANUAL', '手动设备'),
    ('QC', '检验'),
    ('PACK', '包装'),
    ('OUT', '外协'),
)

MACHINE_STATUS = (
    ('idle', '空闲'),
    ('run', '加工中'),
    ('down', '故障'),
    ('maintain', '保养'),
    ('off', '停机'),
)

WO_STATUS = (
    ('draft', '草稿'),
    ('released', '已下达'),
    ('running', '加工中'),
    ('done', '已完工'),
    ('closed', '已关闭'),
    ('cancelled', '已取消'),
)

OP_STATUS = (
    ('wait', '未就绪'),
    ('ready', '可开工'),
    ('running', '加工中'),
    ('done', '已完工'),
    ('out', '外协中'),
)

SCRAP_REASONS = (
    ('size', '尺寸超差'),
    ('setup', '装夹不当'),
    ('tool', '刀具崩刃'),
    ('program', '程序错误'),
    ('material', '材料缺陷'),
    ('other', '其他'),
)

QC_KIND = (
    ('first', '首件'),
    ('patrol', '巡检'),
    ('final', '终检'),
)

QC_RESULT = (
    ('pass', '合格'),
    ('fail', '不合格'),
    ('concession', '让步接收'),
)

LOT_STATUS = (
    ('in', '在库'),
    ('issued', '已发料'),
    ('wip', '在制'),
    ('done', '已入库'),
)

OS_STATUS = (
    ('draft', '草稿'),
    ('sent', '已发出'),
    ('back', '已回厂'),
    ('closed', '已关闭'),
)


class Tracked(generic.BO):
    """带二维码身份的业务对象。扫码地址由令牌拼出，不把电脑地址写死在数据库里。"""

    code = models.CharField('编号', max_length=20, blank=True, null=True)
    qr_token = models.CharField('二维码', max_length=32, unique=True, blank=True, null=True)
    TOKEN_PREFIX = 'XX'

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if kwargs.get('update_fields'):
            return
        changed = []
        if not self.code:
            self.code = '%s%05d' % (self.TOKEN_PREFIX, self.id)
            changed.append('code')
        if not self.qr_token:
            self.qr_token = self.code
            changed.append('qr_token')
        if changed:
            super().save(update_fields=changed)

    @property
    def qr_path(self):
        return '/m/q/%s/' % self.qr_token if self.qr_token else ''


class ShopArea(Tracked):
    """车间里的一块现场。每块区域有自己的看板，贴在该区域的大屏或看板上。"""

    TOKEN_PREFIX = 'AR'
    name = models.CharField('区域', max_length=40)
    seq = models.PositiveIntegerField('顺序', default=10)
    machine_types = models.CharField('承接设备类型', max_length=80, blank=True, default='')
    note = models.CharField('说明', max_length=120, blank=True, default='')

    class Meta:
        verbose_name = '车间区域'
        verbose_name_plural = '车间区域'
        ordering = ['seq', 'id']

    def __unicode__(self):
        return self.name


class Machine(Tracked):
    TOKEN_PREFIX = 'MC'
    name = models.CharField('设备名称', max_length=40)
    machine_type = models.CharField('设备类型', max_length=10, choices=MACHINE_TYPES, default='MC')
    area = models.ForeignKey(
        ShopArea, verbose_name='所在区域', blank=True, null=True,
        related_name='machines', on_delete=models.SET_NULL)
    workshop = models.CharField('车间', max_length=40, blank=True, default='机加车间')
    status = models.CharField('状态', max_length=10, choices=MACHINE_STATUS, default='idle')
    brand = models.CharField('品牌型号', max_length=60, blank=True, default='')
    hour_rate = models.DecimalField('小时费率', max_digits=10, decimal_places=2, default=Decimal('0'))
    photo = models.FileField('照片', upload_to='cnc/machine/', blank=True, null=True)

    class Meta:
        verbose_name = '设备'
        verbose_name_plural = '设备'
        ordering = ['code']

    def __unicode__(self):
        return '%s %s' % (self.code or '', self.name)

    def set_status(self, status, user, summary=''):
        self.status = status
        self.save(update_fields=['status', 'modification'])
        from cnc.qrutil import log_event
        label = dict(MACHINE_STATUS).get(status, status)
        log_event(self.qr_token, 'machine', summary or ('设备改为%s' % label), user)


class Tool(Tracked):
    TOKEN_PREFIX = 'TL'
    name = models.CharField('刀具名称', max_length=40)
    spec = models.CharField('规格', max_length=60, blank=True, default='')
    life_minutes = models.PositiveIntegerField('额定寿命(分钟)', default=0)
    used_minutes = models.PositiveIntegerField('已用(分钟)', default=0)
    machine = models.ForeignKey(Machine, verbose_name='所在设备', blank=True, null=True, on_delete=models.SET_NULL)
    status = models.CharField('状态', max_length=10, default='stock', choices=(
        ('stock', '在库'),
        ('using', '在用'),
        ('scrap', '报废'),
    ))
    photo = models.FileField('照片', upload_to='cnc/tool/', blank=True, null=True)

    class Meta:
        verbose_name = '刀具'
        verbose_name_plural = '刀具'

    def __unicode__(self):
        return '%s %s' % (self.code or '', self.name)

    @property
    def life_ratio(self):
        if not self.life_minutes:
            return None
        return Decimal(self.used_minutes) / Decimal(self.life_minutes)


class Fixture(Tracked):
    TOKEN_PREFIX = 'FX'
    name = models.CharField('夹具名称', max_length=40)
    spec = models.CharField('规格', max_length=60, blank=True, default='')
    status = models.CharField('状态', max_length=10, default='stock', choices=(
        ('stock', '在库'),
        ('using', '在用'),
        ('repair', '维修'),
    ))
    photo = models.FileField('照片', upload_to='cnc/fixture/', blank=True, null=True)

    class Meta:
        verbose_name = '夹具'
        verbose_name_plural = '夹具'

    def __unicode__(self):
        return '%s %s' % (self.code or '', self.name)


class Process(models.Model):
    """标准工序库，下达工单时可以按它生成工序。"""

    name = models.CharField('工序名称', max_length=40)
    machine_type = models.CharField('设备类型', max_length=10, choices=MACHINE_TYPES, default='MC')
    outsource = models.BooleanField('外协工序', default=False)
    seq = models.PositiveIntegerField('排序', default=0)
    std_minutes = models.DecimalField('单件工时(分钟)', max_digits=8, decimal_places=2, default=Decimal('0'))

    class Meta:
        verbose_name = '标准工序'
        verbose_name_plural = '标准工序'
        ordering = ['seq', 'id']

    def __str__(self):
        return self.name


class Routing(Tracked):
    TOKEN_PREFIX = 'RT'
    name = models.CharField('工艺名称', max_length=60)
    material = models.ForeignKey(
        'basedata.Material', verbose_name='物料', blank=True, null=True, on_delete=models.PROTECT)
    version = models.CharField('版本', max_length=20, default='A')
    is_active = models.BooleanField('启用', default=True)

    class Meta:
        verbose_name = '工艺路线'
        verbose_name_plural = '工艺路线'

    def __unicode__(self):
        return '%s %s' % (self.code or '', self.name)


class RoutingStep(models.Model):
    routing = models.ForeignKey(Routing, verbose_name='工艺路线', related_name='steps', on_delete=models.CASCADE)
    seq = models.PositiveIntegerField('顺序', default=10)
    name = models.CharField('工序', max_length=40)
    machine_type = models.CharField('设备类型', max_length=10, choices=MACHINE_TYPES, default='MC')
    setup_min = models.DecimalField('准备工时(分钟)', max_digits=8, decimal_places=2, default=Decimal('0'))
    unit_min = models.DecimalField('单件工时(分钟)', max_digits=8, decimal_places=2, default=Decimal('0'))
    outsource = models.BooleanField('外协', default=False)
    note = models.CharField('说明', max_length=120, blank=True, default='')

    class Meta:
        verbose_name = '工艺工序'
        verbose_name_plural = '工艺工序'
        ordering = ['seq', 'id']

    def __str__(self):
        return '%s %s' % (self.seq, self.name)


class WorkOrder(Tracked):
    TOKEN_PREFIX = 'WO'
    title = models.CharField('图号/零件', max_length=80)
    material = models.ForeignKey(
        'basedata.Material', verbose_name='物料', blank=True, null=True,
        related_name='cnc_orders', on_delete=models.PROTECT)
    customer = models.ForeignKey(
        'basedata.Partner', verbose_name='客户', blank=True, null=True,
        limit_choices_to={'partner_type': 'C'}, on_delete=models.PROTECT)
    sale_order = models.ForeignKey(
        'sale.SaleOrder', verbose_name='销售订单', blank=True, null=True, on_delete=models.SET_NULL)
    routing = models.ForeignKey(
        Routing, verbose_name='工艺路线', blank=True, null=True, on_delete=models.SET_NULL)
    qty = models.DecimalField('计划数量', max_digits=12, decimal_places=3, default=Decimal('1'))
    due_date = models.DateField('交期', blank=True, null=True)
    priority = models.PositiveSmallIntegerField('优先级', default=3)
    blank_spec = models.CharField('毛坯', max_length=80, blank=True, default='')
    drawing_no = models.CharField('图号', max_length=40, blank=True, default='')
    status = models.CharField('状态', max_length=12, choices=WO_STATUS, default='draft')
    released_at = models.DateTimeField('下达时间', blank=True, null=True)
    finished_at = models.DateTimeField('完工时间', blank=True, null=True)

    class Meta:
        verbose_name = '生产工单'
        verbose_name_plural = '生产工单'
        ordering = ['-id']

    def __unicode__(self):
        return '%s %s' % (self.code or '', self.title)

    def progress_text(self):
        total = self.operations.count()
        done = self.operations.filter(status='done').count()
        return '%s/%s' % (done, total)

    def is_late(self):
        if not self.due_date or self.status in ('done', 'closed', 'cancelled'):
            return False
        return self.due_date < datetime.date.today()

    def release(self, user):
        if self.status != 'draft':
            raise ValueError('只有草稿可以下达')
        if not self.operations.exists() and self.routing_id:
            for step in self.routing.steps.all():
                WorkOperation.objects.create(
                    work_order=self,
                    seq=step.seq,
                    name=step.name,
                    machine_type=step.machine_type,
                    setup_min=step.setup_min,
                    unit_min=step.unit_min,
                    outsource=step.outsource,
                    plan_qty=self.qty,
                    note=step.note,
                )
        if not self.operations.exists():
            raise ValueError('请先添加工序，或选择已有工艺路线')
        for operation in self.operations.all():
            if not operation.plan_qty:
                operation.plan_qty = self.qty
                operation.save(update_fields=['plan_qty'])
        first = self.operations.order_by('seq', 'id').first()
        now = timezone.now()
        self.operations.exclude(pk=first.pk).update(status='wait')
        first.status = 'out' if first.outsource else 'ready'
        first.save(update_fields=['status'])
        self.status = 'released'
        self.released_at = now
        self.save(update_fields=['status', 'released_at', 'modification'])
        self.refresh_status()
        from cnc.qrutil import log_event
        log_event(self.qr_token, 'release', '下达工单 %s' % self.code, user)

    def refresh_status(self):
        ops = list(self.operations.all())
        if not ops:
            return
        if all(item.status == 'done' for item in ops):
            self.status = 'done'
            self.finished_at = timezone.now()
            self.save(update_fields=['status', 'finished_at', 'modification'])
            return
        if any(item.status in ('running', 'out', 'done') for item in ops):
            if self.status not in ('running', 'closed', 'cancelled'):
                self.status = 'running'
                self.save(update_fields=['status', 'modification'])


class WorkOperation(Tracked):
    TOKEN_PREFIX = 'OP'
    work_order = models.ForeignKey(WorkOrder, verbose_name='工单', related_name='operations', on_delete=models.CASCADE)
    seq = models.PositiveIntegerField('顺序', default=10)
    name = models.CharField('工序', max_length=40)
    machine_type = models.CharField('设备类型', max_length=10, choices=MACHINE_TYPES, default='MC')
    machine = models.ForeignKey(Machine, verbose_name='设备', blank=True, null=True, on_delete=models.SET_NULL)
    operator = models.ForeignKey(User, verbose_name='操作者', blank=True, null=True, on_delete=models.SET_NULL)
    plan_qty = models.DecimalField('计划数量', max_digits=12, decimal_places=3, default=Decimal('0'))
    good_qty = models.DecimalField('合格数量', max_digits=12, decimal_places=3, default=Decimal('0'))
    scrap_qty = models.DecimalField('报废数量', max_digits=12, decimal_places=3, default=Decimal('0'))
    setup_min = models.DecimalField('准备工时(分钟)', max_digits=8, decimal_places=2, default=Decimal('0'))
    unit_min = models.DecimalField('单件工时(分钟)', max_digits=8, decimal_places=2, default=Decimal('0'))
    outsource = models.BooleanField('外协', default=False)
    program = models.ForeignKey(
        'NcProgram', verbose_name='数控程序', blank=True, null=True, on_delete=models.SET_NULL)
    setup_note = models.CharField('调机说明', max_length=200, blank=True, default='')
    status = models.CharField('状态', max_length=12, choices=OP_STATUS, default='wait')
    note = models.CharField('说明', max_length=120, blank=True, default='')
    started_at = models.DateTimeField('开工时间', blank=True, null=True)
    finished_at = models.DateTimeField('完工时间', blank=True, null=True)

    class Meta:
        verbose_name = '工序任务'
        verbose_name_plural = '工序任务'
        ordering = ['work_order', 'seq', 'id']

    def __unicode__(self):
        return '%s-%s %s' % (self.work_order.code or '', self.seq, self.name)

    def can_start(self):
        return self.status in ('ready', 'running')

    def start(self, user, machine=None):
        if self.status not in ('ready', 'running'):
            raise ValueError('当前工序还不能开工')
        if self.machine_type == 'PROG':
            machine = None
        elif machine is not None:
            self.check_machine(machine)
        self.status = 'running'
        self.operator = user if getattr(user, 'is_authenticated', False) else self.operator
        if machine:
            self.machine = machine
            machine.set_status('run', user, '开工 %s' % self)
        if not self.started_at:
            self.started_at = timezone.now()
        self.save()
        self.work_order.refresh_status()
        from cnc.qrutil import log_event
        log_event(self.qr_token, 'start', '开工 %s' % self, user)
        log_event(self.work_order.qr_token, 'start', '工序开工 %s' % self.name, user)

    def check_machine(self, machine):
        if machine.status in ('down', 'maintain'):
            raise ValueError('这台设备正在维修或保养，不能开工')
        if self.machine_type == 'SETUP':
            if machine.machine_type != 'MC':
                raise ValueError('调机请选择加工中心')
            return
        if self.machine_type in ('QC', 'PACK', 'OUT', 'SAW'):
            return
        if machine.machine_type != self.machine_type:
            raise ValueError('这台设备不能做这道工序')

    def report(self, user, good, scrap, reason, minutes, note=''):
        if self.status not in ('ready', 'running'):
            raise ValueError('当前工序不能报工')
        if self.machine_type in ('PROG', 'SETUP') and not self.program_id:
            raise ValueError('这道工序要先指定数控程序')
        good = Decimal(good or 0)
        scrap = Decimal(scrap or 0)
        minutes = Decimal(minutes or 0)
        if good < 0 or scrap < 0 or minutes < 0:
            raise ValueError('数量不能为负')
        from django.db import transaction
        with transaction.atomic():
            if self.status == 'ready':
                self.start(user, self.machine)
            self.good_qty = (self.good_qty or 0) + good
            self.scrap_qty = (self.scrap_qty or 0) + scrap
            self.operator = user if getattr(user, 'is_authenticated', False) else self.operator
            self.save()
            JobLog.objects.create(
                operation=self,
                user=self.operator,
                machine=self.machine,
                good_qty=good,
                scrap_qty=scrap,
                scrap_reason=reason or '',
                minutes=minutes,
                note=note or '',
            )
            from cnc.qrutil import log_event
            log_event(
                self.qr_token, 'report',
                '报工 合格%s 报废%s' % (good, scrap), user)
            if self.plan_qty and self.good_qty >= self.plan_qty:
                self.finish(user)

    def finish(self, user):
        if self.status == 'done':
            return
        if self.status not in ('ready', 'running'):
            raise ValueError('当前工序还不能完工')
        if self.machine_type in ('PROG', 'SETUP') and not self.program_id:
            raise ValueError('这道工序要先指定数控程序')
        if self.machine_type == 'QC':
            from quality.services import operation_cleared
            if not operation_cleared(self):
                raise ValueError('检验工序要先有合格或让步接收的检验记录')
        self.status = 'done'
        self.finished_at = timezone.now()
        if self.machine_id and self.machine.status == 'run':
            still = WorkOperation.objects.filter(machine=self.machine, status='running').exclude(pk=self.pk).exists()
            maintaining = MaintainOrder.objects.filter(machine=self.machine, status='doing').exists()
            if not still and not maintaining:
                self.machine.status = 'idle'
                self.machine.save(update_fields=['status', 'modification'])
        self.save()
        nxt = self.work_order.operations.filter(seq__gt=self.seq).order_by('seq', 'id').first()
        if nxt and nxt.status == 'wait':
            nxt.status = 'out' if nxt.outsource else 'ready'
            nxt.save(update_fields=['status'])
        self.work_order.refresh_status()
        from cnc.qrutil import log_event
        log_event(self.qr_token, 'finish', '工序完工 %s' % self.name, user)


class JobLog(models.Model):
    operation = models.ForeignKey(WorkOperation, verbose_name='工序', related_name='logs', on_delete=models.CASCADE)
    user = models.ForeignKey(User, verbose_name='报工人', blank=True, null=True, on_delete=models.SET_NULL)
    machine = models.ForeignKey(Machine, verbose_name='设备', blank=True, null=True, on_delete=models.SET_NULL)
    good_qty = models.DecimalField('合格', max_digits=12, decimal_places=3, default=Decimal('0'))
    scrap_qty = models.DecimalField('报废', max_digits=12, decimal_places=3, default=Decimal('0'))
    scrap_reason = models.CharField('报废原因', max_length=20, blank=True, default='', choices=SCRAP_REASONS)
    minutes = models.DecimalField('工时(分钟)', max_digits=8, decimal_places=2, default=Decimal('0'))
    note = models.CharField('备注', max_length=120, blank=True, default='')
    created = models.DateTimeField('时间', auto_now_add=True)

    class Meta:
        verbose_name = '报工记录'
        verbose_name_plural = '报工记录'
        ordering = ['-id']

    def __str__(self):
        return '%s %s' % (self.operation, self.created)


class Inspection(Tracked):
    TOKEN_PREFIX = 'QC'
    work_order = models.ForeignKey(WorkOrder, verbose_name='工单', on_delete=models.CASCADE)
    operation = models.ForeignKey(
        WorkOperation, verbose_name='工序', blank=True, null=True, on_delete=models.SET_NULL)
    kind = models.CharField('检验类型', max_length=12, choices=QC_KIND, default='first')
    result = models.CharField('结论', max_length=12, choices=QC_RESULT, default='pass')
    check_qty = models.DecimalField('检验数量', max_digits=12, decimal_places=3, default=Decimal('0'))
    fail_qty = models.DecimalField('不合格数量', max_digits=12, decimal_places=3, default=Decimal('0'))
    inspector = models.ForeignKey(User, verbose_name='检验员', blank=True, null=True, on_delete=models.SET_NULL)
    note = models.CharField('说明', max_length=200, blank=True, default='')

    class Meta:
        verbose_name = '质检单'
        verbose_name_plural = '质检单'
        ordering = ['-id']

    def __unicode__(self):
        return '%s %s' % (self.code or '', self.get_kind_display())


class MaterialLot(Tracked):
    TOKEN_PREFIX = 'LT'
    material = models.ForeignKey(
        'basedata.Material', verbose_name='物料', blank=True, null=True, on_delete=models.PROTECT)
    work_order = models.ForeignKey(
        WorkOrder, verbose_name='工单', blank=True, null=True, on_delete=models.SET_NULL)
    heat_no = models.CharField('炉批号', max_length=40, blank=True, default='')
    qty = models.DecimalField('数量', max_digits=12, decimal_places=3, default=Decimal('0'))
    warehouse = models.ForeignKey(
        'basedata.Warehouse', verbose_name='仓库', blank=True, null=True, on_delete=models.SET_NULL)
    status = models.CharField('状态', max_length=12, choices=LOT_STATUS, default='in')

    class Meta:
        verbose_name = '物料批次'
        verbose_name_plural = '物料批次'

    def __unicode__(self):
        return '%s %s' % (self.code or '', self.heat_no or self.material or '')


class NcProgram(Tracked):
    TOKEN_PREFIX = 'NC'
    name = models.CharField('程序名', max_length=60)
    material = models.ForeignKey(
        'basedata.Material', verbose_name='物料', blank=True, null=True, on_delete=models.PROTECT)
    operation_name = models.CharField('对应工序', max_length=40, blank=True, default='')
    version = models.CharField('版本', max_length=20, default='A')
    program_file = models.FileField('程序文件', upload_to='cnc/program/', blank=True, null=True)
    note = models.CharField('说明', max_length=120, blank=True, default='')

    class Meta:
        verbose_name = '数控程序'
        verbose_name_plural = '数控程序'

    def __unicode__(self):
        return '%s %s' % (self.code or '', self.name)


class Drawing(Tracked):
    TOKEN_PREFIX = 'DR'
    name = models.CharField('图纸名称', max_length=80)
    drawing_no = models.CharField('图号', max_length=40, blank=True, default='')
    version = models.CharField('版本', max_length=20, default='A')
    material = models.ForeignKey(
        'basedata.Material', verbose_name='物料', blank=True, null=True, on_delete=models.PROTECT)
    work_order = models.ForeignKey(
        WorkOrder, verbose_name='工单', blank=True, null=True, on_delete=models.SET_NULL)
    drawing_file = models.FileField('二维图纸', upload_to='cnc/drawing/', blank=True, null=True)
    model_file = models.FileField('三维模型', upload_to='cnc/model/', blank=True, null=True)
    photo = models.FileField('照片', upload_to='cnc/drawing/', blank=True, null=True)

    class Meta:
        verbose_name = '图纸'
        verbose_name_plural = '图纸'

    def __unicode__(self):
        return '%s %s' % (self.drawing_no or self.code or '', self.name)


class OutsourceOrder(Tracked):
    TOKEN_PREFIX = 'OS'
    work_order = models.ForeignKey(WorkOrder, verbose_name='工单', on_delete=models.CASCADE)
    operation = models.ForeignKey(
        WorkOperation, verbose_name='工序', blank=True, null=True, on_delete=models.SET_NULL)
    vendor = models.ForeignKey(
        'basedata.Partner', verbose_name='外协厂', blank=True, null=True,
        limit_choices_to={'partner_type': 'S'}, on_delete=models.PROTECT)
    qty = models.DecimalField('数量', max_digits=12, decimal_places=3, default=Decimal('0'))
    status = models.CharField('状态', max_length=12, choices=OS_STATUS, default='draft')
    sent_at = models.DateTimeField('发出时间', blank=True, null=True)
    back_at = models.DateTimeField('回厂时间', blank=True, null=True)
    note = models.CharField('说明', max_length=120, blank=True, default='')

    class Meta:
        verbose_name = '外协单'
        verbose_name_plural = '外协单'
        ordering = ['-id']

    def __unicode__(self):
        return '%s' % (self.code or self.pk)

    def send_out(self, user):
        if self.status != 'draft':
            raise ValueError('这张外协单已经发出')
        self.status = 'sent'
        self.sent_at = timezone.now()
        self.save(update_fields=['status', 'sent_at', 'modification'])
        if self.operation_id and self.operation.status in ('ready', 'running'):
            self.operation.status = 'out'
            self.operation.save(update_fields=['status'])
            self.operation.work_order.refresh_status()
        from cnc.qrutil import log_event
        log_event(self.qr_token, 'outsource', '外协发出', user)

    def receive(self, user):
        if self.status != 'sent':
            raise ValueError('外协还没发出，不能回厂')
        self.status = 'back'
        self.back_at = timezone.now()
        self.save(update_fields=['status', 'back_at', 'modification'])
        if self.operation_id and self.operation.status == 'out':
            self.operation.status = 'ready'
            self.operation.save(update_fields=['status'])
            self.operation.work_order.refresh_status()
        from cnc.qrutil import log_event
        log_event(self.qr_token, 'outsource', '外协回厂', user)


class MaintainOrder(Tracked):
    """设备故障维修或计划保养。开工后设备改为故障或保养，完成后恢复空闲。"""

    TOKEN_PREFIX = 'MN'
    KIND = (
        ('repair', '维修'),
        ('maintain', '保养'),
    )
    STATUS = (
        ('open', '待处理'),
        ('doing', '进行中'),
        ('done', '已完成'),
        ('cancelled', '已取消'),
    )
    machine = models.ForeignKey(Machine, verbose_name='设备', on_delete=models.PROTECT)
    kind = models.CharField('类型', max_length=12, choices=KIND, default='repair')
    title = models.CharField('项目', max_length=80)
    symptom = models.CharField('现象', max_length=200, blank=True, default='')
    status = models.CharField('状态', max_length=12, choices=STATUS, default='open')
    plan_date = models.DateField('计划日期', blank=True, null=True)
    technician = models.ForeignKey(
        User, verbose_name='维修人', blank=True, null=True, on_delete=models.SET_NULL)
    work_done = models.CharField('处理内容', max_length=200, blank=True, default='')
    spare = models.CharField('更换备件', max_length=120, blank=True, default='')
    note = models.CharField('说明', max_length=120, blank=True, default='')
    started_at = models.DateTimeField('开工时间', blank=True, null=True)
    finished_at = models.DateTimeField('完工时间', blank=True, null=True)

    class Meta:
        verbose_name = '设备维修保养'
        verbose_name_plural = '设备维修保养'
        ordering = ['-id']

    def __unicode__(self):
        return '%s %s' % (self.code or '', self.title)

    def start(self, user):
        if self.status not in ('open', 'doing'):
            raise ValueError('这张单已经结束')
        if WorkOperation.objects.filter(machine=self.machine, status='running').exists():
            raise ValueError('这台设备上还有未完工的工序，不能开始维修保养')
        self.status = 'doing'
        self.technician = user if getattr(user, 'is_authenticated', False) else self.technician
        if not self.started_at:
            self.started_at = timezone.now()
        self.save()
        target = 'down' if self.kind == 'repair' else 'maintain'
        self.machine.set_status(target, user, '%s开工 %s' % (self.get_kind_display(), self.title))
        from cnc.qrutil import log_event
        log_event(self.qr_token, 'maintain', '%s开工 %s' % (self.get_kind_display(), self.machine), user)

    def finish(self, user, work_done=''):
        if self.status != 'doing':
            raise ValueError('请先开工')
        self.status = 'done'
        self.finished_at = timezone.now()
        self.technician = user if getattr(user, 'is_authenticated', False) else self.technician
        if work_done:
            self.work_done = work_done
        self.save()
        still = MaintainOrder.objects.filter(machine=self.machine, status='doing').exclude(pk=self.pk).exists()
        running = WorkOperation.objects.filter(machine=self.machine, status='running').exists()
        if not still and not running and self.machine.status in ('down', 'maintain'):
            self.machine.set_status('idle', user, '维修保养完成 %s' % self.title)
        from cnc.qrutil import log_event
        log_event(self.qr_token, 'maintain', '完成 %s' % self.title, user)


class DocLink(models.Model):
    """原后台单据的二维码。不改原表结构，用内容类型和主键对应一张码。"""

    content_type = models.ForeignKey(
        'contenttypes.ContentType', verbose_name='单据类型', on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField('单据')
    token = models.CharField('二维码', max_length=40, unique=True)

    class Meta:
        verbose_name = '单据二维码'
        verbose_name_plural = '单据二维码'
        unique_together = (('content_type', 'object_id'),)

    def __str__(self):
        return self.token


class ShopEvent(models.Model):
    token = models.CharField('二维码', max_length=32, db_index=True)
    action = models.CharField('动作', max_length=20)
    summary = models.CharField('内容', max_length=200)
    user = models.ForeignKey(User, verbose_name='人员', blank=True, null=True, on_delete=models.SET_NULL)
    created = models.DateTimeField('时间', auto_now_add=True)

    class Meta:
        verbose_name = '流转记录'
        verbose_name_plural = '流转记录'
        ordering = ['-id']

    def __str__(self):
        return '%s %s' % (self.token, self.summary)


class FaceSample(models.Model):
    """职员人脸样本。基础数据保存照片后，供本地人脸模型训练。"""

    employee = models.ForeignKey(
        'basedata.Employee', verbose_name='职员', related_name='faces', on_delete=models.CASCADE)
    photo = models.FileField('人脸照片', upload_to='face/')
    feature = models.TextField('特征', blank=True, default='')
    origin = models.CharField('来源', max_length=12, blank=True, default='train')
    created = models.DateTimeField('时间', auto_now_add=True)

    class Meta:
        verbose_name = '人脸'
        verbose_name_plural = '人脸'
        ordering = ['-id']

    def __str__(self):
        return '%s' % self.employee


class ObjectSample(models.Model):
    """物料外观样本。基础数据保存照片后，供本地物体模型训练。"""

    material = models.ForeignKey(
        'basedata.Material', verbose_name='物料', related_name='object_samples', on_delete=models.CASCADE)
    photo = models.FileField('物体照片', upload_to='object/')
    feature = models.TextField('特征', blank=True, default='')
    origin = models.CharField('来源', max_length=12, blank=True, default='train')
    created = models.DateTimeField('时间', auto_now_add=True)

    class Meta:
        verbose_name = '物体样本'
        verbose_name_plural = '物体样本'
        ordering = ['-id']

    def __str__(self):
        return '%s' % self.material


from cnc.assembly import (  # noqa: E402
    AssemblyBom, AssemblyBomLine, AssemblyFit, AssemblyOrder, AssemblyPart, AssemblyUnit,
)
