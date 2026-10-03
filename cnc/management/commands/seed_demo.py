# coding=utf-8
import datetime
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from basedata.models import BankAccount, ExpenseAccount, Material, Measure, Partner, Project, Warehouse
from cnc.assembly import AssemblyBom, AssemblyBomLine, AssemblyOrder
from cnc.erpmes import issue_materials, orders_from_sale, receive_finished
from cnc.models import Handoff, Routing, RoutingStep, WorkOrder
from invent.models import (
    AdjustItem, InItem, InitItem, InitialInventory, Inventory, StockIn, WareAdjust,
)
from organ.models import Organization, OrgUnit, Position
from purchase.models import Invoice, POItem, Payment, PurchaseOrder
from sale.models import OfferItem, OfferSheet, PaymentCollection, SaleItem, SaleOrder


class Command(BaseCommand):
    help = '\u5199\u5165\u4e00\u5957\u8986\u76d6\u9500\u552e\u3001\u91c7\u8d2d\u3001\u5e93\u5b58\u3001\u8f66\u95f4\u548c\u8d28\u91cf\u7684\u6a21\u62df\u6570\u636e'

    def handle(self, *args, **options):
        self.user = User.objects.filter(username='admin').first() or User.objects.filter(is_superuser=True).first()
        if self.user is None:
            self.user = User.objects.create_superuser('admin', 'admin@localhost', 'admin')
        self._clear_erp()
        call_command('seed_shop')
        self.org = self._organ()
        self.house, self.finished = self._warehouses()
        self.piece, self.kilo = self._measures()
        self.customer = Partner.objects.get(code='\u6a21\u62df\u5ba2\u6237')
        self.vendor = Partner.objects.get(code='\u6a21\u62df\u5916\u534f')
        self._materials()
        self._stock()
        self._buy()
        self._sell()
        self._money()
        self._people()
        self._quality_and_message()
        call_command('seed_workflows')
        call_command('seed_people')
        self.stdout.write(self.style.SUCCESS('\u6a21\u62df\u6570\u636e\u5df2\u5199\u5165\u3002\u767b\u5f55 admin / admin'))

    def _clear_erp(self):
        AssemblyOrder.objects.filter(note__startswith='\u9500\u552e').delete()
        WorkOrder.objects.filter(drawing_no__in=[
            '\u6a21\u62df\u7269\u6599', '\u6a21\u62df\u603b\u6210', '\u6a21\u62df\u9600\u4f53', '\u6a21\u62df\u87ba\u6813', '\u6a21\u62df\u5706\u94a2',
        ]).delete()
        PaymentCollection.objects.filter(so__title__startswith='\u6a21\u62df').delete()
        SaleOrder.objects.filter(title__startswith='\u6a21\u62df').delete()
        OfferSheet.objects.filter(title__startswith='\u6a21\u62df').delete()
        PurchaseOrder.objects.filter(title__startswith='\u6a21\u62df').delete()
        StockIn.objects.filter(title__startswith='\u6a21\u62df').delete()
        StockIn.objects.filter(title__startswith='\u5165\u5e93').delete()
        from invent.models import StockOut
        StockOut.objects.filter(title__startswith='\u9886\u6599').delete()
        WareAdjust.objects.filter(title__startswith='\u6a21\u62df').delete()
        InitialInventory.objects.filter(title__startswith='\u6a21\u62df').delete()
        from selfhelp.models import Activity, Loan, Reimbursement, WorkOrder as ServiceOrder
        Reimbursement.objects.filter(title__startswith='\u6a21\u62df').delete()
        Loan.objects.filter(title__startswith='\u6a21\u62df').delete()
        ServiceOrder.objects.filter(title__startswith='\u6a21\u62df').delete()
        Activity.objects.filter(title__startswith='\u6a21\u62df').delete()
        Project.objects.filter(name__startswith='\u6a21\u62df').delete()
        from hr.models import Entry
        Entry.objects.filter(name__startswith='\u6a21\u62df').delete()
        codes = ['\u6a21\u62df\u7269\u6599', '\u6a21\u62df\u603b\u6210', '\u6a21\u62df\u9600\u4f53', '\u6a21\u62df\u87ba\u6813', '\u6a21\u62df\u5706\u94a2']
        Inventory.objects.filter(material__code__in=codes).delete()
        AssemblyBom.objects.filter(name='\u6a21\u62df\u6cd5\u5170\u7528\u6599').delete()

    def _organ(self):
        today = datetime.date.today()
        org, _created = Organization.objects.get_or_create(
            code='ORG1', defaults={'name': '\u6a21\u62df\u673a\u52a0\u5382', 'short': '\u673a\u52a0\u5382', 'begin': today, 'creator': 'admin'})
        unit, _created = OrgUnit.objects.get_or_create(
            code='SHOP', defaults={'name': '\u751f\u4ea7\u8f66\u95f4', 'organization': org, 'unit_type': 2, 'begin': today, 'creator': 'admin'})
        position, _created = Position.objects.get_or_create(
            code='OP01', defaults={'name': '\u64cd\u4f5c\u5de5', 'unit': unit, 'organization': org, 'series': 'P', 'begin': today, 'creator': 'admin'})
        from basedata.models import Employee
        person = Employee.objects.filter(user=self.user).first()
        if person is None:
            Employee.objects.create(
                name='\u8d75\u516d', code='10006', idcard='000000000000000000',
                position=position, organization=org, user=self.user, phone='13800000000',
                creator='admin', begin=today,
            )
        self.position = position
        self.unit = unit
        return org

    def _warehouses(self):
        raw, _created = Warehouse.objects.get_or_create(code='RAW', defaults={'name': '\u539f\u6599\u5e93', 'org': self.org})
        done, _created = Warehouse.objects.get_or_create(code='FG', defaults={'name': '\u6210\u54c1\u5e93', 'org': self.org})
        return raw, done

    def _measures(self):
        piece, _created = Measure.objects.get_or_create(code='PCS', defaults={'name': '\u4ef6'})
        kilo, _created = Measure.objects.get_or_create(code='KG', defaults={'name': '\u5343\u514b'})
        return piece, kilo

    def _materials(self):
        self.flange = Material.objects.get(code='\u6a21\u62df\u7269\u6599')
        self.product = Material.objects.get(code='\u6a21\u62df\u603b\u6210')
        self.body = Material.objects.get(code='\u6a21\u62df\u9600\u4f53')
        self.bolt = Material.objects.get(code='\u6a21\u62df\u87ba\u6813')
        self.bar, _created = Material.objects.get_or_create(
            code='\u6a21\u62df\u5706\u94a2',
            defaults={'name': '\u5706\u94a2', 'spec': '45# \u03c680', 'supply_kind': 'raw', 'can_sale': False},
        )
        self.bar.supply_kind = 'raw'
        self.bar.can_sale = False
        self.bar.stock_price = Decimal('12.5000')
        self.bar.purchase_price = Decimal('12.5000')
        self.bar.warehouse = self.house
        self.bar.save()
        self.flange.can_sale = True
        self.flange.supply_kind = 'part'
        self.flange.stock_price = Decimal('46.0000')
        self.flange.sale_price = Decimal('80.0000')
        self.flange.warehouse = self.finished
        self.flange.save()
        self.product.can_sale = True
        self.product.sale_price = Decimal('260.0000')
        self.product.warehouse = self.finished
        self.product.save()
        self.body.supply_kind = 'part'
        self.body.can_sale = True
        self.body.sale_price = Decimal('90.0000')
        self.body.warehouse = self.finished
        self.body.save()
        self.bolt.supply_kind = 'hardware'
        self.bolt.can_sale = False
        self.bolt.stock_price = Decimal('0.5000')
        self.bolt.warehouse = self.house
        self.bolt.save()
        for material, measure in (
            (self.bar, self.kilo), (self.flange, self.piece), (self.product, self.piece),
            (self.body, self.piece), (self.bolt, self.piece),
        ):
            material.measure.add(measure)
        bom, _created = AssemblyBom.objects.get_or_create(
            name='\u6a21\u62df\u6cd5\u5170\u7528\u6599',
            defaults={'product': self.flange, 'version': 'A', 'note': '\u4e00\u4ef6\u6cd5\u5170\u7528\u4e00\u6bb5\u5706\u94a2'},
        )
        AssemblyBomLine.objects.get_or_create(
            bom=bom, material=self.bar, defaults={'seq': 10, 'qty': Decimal('1.5'), 'note': '\u4e0b\u6599'},
        )
        routing, created = Routing.objects.get_or_create(
            name='\u6a21\u62df\u9600\u4f53\u5de5\u827a', defaults={'material': self.body, 'version': 'A'})
        if created or not routing.steps.exists():
            RoutingStep.objects.get_or_create(
                routing=routing, seq=10, name='\u8f66\u524a',
                defaults={'machine_type': 'MANUAL', 'setup_min': Decimal('15'), 'unit_min': Decimal('8')})
            RoutingStep.objects.get_or_create(
                routing=routing, seq=20, name='\u68c0\u9a8c',
                defaults={'machine_type': 'QC', 'unit_min': Decimal('3')})

    def _stock(self):
        sheet = InitialInventory.objects.create(
            code='IN90001', title='\u6a21\u62df\u671f\u521d\u5e93\u5b58', user=self.user, org=self.org, creator='admin')
        InitItem.objects.create(
            master=sheet, material=self.bar, measure=self.kilo, warehouse=self.house,
            cnt=Decimal('20'), price=Decimal('12.5000'), source='IN90001')
        InitItem.objects.create(
            master=sheet, material=self.bolt, measure=self.piece, warehouse=self.house,
            cnt=Decimal('80'), price=Decimal('0.5000'), source='IN90001')
        sheet.init_entry()

    def _buy(self):
        today = datetime.date.today()
        po = PurchaseOrder.objects.create(
            code='PO90001', partner=self.vendor, org=self.org, user=self.user,
            order_date=today, arrive_date=today, title='\u6a21\u62df\u5706\u94a2\u91c7\u8d2d', creator='admin')
        POItem.objects.create(po=po, material=self.bar, measure=self.kilo, cnt=Decimal('30'), price=Decimal('12.5000'))
        stock = StockIn.objects.create(
            code='SI90001', title='\u6a21\u62df\u91c7\u8d2d\u5165\u5e93', warehouse=self.house, user=self.user,
            po=po, org=self.org, batch='HEAT-45', creator='admin')
        InItem.objects.create(
            master=stock, material=self.bar, measure=self.kilo, warehouse=self.house,
            cnt=Decimal('30'), price=Decimal('12.5000'), po_item=po.poitem_set.first())
        stock.action_entry(None)
        Invoice.objects.create(
            code='INV90001', number='00000001', po=po, vo_amount=Decimal('375.0000'), creator='admin')
        bank, _created = BankAccount.objects.get_or_create(
            account='6222000000000001', defaults={'title': '\u6a21\u62df\u57fa\u672c\u6237', 'org': self.org, 'creator': 'admin'})
        Payment.objects.create(code='PY90001', po=po, py_amount=Decimal('200.0000'), bank=bank, org=self.org, creator='admin')
        row = Inventory.objects.filter(material=self.bolt, warehouse=self.house).first()
        if row:
            adjust = WareAdjust.objects.create(code='AD90001', title='\u6a21\u62df\u87ba\u6813\u76d8\u76c8', user=self.user, org=self.org, creator='admin')
            AdjustItem.objects.create(master=adjust, inventory=row, material=self.bolt, measure=self.piece, warehouse=self.house, cnt=Decimal('2'), prop='+', price=row.price)
            adjust.action_adjust(None)

    def _sell(self):
        today = datetime.date.today()
        offer = OfferSheet.objects.create(
            code='OF90001', partner=self.customer, org=self.org, user=self.user,
            offer_date=today, deliver_date=today + datetime.timedelta(days=7),
            title='\u6a21\u62df\u9600\u4f53\u62a5\u4ef7', creator='admin')
        OfferItem.objects.create(master=offer, material=self.product, measure=self.piece, cnt=Decimal('2'), sale_price=Decimal('260'))
        sale = SaleOrder.objects.create(
            code='SO90001', partner=self.customer, org=self.org, user=self.user,
            order_date=today, deliver_date=today + datetime.timedelta(days=5),
            title='\u6a21\u62df\u9600\u4f53\u90e8\u4ef6\u8ba2\u5355', creator='admin')
        SaleItem.objects.create(master=sale, material=self.product, measure=self.piece, cnt=Decimal('2'), sale_price=Decimal('260'))
        orders_from_sale(sale, self.user)
        PaymentCollection.objects.create(
            code='PC90001', so=sale, collection_amount=Decimal('200.00'), org=self.org, creator='admin')
        for order in WorkOrder.objects.filter(sale_order=sale, status='draft'):
            order.release(self.user)
        assembly = AssemblyOrder.objects.filter(note__contains='SO90001', status='draft').first()
        if assembly:
            assembly.release(self.user)
        flange_job = WorkOrder.objects.filter(sale_order=sale, material=self.flange).first()
        if flange_job and flange_job.materials.exists():
            issue_materials(flange_job, self.user)
        done = WorkOrder.objects.filter(drawing_no='\u6a21\u62df-\u6cd5\u5170-\u5b8c\u5de5', status='done', stocked_at__isnull=True).first()
        if done:
            receive_finished(done, self.user)

    def _money(self):
        project = Project.objects.create(
            code='PJ9001', name='\u6a21\u62df\u9600\u4f53\u9879\u76ee', partner=self.customer,
            status='01', prj_type='00', budget=Decimal('50000'), creator='admin')
        loan = __import__('selfhelp.models', fromlist=['Loan']).Loan.objects.create(
            code='LN9001', title='\u6a21\u62df\u5dee\u65c5\u501f\u6b3e', project=project, user=self.user,
            loan_amount=Decimal('800.00'), creator='admin')
        account, _created = ExpenseAccount.objects.get_or_create(
            code='EX9001', defaults={'name': '\u6a21\u62df\u5200\u5177\u8d39', 'category': 'MU', 'creator': 'admin'})
        sheet = __import__('selfhelp.models', fromlist=['Reimbursement']).Reimbursement.objects.create(
            code='RB9001', title='\u6a21\u62df\u5200\u5177\u62a5\u9500', project=project, user=self.user,
            loan=loan, org=self.unit, creator='admin')
        __import__('selfhelp.models', fromlist=['ReimbursementItem']).ReimbursementItem.objects.create(
            reimbursement=sheet, expense_account=account, amount=Decimal('120.00'), memo='\u5200\u7247')
        now = timezone.now()
        __import__('selfhelp.models', fromlist=['Activity']).Activity.objects.create(
            code='AC9001', title='\u6a21\u62df\u73ed\u524d\u4f1a', classification='M',
            begin_time=now, end_time=now + datetime.timedelta(hours=1),
            location='\u8f66\u95f4', host='\u8d75\u516d', creator='admin')
        __import__('selfhelp.models', fromlist=['WorkOrder']).WorkOrder.objects.create(
            code='SW9001', title='\u6a21\u62df\u8bbe\u5907\u54a8\u8be2', description='\u4e3b\u8f74\u5f02\u54cd\u9700\u8981\u73b0\u573a\u786e\u8ba4',
            project=project, user=self.user, creator='admin')

    def _people(self):
        from basedata.models import Employee
        from hr.models import Entry
        guider = Employee.objects.filter(user=self.user).first() or Employee.objects.order_by('id').first()
        Entry.objects.create(
            code='EM9001', name='\u6a21\u62df\u65b0\u4eba', idcard='000000199001010099',
            zipcode='200000', phone='13900000000', guider=guider, position=self.position, creator='admin')

    def _quality_and_message(self):
        from quality.models import CheckRecord
        from quality.services import open_check
        running = WorkOrder.objects.filter(drawing_no='\u6a21\u62df-\u6cd5\u5170-\u5728\u5236').first()
        if running and not CheckRecord.objects.filter(work_order=running).exists():
            operation = running.operations.order_by('seq').first()
            open_check('first', self.user, work_order=running, operation=operation, result='pass', check_qty=1, note='\u6a21\u62df\u9996\u4ef6')
        if running and not Handoff.objects.filter(body__startswith='\u6a21\u62df\uff1a\u9996\u4ef6').exists():
            Handoff.objects.create(
                token=(running.qr_token or '')[:40], kind='info', sender=self.user, receiver=self.user,
                place='\u8f66\u524a\u5de5\u4f4d', body='\u6a21\u62df\uff1a\u9996\u4ef6\u5df2\u5408\u683c\uff0c\u8bf7\u7ee7\u7eed\u8f66\u524a')
