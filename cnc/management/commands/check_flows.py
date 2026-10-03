from decimal import Decimal

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.test import Client
from django.urls import reverse

from cnc.models import (
    Drawing, Fixture, Inspection, Machine, MaterialLot, NcProgram, OutsourceOrder,
    Routing, Tool, WorkOrder,
)


class Command(BaseCommand):
    help = '检查后台单据二维码和生产流程页面'

    def handle(self, *args, **options):
        user = get_user_model().objects.get(username='admin')
        client = Client()
        client.force_login(user)
        fails = []

        def hit(url, needle=None):
            response = client.get(url)
            body = response.content.decode('utf-8', 'replace')
            if response.status_code != 200 or 'TemplateSyntaxError' in body:
                fails.append('%s -> %s' % (url, response.status_code))
                return ''
            if needle and needle not in body:
                fails.append('%s 缺少 %s' % (url, needle))
            return body

        for model, model_admin in admin.site._registry.items():
            label = model._meta.label
            try:
                list_url = reverse('admin:%s_%s_changelist' % (model._meta.app_label, model._meta.model_name))
            except Exception as exc:
                fails.append('%s 列表地址 %s' % (label, exc))
                continue
            response = client.get(list_url)
            body = response.content.decode('utf-8', 'replace')
            if response.status_code != 200:
                fails.append('%s -> %s' % (list_url, response.status_code))
                continue
            obj = model_admin.get_queryset(response.wsgi_request).order_by('pk').first()
            if obj is None:
                continue
            try:
                change_url = reverse(
                    'admin:%s_%s_change' % (model._meta.app_label, model._meta.model_name),
                    args=[obj.pk])
            except Exception:
                continue
            body = hit(change_url, '/m/qr/')
            if '/m/q/' in body:
                token = body.split('/m/q/', 1)[1].split('/', 1)[0]
                hit('/m/qr/%s/' % token, '<svg')
                opened = client.get('/m/q/%s/' % token, follow=True)
                if opened.status_code != 200:
                    fails.append('扫码 %s -> %s' % (token, opened.status_code))

        for url in ('/', '/m/', '/m/scan/', '/m/report/'):
            hit(url)
        for name in ('progress', 'due', 'machine', 'quality', 'operator', 'outsource', 'tool'):
            hit('/m/report/%s/' % name)

        order = WorkOrder.objects.filter(drawing_no__startswith='模拟').exclude(status='cancelled').first()
        if order is None:
            fails.append('没有模拟工单')
        else:
            hit('/m/wo/%s/' % order.pk, order.code)
            hit('/m/wo/%s/card/' % order.pk)
            ready = WorkOrder.objects.filter(drawing_no__startswith='模拟', status='released').first()
            if ready:
                op = ready.operations.order_by('seq').first()
                hit('/m/op/%s/' % op.pk)
                payload = {'action': 'start'}
                if op.machine_type == 'SETUP':
                    machine = Machine.objects.filter(machine_type='MC').exclude(status__in=['down', 'maintain']).first()
                elif op.machine_type == 'PROG':
                    machine = None
                else:
                    machine = Machine.objects.filter(machine_type=op.machine_type).exclude(
                        status__in=['down', 'maintain']).first()
                if machine:
                    payload['machine'] = machine.pk
                client.post('/m/op/%s/' % op.pk, payload)
                op.refresh_from_db()
                if op.status != 'running':
                    fails.append('工序开工后状态是 %s' % op.status)
                client.post('/m/op/%s/' % op.pk, {
                    'action': 'report', 'good': '1', 'scrap': '0', 'minutes': '12', 'reason': '', 'note': '流程检查',
                })
                client.post('/m/op/%s/' % op.pk, {
                    'action': 'inspect', 'kind': 'patrol', 'result': 'pass', 'check_qty': '1', 'fail_qty': '0', 'note': '巡检',
                })
                op.refresh_from_db()
                if op.good_qty < Decimal('1'):
                    fails.append('报工数量没有写入')
            else:
                running = WorkOrder.objects.filter(drawing_no__startswith='模拟', status='running').first()
                op = running.operations.filter(good_qty__gte=1).first() if running else None
                if op is None:
                    fails.append('没有可核对的报工记录')
                else:
                    hit('/m/op/%s/' % op.pk)

        for model, urlname in (
            (Machine, '/m/machine/%s/'),
            (Tool, '/m/tool/%s/'),
            (Fixture, '/m/fixture/%s/'),
            (MaterialLot, '/m/lot/%s/'),
            (Inspection, '/m/qc/%s/'),
            (NcProgram, '/m/nc/%s/'),
            (Drawing, '/m/drawing/%s/'),
            (OutsourceOrder, '/m/os/%s/'),
            (Routing, '/m/routing/%s/'),
        ):
            obj = model.objects.order_by('pk').first()
            if obj is None:
                fails.append('%s 没有模拟数据' % model._meta.verbose_name)
                continue
            hit(urlname % obj.pk)
            opened = client.get('/m/q/%s/' % obj.qr_token, follow=True)
            if opened.status_code != 200:
                fails.append('扫码 %s -> %s' % (obj.qr_token, opened.status_code))

        if fails:
            self.stdout.write('失败 %s 项' % len(fails))
            for item in fails:
                self.stdout.write(item)
            raise SystemExit(1)
        self.stdout.write('全部流程检查通过')
