# coding=utf-8
from django.core.management.base import BaseCommand

from syscfg.backup import run_backup
from syscfg.models import BackupPlan


class Command(BaseCommand):
    help = '按已启用的备份方案执行备份'

    def handle(self, *args, **options):
        plans = list(BackupPlan.objects.filter(enabled=True))
        if not plans:
            self.stdout.write('没有启用的备份方案')
            return
        for plan in plans:
            log = run_backup(plan)
            self.stdout.write('%s：%s %s' % (plan.name, log.get_status_display(), log.message))
