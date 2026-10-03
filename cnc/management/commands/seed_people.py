# coding=utf-8
import datetime
from decimal import Decimal

from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.core.management.base import BaseCommand

from basedata.models import DataImport, Employee, ExpenseAccount, Material, Partner, Project
from cnc.assembly import AssemblyOrder
from cnc.models import Machine, MaintainOrder, OutsourceOrder, Process, Routing, RoutingStep, WorkOrder
from hr.models import Entry
from invent.models import InitialInventory, StockIn, StockOut, WareAdjust, WareReturn
from organ.models import Organization, OrgUnit, Position
from purchase.models import Invoice, Payment, PurchaseOrder
from sale.models import OfferSheet, PaymentCollection, SaleOrder
from selfhelp.models import Activity, Loan, Reimbursement, WorkOrder as ServiceOrder
from workflow.models import Instance, Modal, Node
from workflow.phoneflow import decide_flow, start_flow


POSTS = (
    ('A', 'OFC', '\u5382\u90e8', (
        ('01', '\u529e\u4e8b\u5458'),
        ('02', '\u4ed3\u7ba1\u5458'),
        ('03', '\u8d22\u52a1\u4e3b\u7ba1'),
        ('04', '\u526f\u5382\u957f'),
        ('05', '\u5382\u957f'),
    )),
    ('S', 'SAL', '\u8425\u9500\u90e8', (
        ('01', '\u9500\u552e\u5185\u52e4'),
        ('02', '\u8ddf\u5355\u5458'),
        ('03', '\u4e1a\u52a1\u5458'),
        ('04', '\u9500\u552e\u4e3b\u7ba1'),
        ('05', '\u9500\u552e\u7ecf\u7406'),
    )),
    ('T', 'TEC', '\u6280\u672f\u90e8', (
        ('01', '\u7ed8\u56fe\u5458'),
        ('02', '\u7f16\u7a0b\u5458'),
        ('03', '\u5de5\u827a\u5458'),
        ('04', '\u8d28\u91cf\u5de5\u7a0b\u5e08'),
        ('05', '\u6280\u672f\u8d1f\u8d23\u4eba'),
    )),
    ('P', 'SHOP', '\u751f\u4ea7\u8f66\u95f4', (
        ('01', '\u64cd\u4f5c\u5de5'),
        ('02', '\u624b\u52a8\u52a0\u5de5'),
        ('03', '\u52a0\u5de5\u4e2d\u5fc3\u64cd\u4f5c'),
        ('04', '\u8c03\u673a\u5e08\u5085'),
        ('05', '\u751f\u4ea7\u4e3b\u7ba1'),
    )),
)
NAMES = (
    '\u5468\u6210', '\u5434\u654f', '\u90d1\u5f3a', '\u51af\u4e3d', '\u9648\u521a',
    '\u5b59\u5029', '\u9a6c\u8d85', '\u6731\u7433', '\u80e1\u519b', '\u90ed\u71d5',
    '\u4f55\u5e73', '\u9ad8\u78ca', '\u6797\u96ea', '\u7f57\u658c', '\u5510\u6167',
    '\u97e9\u51ac', '\u66f9\u9633', '\u5f6d\u9759', '\u848b\u4f1f', '\u6f58\u971e',
)
RANKS = (
    '10', '11', '12', '13', '14', '15',
    '20', '21', '22', '23', '24', '25', '26', '27',
)
KINDS = (
    ('ok', '\u540c\u610f', 'A'),
    ('no', '\u62d2\u7edd', 'D'),
    ('stop', '\u7ec8\u6b62', 'T'),
)


class Request(object):
    def __init__(self, user):
        self.user = user
        self.POST = self

    def getlist(self, key):
        return []


class Command(BaseCommand):
    help = '\u6309\u5168\u90e8\u5c97\u4f4d\u548c\u804c\u7ea7\u5199\u5165\u804c\u5458\uff0c\u5e76\u628a\u6bcf\u6761\u6d41\u7a0b\u8d70\u4e00\u904d'

    def handle(self, *args, **options):
        self.user = User.objects.filter(username='admin').first() or User.objects.filter(is_superuser=True).first()
        if self.user is None:
            raise RuntimeError('need admin')
        self.today = datetime.date.today()
        self._clear()
        self._organ()
        self._staff()
        self._handlers()
        self._flows()
        self._all_processes()
        call_command('seed_workflows')
        self.stdout.write(self.style.SUCCESS(
            '\u5c97\u4f4d %s\uff0c\u804c\u5458 %s\uff0c\u804c\u7ea7 %s\u3002\u5c97\u4f4d\u8d26\u53f7\u4e0e\u5bc6\u7801\u76f8\u540c\uff0c\u4f8b\u5982 A05 / A05' % (
                Position.objects.exclude(code='OP01').count() + Position.objects.filter(code='OP01').count(),
                Employee.objects.exclude(code='10006').count(),
                Employee.objects.exclude(rank='00').values('rank').distinct().count(),
            )))

    def _forget(self, qs, app, model):
        ids = list(qs.values_list('pk', flat=True))
        if ids:
            Instance.objects.filter(modal__app_name=app, modal__model_name=model, object_id__in=ids).delete()
        qs.delete()

    def _clear(self):
        self._forget(OutsourceOrder.objects.filter(note__startswith='\u6d41\u7a0b'), 'cnc', 'outsourceorder')
        self._forget(WorkOrder.objects.filter(drawing_no__startswith='\u6d41\u7a0b'), 'cnc', 'workorder')
        self._forget(WorkOrder.objects.filter(drawing_no='\u6a21\u62df-\u5168\u5de5\u5e8f'), 'cnc', 'workorder')
        Routing.objects.filter(name='\u6a21\u62df\u5168\u5de5\u5e8f\u5de5\u827a').delete()
        self._forget(MaintainOrder.objects.filter(title__startswith='\u6d41\u7a0b'), 'cnc', 'maintainorder')
        self._forget(AssemblyOrder.objects.filter(note__startswith='\u6d41\u7a0b'), 'cnc', 'assemblyorder')
        self._forget(Entry.objects.filter(name__startswith='\u6d41\u7a0b'), 'hr', 'entry')
        self._forget(DataImport.objects.filter(title__startswith='\u6d41\u7a0b'), 'basedata', 'dataimport')
        self._forget(Reimbursement.objects.filter(title__startswith='\u6d41\u7a0b'), 'selfhelp', 'reimbursement')
        self._forget(Loan.objects.filter(title__startswith='\u6d41\u7a0b'), 'selfhelp', 'loan')
        self._forget(ServiceOrder.objects.filter(title__startswith='\u6d41\u7a0b'), 'selfhelp', 'workorder')
        self._forget(Activity.objects.filter(title__startswith='\u6d41\u7a0b'), 'selfhelp', 'activity')
        self._forget(PaymentCollection.objects.filter(so__title__startswith='\u6d41\u7a0b'), 'sale', 'paymentcollection')
        self._forget(SaleOrder.objects.filter(title__startswith='\u6d41\u7a0b'), 'sale', 'saleorder')
        self._forget(OfferSheet.objects.filter(title__startswith='\u6d41\u7a0b'), 'sale', 'offersheet')
        self._forget(Invoice.objects.filter(po__title__startswith='\u6d41\u7a0b'), 'purchase', 'invoice')
        self._forget(Payment.objects.filter(po__title__startswith='\u6d41\u7a0b'), 'purchase', 'payment')
        self._forget(PurchaseOrder.objects.filter(title__startswith='\u6d41\u7a0b'), 'purchase', 'purchaseorder')
        self._forget(WareReturn.objects.filter(title__startswith='\u6d41\u7a0b'), 'invent', 'warereturn')
        self._forget(WareAdjust.objects.filter(title__startswith='\u6d41\u7a0b'), 'invent', 'wareadjust')
        self._forget(StockOut.objects.filter(title__startswith='\u6d41\u7a0b'), 'invent', 'stockout')
        self._forget(StockIn.objects.filter(title__startswith='\u6d41\u7a0b'), 'invent', 'stockin')
        self._forget(InitialInventory.objects.filter(title__startswith='\u6d41\u7a0b'), 'invent', 'initialinventory')
        self._forget(Project.objects.filter(name__startswith='\u6d41\u7a0b'), 'basedata', 'project')
        codes = []
        for series, _unit, _uname, rows in POSTS:
            for grade, _title in rows:
                codes.append(series + grade)
        codes.extend(['X01', 'X02'])
        self._forget(Employee.objects.filter(code__in=codes), 'basedata', 'employee')
        User.objects.filter(username__in=codes).delete()
        Position.objects.filter(code__in=[item for item in codes if item not in ('P01', 'X01', 'X02')]).delete()
        OrgUnit.objects.filter(code__in=['OFC', 'SAL', 'TEC']).delete()

    def _organ(self):
        self.org, _created = Organization.objects.get_or_create(
            code='ORG1', defaults={'name': '\u6a21\u62df\u673a\u52a0\u5382', 'short': '\u673a\u52a0\u5382', 'begin': self.today, 'creator': 'admin'})
        self.units = {}
        shop, _created = OrgUnit.objects.get_or_create(
            code='SHOP', defaults={'name': '\u751f\u4ea7\u8f66\u95f4', 'organization': self.org, 'unit_type': 2, 'begin': self.today, 'creator': 'admin'})
        self.units['SHOP'] = shop
        for code, name, unit_type in (
            ('OFC', '\u5382\u90e8', 2),
            ('SAL', '\u8425\u9500\u90e8', 2),
            ('TEC', '\u6280\u672f\u90e8', 2),
        ):
            unit, _created = OrgUnit.objects.get_or_create(
                code=code, defaults={'name': name, 'organization': self.org, 'unit_type': unit_type, 'begin': self.today, 'creator': 'admin'})
            self.units[code] = unit
        self.customer, _created = Partner.objects.get_or_create(
            code='\u6a21\u62df\u5ba2\u6237', defaults={'name': '\u6a21\u62df\u673a\u52a0\u5ba2\u6237', 'partner_type': 'C'})
        self.vendor, _created = Partner.objects.get_or_create(
            code='\u6a21\u62df\u5916\u534f', defaults={'name': '\u6a21\u62df\u70ed\u5904\u7406\u5382', 'partner_type': 'S'})

    def _staff(self):
        self.people = {}
        index = 0
        for series, unit_code, _unit_name, rows in POSTS:
            parent = None
            for grade, title in reversed(rows):
                code = 'OP01' if series == 'P' and grade == '01' else series + grade
                position, _created = Position.objects.get_or_create(
                    code=code,
                    defaults={
                        'name': title, 'unit': self.units[unit_code], 'organization': self.org,
                        'series': series, 'grade': grade, 'parent': parent, 'begin': self.today, 'creator': 'admin',
                    },
                )
                position.name = title
                position.unit = self.units[unit_code]
                position.series = series
                position.grade = grade
                position.parent = parent
                position.status = True
                position.save()
                parent = position
                self._person(series + grade, NAMES[index], position, RANKS[index % len(RANKS)], '10')
                index += 1
        clerk = Position.objects.get(code='A01')
        self._person('X01', '\u6d41\u7a0b\u62d2\u7edd', clerk, '27', '12')
        self._person('X02', '\u6d41\u7a0b\u7ec8\u6b62', clerk, '26', '12')

    def _person(self, code, name, position, rank, status):
        account, created = User.objects.get_or_create(username=code, defaults={'is_staff': True, 'is_active': True})
        account.is_staff = True
        account.is_active = True
        account.last_name = name
        account.set_password(code)
        account.save()
        person, _created = Employee.objects.get_or_create(
            code=code,
            defaults={
                'name': name, 'position': position, 'organization': self.org, 'user': account,
                'rank': rank, 'status': status, 'gender': '1' if code[-1] in '135' else '2',
                'idcard': '11010119900101%04d' % (abs(hash(code)) % 10000),
                'phone': '1380000%04d' % (abs(hash(code)) % 10000),
                'begin': self.today, 'startday': self.today, 'creator': 'admin',
            },
        )
        person.name = name
        person.position = position
        person.user = account
        person.rank = rank
        person.status = status
        person.save()
        self.people[code] = person

    def _handlers(self):
        rules = (
            ('\u4ed3\u7ba1', 'A02'),
            ('\u8d22\u52a1', 'A03'),
            ('\u8ba1\u5212', 'P05'),
            ('\u85aa\u916c', 'A01'),
            ('\u5408\u540c', 'A02'),
            ('\u5546\u52a1', 'S05'),
            ('\u603b\u7ecf\u7406', 'A05'),
            ('\u4e3b\u7ba1', 'A04'),
            ('\u53d7\u7406', 'P05'),
            ('\u8c03\u5ea6', 'T03'),
            ('\u6279\u51c6', 'A05'),
        )
        for node in Node.objects.filter(stop=False):
            for word, code in rules:
                if word in (node.name or ''):
                    account = self.people[code].user
                    node.users.add(account)
                    break

    def _flows(self):
        self.req = Request(self.user)
        for key, label, mark in KINDS:
            papers = self._papers(label, mark)
            if key == 'ok':
                papers.append(self.people['A05'])
                operation = '1'
            elif key == 'no':
                papers.append(self.people['X01'])
                operation = '3'
            else:
                papers.append(self.people['X02'])
                operation = '4'
            for obj in papers:
                self._walk(obj, operation, label)

    def _papers(self, label, mark):
        title = '\u6d41\u7a0b%s' % label
        later = self.today + datetime.timedelta(days=3)
        project = Project.objects.create(
            code='PJ%s01' % mark, name=title + '\u9879\u76ee', partner=self.customer, status='00', creator='admin')
        po = PurchaseOrder.objects.create(
            code='PO%s901' % mark, partner=self.vendor, org=self.org, user=self.user,
            order_date=self.today, arrive_date=later, title=title + '\u91c7\u8d2d', creator='admin')
        invoice = Invoice.objects.create(
            code='IV%s901' % mark, number='NO%s901' % mark, po=po, vo_amount=Decimal('1.0000'), creator='admin')
        payment = Payment.objects.create(
            code='PY%s901' % mark, po=po, py_amount=Decimal('1.0000'), org=self.org, creator='admin')
        offer = OfferSheet.objects.create(
            code='OF%s901' % mark, partner=self.customer, org=self.org, user=self.user,
            offer_date=self.today, deliver_date=later, title=title + '\u62a5\u4ef7', creator='admin')
        sale = SaleOrder.objects.create(
            code='SO%s901' % mark, partner=self.customer, org=self.org, user=self.user,
            order_date=self.today, deliver_date=later, title=title + '\u9500\u552e', creator='admin')
        collection = PaymentCollection.objects.create(
            code='PC%s901' % mark, so=sale, collection_amount=Decimal('1.00'), org=self.org, creator='admin')
        opening = InitialInventory.objects.create(
            code='IN%s901' % mark, title=title + '\u671f\u521d', user=self.user, org=self.org, creator='admin')
        stock_in = StockIn.objects.create(
            code='SI%s901' % mark, title=title + '\u5165\u5e93', warehouse=self._warehouse(), user=self.user, org=self.org, creator='admin')
        stock_out = StockOut.objects.create(
            code='SOU%s01' % mark, title=title + '\u9886\u6599', user=self.user, org=self.org, creator='admin')
        returned = WareReturn.objects.create(
            code='RT%s901' % mark, title=title + '\u8fd4\u5e93', out=stock_out, user=self.user, org=self.org, creator='admin')
        adjust = WareAdjust.objects.create(
            code='AD%s901' % mark, title=title + '\u8c03\u6574', user=self.user, org=self.org, creator='admin')
        service = ServiceOrder.objects.create(
            code='SW%s01' % mark, title=title + '\u54a8\u8be2', project=project, user=self.user, creator='admin')
        loan = Loan.objects.create(
            code='LN%s01' % mark, title=title + '\u501f\u6b3e', project=project, user=self.user, loan_amount=Decimal('1.00'), creator='admin')
        sheet = Reimbursement.objects.create(
            code='RB%s01' % mark, title=title + '\u62a5\u9500', project=project, user=self.user, creator='admin')
        account, _created = ExpenseAccount.objects.get_or_create(
            code='EX9001', defaults={'name': '\u6a21\u62df\u5200\u5177\u8d39', 'category': 'MU', 'creator': 'admin'})
        from selfhelp.models import ReimbursementItem
        ReimbursementItem.objects.create(reimbursement=sheet, expense_account=account, amount=Decimal('1.00'), memo=label)
        now = datetime.datetime.now()
        activity = Activity.objects.create(
            code='AC%s01' % mark, title=title + '\u4f1a\u8bae', classification='M',
            begin_time=now, end_time=now + datetime.timedelta(hours=1), creator='admin')
        entry = Entry.objects.create(
            code='EM%s01' % mark, name=title + '\u5165\u804c', idcard='00000019900101%04d' % (ord(mark) * 10),
            zipcode='200000', guider=Employee.objects.filter(user=self.user).first() or Employee.objects.order_by('id').first(),
            position=Position.objects.get(code='A01'), creator='admin')
        ticket = DataImport.objects.create(
            title=title + '\u5bfc\u5165', content_type=ContentType.objects.get(app_label='basedata', model='material'),
            creator='admin')
        order = WorkOrder.objects.create(
            title=title + '\u5de5\u5355', material=self._material(), customer=self.customer,
            qty=Decimal('1'), drawing_no=('\u6d41\u7a0b-' + label)[:40], creator='admin')
        outside = OutsourceOrder.objects.create(
            work_order=order, vendor=self.vendor, qty=Decimal('1'), note=(title + '\u5916\u534f')[:120])
        machine = Machine.objects.order_by('id').first()
        repair = None
        if machine is not None:
            repair = MaintainOrder.objects.create(machine=machine, title=title + '\u4fdd\u517b', kind='maintain', note=title)
        assembly = AssemblyOrder.objects.create(
            title=(title + '\u88c5\u914d')[:80], product=self._material(), customer=self.customer, qty=1, note=title)
        rows = [
            project, po, invoice, payment, offer, sale, collection, opening, stock_in, stock_out, returned,
            adjust, service, loan, sheet, activity, entry, ticket, order, outside, assembly,
        ]
        if repair is not None:
            rows.append(repair)
        return rows

    def _warehouse(self):
        from basedata.models import Warehouse
        house = Warehouse.objects.order_by('id').first()
        if house is None:
            house = Warehouse.objects.create(code='RAW', name='\u539f\u6599\u5e93', org=self.org)
        return house

    def _material(self):
        material = Material.objects.filter(code='\u6a21\u62df\u7269\u6599').first()
        if material is None:
            material = Material.objects.create(code='\u6a21\u62df\u7269\u6599', name='\u6cd5\u5170\u76d8', can_sale=True)
        return material

    def _walk(self, obj, operation, label):
        modal = Modal.objects.filter(app_name=obj._meta.app_label, model_name=obj._meta.model_name).first()
        name = modal.name if modal else obj._meta.model_name
        try:
            start_flow(self.req, obj)
            status = None
            for _step in range(6):
                if operation == '1':
                    decide_flow(self.req, obj, '1', '\u6a21\u62df\u540c\u610f')
                else:
                    decide_flow(self.req, obj, operation, '\u6a21\u62df' + label)
                    break
                inst = Instance.objects.filter(modal=modal, object_id=obj.pk).first()
                status = inst.status if inst else None
                if status in (3, 4, 99):
                    break
            inst = Instance.objects.filter(modal=modal, object_id=obj.pk).first()
            self.stdout.write('%s %s -> %s' % (name, label, inst.status if inst else 'none'))
        except Exception as exc:
            self.stdout.write('%s %s \u5931\u8d25 %s' % (name, label, exc))

    def _all_processes(self):
        material = self._material()
        routing = Routing.objects.create(name='\u6a21\u62df\u5168\u5de5\u5e8f\u5de5\u827a', material=material, version='A')
        seq = 10
        for process in Process.objects.order_by('seq', 'id'):
            RoutingStep.objects.create(
                routing=routing, seq=seq, name=process.name, machine_type=process.machine_type,
                unit_min=process.std_minutes or Decimal('5'), outsource=process.outsource)
            seq += 10
        order = WorkOrder.objects.create(
            title='\u5168\u5de5\u5e8f\u6837\u4f8b', material=material, customer=self.customer, routing=routing,
            qty=Decimal('1'), due_date=self.today + datetime.timedelta(days=5),
            drawing_no='\u6a21\u62df-\u5168\u5de5\u5e8f', creator='admin')
        order.release(self.user)
        first = order.operations.order_by('seq', 'id').first()
        if first is not None:
            first.start(self.user, None)
        self.stdout.write('\u5168\u5de5\u5e8f\u5de5\u5355 %s \u5de5\u5e8f %s' % (order.code, order.operations.count()))
