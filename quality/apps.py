from django.apps import AppConfig
from django.db.models.signals import post_migrate


def seed_quality(sender, **kwargs):
    if getattr(sender, 'label', None) != 'quality':
        return
    from quality.models import STAGES, ControlPoint, Standard, StandardItem
    for stage, _label in STAGES:
        ControlPoint.objects.get_or_create(
            stage=stage,
            process_name='',
            defaults={
                'required': stage in ('incoming', 'process', 'outsource', 'assembly', 'final'),
                'note': '全流程质量控制点',
            },
        )
    samples = (
        ('incoming', '来料检验标准', (
            ('材质与炉批', '', '', '', '', '核对材质单', False),
            ('外观', '', '', '', '', '目视', False),
            ('抽检尺寸', '按图纸', '', '', '毫米', '卡尺', True),
        )),
        ('process', '过程检验标准', (
            ('关键尺寸', '50', '49.90', '50.10', '毫米', '卡尺', True),
            ('外观', '', '', '', '', '目视', False),
            ('螺纹或孔', '', '', '', '', '通止规', False),
        )),
        ('outsource', '外协回厂检验标准', (
            ('处理层', '', '', '', '', '目视', False),
            ('变形', '', '', '', '', '平台', True),
            ('关键尺寸', '按图纸', '', '', '毫米', '卡尺', True),
        )),
        ('assembly', '装配检验标准', (
            ('配装间隙', '', '', '', '', '塞尺', True),
            ('动作', '', '', '', '', '手动', False),
            ('外观与标识', '', '', '', '', '目视', False),
        )),
        ('final', '终检与出货标准', (
            ('全尺寸', '按图纸', '', '', '毫米', '卡尺', True),
            ('外观', '', '', '', '', '目视', False),
            ('数量与标识', '', '', '', '', '清点', False),
        )),
    )
    for stage, name, items in samples:
        standard, created = Standard.objects.get_or_create(
            name=name,
            stage=stage,
            defaults={'version': 'A', 'active': True, 'note': '可按物料另建标准，留空物料时作为通用标准'},
        )
        if created:
            for seq, item in enumerate(items, start=1):
                StandardItem.objects.create(
                    standard=standard,
                    seq=seq * 10,
                    name=item[0],
                    nominal=item[1],
                    lower_limit=item[2],
                    upper_limit=item[3],
                    unit=item[4],
                    method=item[5],
                    key_size=item[6],
                )


class QualityConfig(AppConfig):
    name = 'quality'
    verbose_name = '质量管理'

    def ready(self):
        post_migrate.connect(seed_quality, sender=self)
