# coding=utf-8
from django.contrib import admin
from django.forms import models
from django.forms import fields, TextInput, Textarea
from django.contrib import messages
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.contrib.contenttypes.admin import GenericTabularInline
from common import generic
from cnc.models import FaceSample, ObjectSample
from basedata.models import ValueList, ValueListItem, Address, Partner, BankAccount, Project, Measure, Material, Brand,\
    Category, Warehouse, TechnicalParameterName, TechnicalParameterValue, Trade, ExpenseAccount, Employee, Family, Education,\
    WorkExperience, ExtraParam, DataImport, Document


class ValueListItemInline(admin.TabularInline):
    model = ValueListItem
    exclude = ['group_code']

    def get_extra(self, request, obj=None, **kwargs):
        if obj:
            return 0
        else:
            return 3


class ValueListAdmin(generic.BOAdmin):
    """值列表"""

    CODE_NUMBER_WIDTH = 3
    CODE_PREFIX = 'S'
    list_display = ['code', 'name', 'module', 'status']
    fields = (('code',),
              ('name',),
              ('module',),
              ('status', 'init', 'locked',),
              ('locked_by', 'lock_time',))
    raw_id_fields = ['module']
    readonly_fields = ['locked_by', 'lock_time']
    inlines = [ValueListItemInline]
    search_fields = ['code', 'name']

    def save_model(self, request, obj, form, change):
        super(ValueListAdmin, self).save_model(request, obj, form, change)
        # 更新 值列表选项 的 group_code 属性
        # 似乎与 ValueList.save() 覆写的方法功能重复了
        obj.valuelistitem_set.update(group_code=obj.code)


class AddressAdmin(generic.BOAdmin):
    list_display = ['address', 'phone', 'contacts']
    exclude = [
        'content_type',
        'object_id',
        'creator',
        'modifier',
        'creation',
        'modification',
        'begin',
        'end']


class AddressInline(GenericTabularInline):
    model = Address
    exclude = [
        'content_type',
        'object_id',
        'creator',
        'modifier',
        'creation',
        'modification',
        'begin',
        'end']
    extra = 1


class BankAccountInline(admin.TabularInline):
    model = BankAccount
    fields = ['account', 'title', 'memo']

    def get_extra(self, request, obj=None, **kwargs):
        if obj:
            return 0
        else:
            return 1


class PartnerForm(models.ModelForm):
    tax_address = fields.CharField(widget=TextInput(attrs={'size': 119, }), required=False, label=_("tax address"))
    memo = fields.CharField(widget=Textarea(attrs={'rows': 3, 'cols': 85}), required=False, label=_("memo"))

    class Meta:
        model = Partner
        fields = '__all__'


class PartnerAdmin(generic.BOAdmin):
    list_display = ['code', 'name', 'partner_type', 'level']
    list_display_links = ['code', 'name']

    fields = (('code', 'name',),
              ('short', 'pinyin',),
              ('partner_type', 'level'),
              ('tax_num', 'tax_account',),
              ('tax_address',),
              ('contacts', 'phone',),
              ('memo',),)
    search_fields = ['code', 'name', 'pinyin']
    form = PartnerForm
    save_on_top = True
    inlines = [AddressInline, BankAccountInline]

    def get_queryset(self, request):
        if request.user.is_superuser or (
                request.user.has_perm('basedate.view_all_customer') and request.user.has_perm('basedate.view_all_supplier')):
            return super(PartnerAdmin, self).get_queryset(request)
        elif request.user.has_perm('basedata.view_all_customer'):
            return super(PartnerAdmin, self).get_queryset(request).filter(partner_type='C')
        else:
            return super(PartnerAdmin, self).get_queryset(request).filter(partner_type='S')


class ProjectForm(models.ModelForm):
    income = fields.DecimalField(required=False, widget=TextInput(attrs={'readonly': 'true'}))
    expand = fields.DecimalField(required=False, widget=TextInput(attrs={'readonly': 'true'}))

    class Meta:
        model = Project
        fields = '__all__'


class ProjectAdmin(generic.BOAdmin):
    CODE_PREFIX = 'PJ'
    list_display = ['code', 'name', 'status', 'income', 'expand']
    list_display_links = ['code', 'name']
    fields = (
        ('code', 'name',),
        ('short', 'pinyin',),
        ('partner',),
        ('status', 'prj_type',),
        ('description',),
        ('budget', 'income', 'expand',),
        ('blueprint',),
        ('offer',),
        ('business',),
        ('users',),
    )
    search_fields = ['code', 'name']
    readonly_fields = ['status']
    raw_id_fields = ['partner']
    filter_horizontal = ['users']
    form = ProjectForm


class WarehouseAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'location']
    filter_horizontal = ['users']

    def save_model(self, request, obj, form, change):
        super(WarehouseAdmin, self).save_model(request, obj, form, change)
        try:
            code = getattr(obj, 'code')
            if not code:
                obj.code = '%s%02d' % ('A', obj.id)
                obj.save()
        except Exception as e:
            self.message_user(request, 'ERROR:%s' % e, level=messages.ERROR)


class BrandAdmin(admin.ModelAdmin):
    list_display = ['name', 'pinyin']


class MeasureAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'status']


class CategoryAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'path']

    def save_model(self, request, obj, form, change):
        super(CategoryAdmin, self).save_model(request, obj, form, change)
        try:
            code = getattr(obj, 'code')
            if not code:
                obj.code = '%s%02d' % ('F', obj.id)
                obj.save()
            if obj.parent:
                if obj.parent.path:
                    obj.path = obj.parent.path + '/' + obj.parent.name
                else:
                    obj.path = obj.parent.name
                obj.save()
        except Exception as e:
            self.message_user(request, 'ERROR:%s' % e, level=messages.ERROR)


class MaterialForm(models.ModelForm):
    name = fields.CharField(widget=TextInput(attrs={"size": "119"}), label=_("material name"))
    spec = fields.CharField(widget=TextInput(attrs={"size": "119"}), required=False, label=_("specifications"))

    class Mata:
        model = Material
        fields = '__all__'


class ExtraParamInline(admin.TabularInline):
    model = ExtraParam
    fields = ['name', 'data_type', 'data_source']

    def get_extra(self, request, obj=None, **kwargs):
        if obj:
            return 0
        else:
            return 1


def identity_qr(obj):
    token = getattr(obj, 'qr_token', None) if obj is not None else None
    if not token:
        return '保存后生成二维码，可打印或喷涂'
    return format_html(
        '<img src="/m/qr/{}/" alt="二维码" width="180" height="180">'
        '<div>{}</div>',
        token, token,
    )


class FaceTrainInline(admin.TabularInline):
    model = FaceSample
    fields = ('photo',)
    extra = 1
    verbose_name = '人脸训练照片'
    verbose_name_plural = '人脸训练照片'

    def get_queryset(self, request):
        return super(FaceTrainInline, self).get_queryset(request).exclude(origin='profile')


class ObjectTrainInline(admin.TabularInline):
    model = ObjectSample
    fields = ('photo',)
    extra = 1
    verbose_name = '物体训练照片'
    verbose_name_plural = '物体训练照片'

    def get_queryset(self, request):
        return super(ObjectTrainInline, self).get_queryset(request).exclude(origin='profile')


class MaterialAdmin(generic.BOAdmin):
    CODE_PREFIX = 'IT'
    CODE_NUMBER_WIDTH = 5
    list_display = ['code', 'name', 'spec', 'tp']
    list_display_links = ['code', 'name']
    list_filter = ['brand', 'tp']
    search_fields = ['code', 'name']
    fields = (
        ('code', 'barcode', 'qr_token'),
        ('name',),
        ('supply_kind', 'photo'),
        ('drawing_file', 'model_file'),
        ('qr_preview', 'train_status'),
        ('spec',),
        ('brand',),
        ('category',),
        ('status', 'is_equip', 'can_sale', 'is_virtual',),
        ('warehouse',),
        ('tp',),
        ('measure',),
        ('stock_price', 'purchase_price', 'sale_price',),
    )
    filter_horizontal = ['measure']
    readonly_fields = ['qr_token', 'qr_preview', 'train_status']
    inlines = [ObjectTrainInline, ExtraParamInline]
    form = MaterialForm

    def qr_preview(self, obj):
        return identity_qr(obj)
    qr_preview.short_description = '可打印二维码'

    def train_status(self, obj):
        from cnc.trainer import status_text
        return status_text()
    train_status.short_description = '本地模型'

    def save_formset(self, request, form, formset, change):
        if formset.model is ObjectSample:
            for inline_form in formset.forms:
                if getattr(inline_form, 'changed_data', None) and 'photo' in inline_form.changed_data:
                    inline_form.instance.feature = ''
        super(MaterialAdmin, self).save_formset(request, form, formset, change)
        if formset.model is ObjectSample:
            from cnc.trainer import complete_samples, object_embed
            skipped = complete_samples(ObjectSample, 'material', form.instance, object_embed)
            if skipped:
                messages.warning(request, '有 %s 张物体训练照片无法读取，未纳入训练' % skipped)

    def save_related(self, request, form, formsets, change):
        photo_changed = (not change) or ('photo' in form.changed_data)
        sample_changed = any(item.model is ObjectSample and item.has_changed() for item in formsets)
        super(MaterialAdmin, self).save_related(request, form, formsets, change)
        if not (photo_changed or sample_changed):
            return
        from cnc.trainer import refresh_profile_object, train_objects
        if photo_changed:
            refresh_profile_object(form.instance)
        messages.success(request, train_objects())


class TechParamValueInline(admin.TabularInline):
    model = TechnicalParameterValue


class TechParamNameAdmin(admin.ModelAdmin):
    list_display = ['name', 'category']
    inlines = [TechParamValueInline]


class TradeAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'parent']


class ExpenseAdmin(generic.BOAdmin):
    CODE_PREFIX = 'FC'
    list_display = ['code', 'name', 'category']
    list_display_links = ['code', 'name']
    list_filter = ['category']
    search_fields = ['name']


class FamilyForm(models.ModelForm):
    name = fields.CharField(widget=TextInput(attrs={"size": "25"}), label=_("name"))
    phone = fields.CharField(widget=TextInput(attrs={"size": "25"}), label=_("phone"))

    class Meta:
        model = Family
        fields = '__all__'


class FamilyInline(admin.TabularInline):
    model = Family
    exclude = [
        'creator',
        'modifier',
        'creation',
        'modification',
        'begin',
        'end']
    form = FamilyForm
    extra = 1


class EducationInline(admin.TabularInline):
    model = Education
    exclude = ['creator', 'modifier', 'creation', 'modification']
    extra = 0


class WorkExperienceInline(admin.TabularInline):
    model = WorkExperience
    exclude = ['creator', 'modifier', 'creation', 'modification']
    extra = 1


class EmployeeAdmin(generic.BOAdmin):
    CODE_PREFIX = '1'
    list_display = [
        'code',
        'name',
        'position',
        'gender',
        'idcard',
        'age',
        'work_age',
        'literacy',
        'phone',
        'email']
    search_fields = ['code', 'name', 'idcard', 'pinyin']
    fieldsets = [
        (None, {'fields': [
            ('code', 'phone',),
            ('name', 'pinyin',),
            ('photo', 'qr_token'),
            ('qr_preview', 'train_status'),
            ('gender', 'birthday',),
            ('idcard', 'country',),
            ('position',),
            ('rank', 'category'),
            ('status', 'ygxs',),
            ('workday', 'startday',)
        ]}),
        (_('other info'), {'fields': [
            ('hometown', 'address',),
            ('banknum', 'bankname',),
            ('email', 'office',),
            ('emergency', 'literacy',),
            ('religion', 'marital',),
            ('party', 'nation',),
            ('spjob', 'health',),
            ('major', 'degree',),
            ('tag1', 'tag2',),
            ('tag3', 'tag4',), ('user',),
        ], 'classes':['collapse']}),
    ]
    readonly_fields = ['status', 'ygxs', 'rank', 'category']
    inlines = [FaceTrainInline, FamilyInline, EducationInline, WorkExperienceInline]
    raw_id_fields = ['user']

    def get_queryset(self, request):
        if request.user.is_superuser or request.user.has_perm(
                'basedata.view_all_employee'):
            return super(EmployeeAdmin, self).get_queryset(request)
        else:
            return super(EmployeeAdmin, self).get_queryset(request).filter(user=request.user)

    def qr_preview(self, obj):
        return identity_qr(obj)
    qr_preview.short_description = '可打印二维码'

    def train_status(self, obj):
        from cnc.trainer import status_text
        return status_text()
    train_status.short_description = '本地模型'

    def save_formset(self, request, form, formset, change):
        if formset.model is FaceSample:
            for inline_form in formset.forms:
                if getattr(inline_form, 'changed_data', None) and 'photo' in inline_form.changed_data:
                    inline_form.instance.feature = ''
        super(EmployeeAdmin, self).save_formset(request, form, formset, change)
        if formset.model is FaceSample:
            from cnc.trainer import complete_samples, face_embed
            skipped = complete_samples(FaceSample, 'employee', form.instance, face_embed)
            if skipped:
                messages.warning(request, '有 %s 张训练照片没有正脸，未纳入人脸模型' % skipped)

    def save_related(self, request, form, formsets, change):
        photo_changed = (not change) or ('photo' in form.changed_data)
        sample_changed = any(item.model is FaceSample and item.has_changed() for item in formsets)
        super(EmployeeAdmin, self).save_related(request, form, formsets, change)
        if not (photo_changed or sample_changed):
            return
        from cnc.trainer import refresh_profile_face, train_faces
        if photo_changed:
            status = refresh_profile_face(form.instance)
            if status == 'empty':
                messages.warning(request, '这张照片里没有找到正脸，人脸未进入本地模型。请换一张正对镜头的照片。')
        messages.success(request, train_faces())

    def get_readonly_fields(self, request, obj=None):
        if request.user.is_superuser:
            return ['qr_token', 'qr_preview', 'train_status']
        else:
            return ['qr_token', 'qr_preview', 'train_status', 'status', 'ygxs', 'rank', 'category', 'position', 'user']


class DataImportAdmin(generic.BOAdmin):
    """数据导入"""

    list_display = ['imp_date', 'title', 'status']
    list_display_links = ['imp_date', 'title']
    raw_id_fields = ['content_type']
    readonly_fields = ['status']
    extra_buttons = [{'href': 'action', 'title': _('import')}]

    def changeform_view(
            self,
            request,
            object_id=None,
            form_url='',
            extra_context=None):
        if object_id:
            obj = DataImport.objects.get(id=object_id)
            if obj.status == '1':
                extra_context = extra_context or {}
                extra_context.update(dict(readonly=True))
        return super(DataImportAdmin, self).changeform_view(request, object_id, form_url, extra_context)


class DocumentForm(models.ModelForm):
    title = fields.CharField(widget=TextInput(attrs={"size": "119"}), label=_("title"))
    keywords = fields.CharField(widget=TextInput(attrs={"size": "119"}), label=_("keywords"))

    class Meta:
        model = Document
        fields = '__all__'


class DocumentAdmin(generic.BOAdmin):
    CODE_PREFIX = 'FD'
    CODE_NUMBER_WIDTH = 4
    list_display = [
        'code',
        'title',
        'keywords',
        'tp',
        'business_domain',
        'status',
        'creation']
    list_display_links = ['code', 'title']
    fields = (('code', 'status',), ('title',), ('keywords',),
              ('description',), ('business_domain', 'tp',), ('attach',))
    readonly_fields = ['status']
    list_filter = ['tp', 'business_domain']
    search_fields = ['title', 'keywords', 'code']
    form = DocumentForm
    actions = ['publish']
    date_hierarchy = 'begin'

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.status == '1':
            return [
                'code',
                'status',
                'title',
                'keywords',
                'description',
                'business_domain',
                'tp',
                'attach',
            ]
        else:
            return ['status']

    def publish(self, request, queryset):
        import datetime
        cnt = queryset.filter(status='0').update(status='1', pub_date=datetime.datetime.now())
        self.message_user(request, u'%s 个文档发布成功' % cnt)

    publish.short_description = _('publish selected %(verbose_name_plural)s')


# admin.site.register(Address,AddressAdmin)
admin.site.register(ValueList, ValueListAdmin)
admin.site.register(Partner, PartnerAdmin)
admin.site.register(Project, ProjectAdmin)
admin.site.register(Material, MaterialAdmin)
admin.site.register(Warehouse, WarehouseAdmin)
admin.site.register(Brand, BrandAdmin)
admin.site.register(Measure, MeasureAdmin)
admin.site.register(Category, CategoryAdmin)
admin.site.register(TechnicalParameterName, TechParamNameAdmin)
admin.site.register(Trade, TradeAdmin)
admin.site.register(ExpenseAccount, ExpenseAdmin)
admin.site.register(Employee, EmployeeAdmin)
admin.site.register(DataImport, DataImportAdmin)
admin.site.register(Document, DocumentAdmin)
