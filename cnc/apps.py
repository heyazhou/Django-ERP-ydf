from django.apps import AppConfig
from django.db.models.signals import post_migrate


PROCESS_SEED = (
    ('下料', 'SAW', False),
    ('加工程序', 'PROG', False),
    ('调机', 'SETUP', False),
    ('手动加工', 'MANUAL', False),
    ('车削', 'MANUAL', False),
    ('铣削', 'MANUAL', False),
    ('线切割', 'MANUAL', False),
    ('电火花', 'MANUAL', False),
    ('手工焊接', 'MANUAL', False),
    ('钻孔', 'MANUAL', False),
    ('攻丝', 'MANUAL', False),
    ('打磨清洗', 'MANUAL', False),
    ('加工中心', 'MC', False),
    ('磨削', 'GRIND', False),
    ('钳工', 'BENCH', False),
    ('部件装配', 'ASSEM', False),
    ('热处理', 'OUT', True),
    ('表面处理', 'OUT', True),
    ('检验', 'QC', False),
    ('包装', 'PACK', False),
)


def seed_processes(sender, **kwargs):
    if getattr(sender, 'label', None) != 'cnc':
        return
    from cnc.models import Process
    for index, (name, machine_type, outsource) in enumerate(PROCESS_SEED, start=1):
        Process.objects.get_or_create(
            name=name,
            defaults={'machine_type': machine_type, 'outsource': outsource, 'seq': index},
        )
    from cnc.boards import ensure_shop_areas
    ensure_shop_areas()


class CncConfig(AppConfig):
    name = 'cnc'
    verbose_name = '数控生产'

    def ready(self):
        post_migrate.connect(seed_processes, sender=self)
