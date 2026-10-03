import datetime
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone

from cnc.models import Machine, Tracked

ASSEMBLY_STATUS = (
    ('draft', '草稿'),
    ('kitting', '待配料'),
    ('assembling', '装配中'),
    ('qc', '待检'),
    ('done', '已完工'),
    ('cancelled', '已取消'),
)

PART_STATUS = (
    ('wait', '待配'),
    ('partial', '部分配料'),
    ('issued', '已齐'),
)

UNIT_STATUS = (
    ('wait', '待装'),
    ('running', '装配中'),
    ('qc', '待检'),
    ('pass', '合格'),
    ('fail', '不合格'),
)

UNIT_RESULT = (
    ('', '未检'),
    ('pass', '合格'),
    ('fail', '不合格'),
    ('concession', '让步接收'),
)


class AssemblyBom(Tracked):
    """一套部件由哪些零件组成。"""

    TOKEN_PREFIX = 'AB'
    name = models.CharField('清单名称', max_length=80)
    product = models.ForeignKey(
        'basedata.Material', verbose_name='总成物料', blank=True, null=True,
        related_name='assembly_boms', on_delete=models.PROTECT)
    version = models.CharField('版本', max_length=20, default='A')
    is_active = models.BooleanField('启用', default=True)
    note = models.CharField('说明', max_length=200, blank=True, default='')

    class Meta:
        verbose_name = '部件装配清单'
        verbose_name_plural = '部件装配清单'
        ordering = ['-id']

    def __unicode__(self):
        return '%s %s' % (self.code or '', self.name)


class AssemblyBomLine(models.Model):
    bom = models.ForeignKey(AssemblyBom, verbose_name='装配清单', related_name='lines', on_delete=models.CASCADE)
    seq = models.PositiveIntegerField('顺序', default=10)
    material = models.ForeignKey('basedata.Material', verbose_name='零件', on_delete=models.PROTECT)
    qty = models.DecimalField('单套用量', max_digits=12, decimal_places=3, default=Decimal('1'))
    critical = models.BooleanField('关键件', default=False)
    note = models.CharField('说明', max_length=120, blank=True, default='')

    class Meta:
        verbose_name = '清单明细'
        verbose_name_plural = '清单明细'
        ordering = ['seq', 'id']

    def __str__(self):
        return '%s × %s' % (self.material, self.qty)


class AssemblyOrder(Tracked):
    """一张部件装配工单：配料、装配、单件检验。"""

    TOKEN_PREFIX = 'AO'
    title = models.CharField('装配任务', max_length=80)
    bom = models.ForeignKey(
        AssemblyBom, verbose_name='装配清单', blank=True, null=True, on_delete=models.PROTECT)
    product = models.ForeignKey(
        'basedata.Material', verbose_name='总成物料', blank=True, null=True,
        related_name='assembly_orders', on_delete=models.PROTECT)
    customer = models.ForeignKey(
        'basedata.Partner', verbose_name='客户', blank=True, null=True,
        limit_choices_to={'partner_type': 'C'}, on_delete=models.PROTECT)
    qty = models.PositiveIntegerField('套数', default=1)
    due_date = models.DateField('交期', blank=True, null=True)
    station = models.ForeignKey(
        Machine, verbose_name='装配工位', blank=True, null=True, on_delete=models.SET_NULL)
    status = models.CharField('状态', max_length=12, choices=ASSEMBLY_STATUS, default='draft')
    note = models.CharField('说明', max_length=200, blank=True, default='')
    released_at = models.DateTimeField('下达时间', blank=True, null=True)
    finished_at = models.DateTimeField('完工时间', blank=True, null=True)

    class Meta:
        verbose_name = '部件装配工单'
        verbose_name_plural = '部件装配工单'
        ordering = ['-id']

    def __unicode__(self):
        return '%s %s' % (self.code or '', self.title)

    def kit_text(self):
        total = self.parts.count()
        ready = self.parts.filter(status='issued').count()
        return '%s/%s' % (ready, total)

    def unit_text(self):
        total = self.units.count()
        passed = self.units.filter(status='pass').count()
        return '%s/%s' % (passed, total)

    def is_late(self):
        if not self.due_date or self.status in ('done', 'cancelled'):
            return False
        return self.due_date < datetime.date.today()

    def component_lines(self):
        parts = list(self.parts.select_related('material'))
        if parts:
            return parts
        if self.bom_id:
            return list(self.bom.lines.select_related('material'))
        return []

    def component_jobs(self):
        """每个零部件对应的生产工单和工序。"""
        from cnc.models import WorkOrder
        lines = self.component_lines()
        material_ids = [line.material_id for line in lines if getattr(line, 'material_id', None)]
        grouped = {}
        if material_ids:
            orders = WorkOrder.objects.filter(material_id__in=material_ids).exclude(
                status='cancelled',
            ).select_related('material').prefetch_related('operations').order_by('-id')
            for order in orders:
                grouped.setdefault(order.material_id, []).append(order)
        rows = []
        for line in lines:
            jobs = []
            for order in grouped.get(line.material_id, []):
                operations = list(order.operations.all())
                jobs.append({
                    'order': order,
                    'operations': operations,
                    'current': _current_operation(operations),
                })
            rows.append({
                'line': line,
                'material': line.material,
                'jobs': jobs,
                'headline': _component_headline(line.material, jobs),
            })
        return rows

    def process_brief(self):
        return '；'.join(item['headline'] for item in self.component_jobs()) or '无零部件'

    def release(self, user):
        if self.status != 'draft':
            raise ValueError('只有草稿可以下达')
        if not self.bom_id or not self.bom.lines.exists():
            raise ValueError('请先选择带明细的装配清单')
        if self.parts.exists() or self.units.exists():
            raise ValueError('这张工单已经展开过')
        if not self.product_id and self.bom.product_id:
            self.product = self.bom.product
        for line in self.bom.lines.all():
            AssemblyPart.objects.create(
                order=self,
                seq=line.seq,
                material=line.material,
                per_qty=line.qty,
                need_qty=line.qty * self.qty,
                critical=line.critical,
                note=line.note,
            )
        for index in range(1, self.qty + 1):
            AssemblyUnit.objects.create(order=self, seq=index)
        self.status = 'kitting'
        self.released_at = timezone.now()
        self.save(update_fields=['status', 'released_at', 'product', 'modification'])
        from cnc.qrutil import log_event
        log_event(self.qr_token, 'release', '下达装配 %s，%s 套' % (self.code, self.qty), user)

    def refresh_progress(self):
        if self.status in ('draft', 'cancelled'):
            return
        parts = list(self.parts.all())
        units = list(self.units.all())
        if not parts and not units:
            return
        kit_ready = bool(parts) and all(item.status == 'issued' for item in parts)
        if units and kit_ready and all(item.status in ('pass', 'fail') for item in units):
            new_status = 'done'
        elif units and any(item.status == 'running' for item in units):
            new_status = 'assembling'
        elif kit_ready and units and any(item.status == 'qc' for item in units) and not any(
                item.status in ('wait', 'running') for item in units):
            new_status = 'qc'
        elif kit_ready and units and any(item.status != 'wait' for item in units):
            new_status = 'assembling'
        else:
            new_status = 'kitting'
        if new_status == self.status:
            return
        self.status = new_status
        fields = ['status', 'modification']
        if new_status == 'done':
            self.finished_at = timezone.now()
            fields.append('finished_at')
        self.save(update_fields=fields)


class AssemblyPart(models.Model):
    order = models.ForeignKey(AssemblyOrder, verbose_name='装配工单', related_name='parts', on_delete=models.CASCADE)
    seq = models.PositiveIntegerField('顺序', default=10)
    material = models.ForeignKey('basedata.Material', verbose_name='零件', on_delete=models.PROTECT)
    per_qty = models.DecimalField('单套用量', max_digits=12, decimal_places=3, default=Decimal('1'))
    need_qty = models.DecimalField('需求数量', max_digits=12, decimal_places=3, default=Decimal('0'))
    issued_qty = models.DecimalField('已配数量', max_digits=12, decimal_places=3, default=Decimal('0'))
    lot_no = models.CharField('批次', max_length=40, blank=True, default='')
    critical = models.BooleanField('关键件', default=False)
    status = models.CharField('状态', max_length=12, choices=PART_STATUS, default='wait')
    note = models.CharField('说明', max_length=120, blank=True, default='')

    class Meta:
        verbose_name = '部件装配配料'
        verbose_name_plural = '部件装配配料'
        ordering = ['seq', 'id']

    def __str__(self):
        return '%s %s' % (self.material, self.need_qty)

    def save(self, *args, **kwargs):
        if self.need_qty and self.issued_qty >= self.need_qty:
            self.status = 'issued'
        elif self.issued_qty > 0:
            self.status = 'partial'
        else:
            self.status = 'wait'
        super().save(*args, **kwargs)
        self.order.refresh_progress()

    def issue(self, qty, lot_no, user):
        qty = Decimal(qty or 0)
        if qty <= 0:
            raise ValueError('配料数量要大于 0')
        if self.need_qty and (self.issued_qty or 0) + qty > self.need_qty:
            raise ValueError('配料数量不能超过需求')
        self.issued_qty = (self.issued_qty or 0) + qty
        if lot_no:
            self.lot_no = lot_no
        self.save()
        from cnc.qrutil import log_event
        log_event(
            self.order.qr_token, 'kit',
            '配料 %s +%s 批次%s' % (self.material, qty, self.lot_no or '-'), user)


class AssemblyUnit(Tracked):
    """一套总成一个序列，用来追溯装了哪些关键件。"""

    TOKEN_PREFIX = 'AU'
    order = models.ForeignKey(AssemblyOrder, verbose_name='装配工单', related_name='units', on_delete=models.CASCADE)
    seq = models.PositiveIntegerField('套次', default=1)
    station = models.ForeignKey(
        Machine, verbose_name='工位', blank=True, null=True, on_delete=models.SET_NULL)
    assembler = models.ForeignKey(
        User, verbose_name='装配员', blank=True, null=True, on_delete=models.SET_NULL)
    status = models.CharField('状态', max_length=12, choices=UNIT_STATUS, default='wait')
    result = models.CharField('检验结论', max_length=12, choices=UNIT_RESULT, blank=True, default='')
    note = models.CharField('说明', max_length=200, blank=True, default='')
    started_at = models.DateTimeField('开工时间', blank=True, null=True)
    finished_at = models.DateTimeField('装完时间', blank=True, null=True)

    class Meta:
        verbose_name = '部件装配单件'
        verbose_name_plural = '部件装配单件'
        ordering = ['order', 'seq', 'id']

    def __unicode__(self):
        return '%s-%02d' % (self.order.code or '', self.seq)

    def save(self, *args, **kwargs):
        if self.result == 'fail':
            self.status = 'fail'
        elif self.result in ('pass', 'concession') and self.status in ('qc', 'running', 'pass', 'fail'):
            self.status = 'pass'
        super().save(*args, **kwargs)
        self.order.refresh_progress()

    def start(self, user, station=None):
        if self.status not in ('wait', 'running'):
            raise ValueError('这套已经装完')
        if station is not None and station.machine_type != 'ASSEM':
            raise ValueError('请选择装配工位')
        if station is not None and station.status in ('down', 'maintain'):
            raise ValueError('这个工位正在维修或保养')
        self.status = 'running'
        self.assembler = user if getattr(user, 'is_authenticated', False) else self.assembler
        if station:
            self.station = station
        if not self.started_at:
            self.started_at = timezone.now()
        self.save()
        if self.station_id and self.station.status != 'run':
            self.station.set_status('run', user, '装配 %s' % self)
        from cnc.qrutil import log_event
        log_event(self.qr_token, 'start', '开始装配 %s' % self, user)
        log_event(self.order.qr_token, 'start', '单件开工 %s' % self, user)

    def finish(self, user):
        if self.status not in ('wait', 'running'):
            raise ValueError('当前不能完工')
        if self.order.parts.exclude(status='issued').exists():
            raise ValueError('配料还没齐，不能完工')
        self.status = 'qc'
        self.finished_at = timezone.now()
        self.assembler = user if getattr(user, 'is_authenticated', False) else self.assembler
        self.save()
        from cnc.qrutil import log_event
        log_event(self.qr_token, 'finish', '装配完成，待检 %s' % self, user)

    def inspect(self, user, result, note=''):
        if result not in ('pass', 'fail', 'concession'):
            raise ValueError('请选择检验结论')
        if self.status not in ('running', 'qc', 'pass', 'fail'):
            raise ValueError('还没装配，不能检验')
        self.result = result
        self.status = 'fail' if result == 'fail' else 'pass'
        if note:
            self.note = note
        self.save()
        from cnc.qrutil import log_event
        log_event(self.qr_token, 'inspect', '单件%s %s' % (self.get_result_display(), self), user)
        log_event(self.order.qr_token, 'inspect', '%s %s' % (self, self.get_result_display()), user)

    def fit(self, material, lot_no, qty, user):
        record = AssemblyFit.objects.create(
            unit=self, material=material, lot_no=lot_no or '', qty=qty or 1)
        from cnc.qrutil import log_event
        log_event(self.qr_token, 'fit', '装入 %s 批次%s' % (material, record.lot_no or '-'), user)
        return record


class AssemblyFit(models.Model):
    unit = models.ForeignKey(AssemblyUnit, verbose_name='单件', related_name='fits', on_delete=models.CASCADE)
    material = models.ForeignKey('basedata.Material', verbose_name='零件', on_delete=models.PROTECT)
    lot_no = models.CharField('批次', max_length=40, blank=True, default='')
    qty = models.DecimalField('数量', max_digits=12, decimal_places=3, default=Decimal('1'))
    note = models.CharField('说明', max_length=120, blank=True, default='')
    created = models.DateTimeField('时间', auto_now_add=True)

    class Meta:
        verbose_name = '装入记录'
        verbose_name_plural = '装入记录'
        ordering = ['id']

    def __str__(self):
        return '%s %s' % (self.material, self.lot_no)


def _current_operation(operations):
    for status in ('running', 'ready', 'out', 'wait'):
        for operation in operations:
            if operation.status == status:
                return operation
    return operations[-1] if operations else None


def _component_headline(material, jobs):
    name = getattr(material, 'name', None) or material
    open_jobs = [job for job in jobs if job['order'].status not in ('done', 'closed')]
    if not jobs:
        return '%s 无生产工单' % name
    if not open_jobs:
        return '%s 工序已完工' % name
    texts = []
    for job in open_jobs:
        current = job['current']
        if current:
            texts.append('%s %s/%s' % (job['order'].code, current.name, current.get_status_display()))
        else:
            texts.append('%s %s' % (job['order'].code, job['order'].get_status_display()))
    return '%s %s' % (name, '、'.join(texts))


def ensure_demo_assembly():
    """写入一套阀体部件的 BOM、配料和单件，方便直接在后台查看。"""
    from basedata.models import Material, Partner

    if AssemblyOrder.objects.filter(note='模拟-装配单').exists():
        return
    user = User.objects.filter(is_superuser=True).first() or User.objects.first()
    if user is None:
        return
    product, _created = Material.objects.get_or_create(
        code='模拟总成', defaults={'name': '阀体部件', 'spec': '总成', 'can_sale': True})
    body, _created = Material.objects.get_or_create(
        code='模拟阀体', defaults={'name': '阀体', 'spec': '45#', 'can_sale': False})
    bolt, _created = Material.objects.get_or_create(
        code='模拟螺栓', defaults={'name': '螺栓', 'spec': 'M8×25', 'can_sale': False})
    flange = Material.objects.filter(code='模拟物料').first()
    customer = Partner.objects.filter(code='模拟客户').first()
    bom, created = AssemblyBom.objects.get_or_create(
        name='阀体部件清单',
        defaults={'product': product, 'version': 'A', 'note': '阀体、法兰、螺栓'},
    )
    if created or not bom.lines.exists():
        AssemblyBomLine.objects.get_or_create(
            bom=bom, material=body, defaults={'seq': 10, 'qty': Decimal('1'), 'critical': True})
        if flange:
            AssemblyBomLine.objects.get_or_create(
                bom=bom, material=flange, defaults={'seq': 20, 'qty': Decimal('1'), 'critical': True})
        AssemblyBomLine.objects.get_or_create(
            bom=bom, material=bolt, defaults={'seq': 30, 'qty': Decimal('4'), 'critical': False, 'note': '对角拧紧'})
    station = Machine.objects.filter(machine_type='ASSEM').first()
    order = AssemblyOrder.objects.create(
        title='阀体部件总成', bom=bom, product=product, customer=customer,
        qty=4, due_date=datetime.date.today() + datetime.timedelta(days=3),
        station=station, note='模拟-装配单',
    )
    order.release(user)
    body_part = order.parts.filter(material=body).first()
    if body_part:
        body_part.issue(body_part.need_qty, 'BODY-1003', user)
    flange_part = order.parts.filter(material=flange).first() if flange else None
    if flange_part:
        flange_part.issue(Decimal('2'), '模拟批次', user)
