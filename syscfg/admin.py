# coding=utf-8
from django import forms
from django.contrib import admin, messages
from django.conf import settings
from django.forms import ModelForm, DateField
from syscfg.models import *
from common import generic


class SiteForm(ModelForm):
    """

    """
    class Meta:
        model = Site
        fields = '__all__'


class SiteAdmin(admin.ModelAdmin):
    list_per_page = 10
    list_display = ['name', 'begin', 'end']
    fields = (('begin', 'end'), 'name', 'description', 'user')
    filter_horizontal = ['user']
    form = SiteForm


class ModuleAdmin(generic.BOAdmin):
    CODE_NUMBER_WIDTH = 3
    CODE_PREFIX = 'U'
    list_display = ['code', 'name', 'parent', 'status']
    ordering = ['weight']
    raw_id_fields = ['parent']


class MenuAdmin(generic.BOAdmin):
    CODE_NUMBER_WIDTH = 3
    CODE_PREFIX = 'M'

    list_display = ['code', 'name', 'module', 'status']
    list_filter = ['module']
    ordering = ['weight']
    raw_id_fields = ['module']


class RoleAdmin(generic.BOAdmin):
    CODE_NUMBER_WIDTH = 3
    CODE_PREFIX = 'R'
    list_display = ['code', 'name', 'status']
    filter_horizontal = ['users', 'menus']


admin.site.register(Site, SiteAdmin)
admin.site.register(Module, ModuleAdmin)
admin.site.register(Menu, MenuAdmin)
admin.site.register(Role, RoleAdmin)


class KeepPasswordForm(ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field = self.fields.get('password')
        if field is not None:
            field.widget = forms.PasswordInput(render_value=False)
            field.required = False
            if not field.help_text:
                field.help_text = '留空则不修改'

    def clean_password(self):
        value = self.cleaned_data.get('password') or ''
        if not value and getattr(self.instance, 'pk', None):
            return self.instance.password
        return value


class FileServerForm(KeepPasswordForm):
    class Meta:
        model = FileServer
        fields = '__all__'


class DatabaseServerForm(KeepPasswordForm):
    class Meta:
        model = DatabaseServer
        fields = '__all__'


class FileServerAdmin(admin.ModelAdmin):
    form = FileServerForm
    list_display = ['name', 'kind', 'place', 'enabled', 'last_message']
    list_filter = ['kind', 'enabled']
    search_fields = ['name', 'host', 'share']
    readonly_fields = ['last_check', 'last_message']
    actions = ['test_write', 'enable_server', 'sync_files']
    fieldsets = (
        (None, {'fields': ('name', 'kind', 'enabled', 'note')}),
        ('局域网共享', {'fields': ('host', 'share', 'directory', 'username', 'password')}),
        ('检测', {'fields': ('last_check', 'last_message')}),
    )

    @admin.display(description='位置')
    def place(self, obj):
        if obj.kind == 'share' and not ((obj.host or '').strip() and (obj.share or '').strip()):
            return '未填写局域网共享'
        return obj.storage_path()

    @admin.action(description='测试写入')
    def test_write(self, request, queryset):
        from syscfg.fileserver import test_file_server
        for server in queryset:
            ok, message = test_file_server(server)
            self.message_user(request, '%s：%s' % (server.name, message), messages.SUCCESS if ok else messages.ERROR)

    @admin.action(description='测试并启用')
    def enable_server(self, request, queryset):
        from syscfg.fileserver import test_file_server
        if queryset.count() != 1:
            self.message_user(request, '请只选择一台文件服务器', messages.ERROR)
            return
        server = queryset.first()
        ok, message = test_file_server(server)
        if not ok:
            self.message_user(request, '%s：%s' % (server.name, message), messages.ERROR)
            return
        server.enabled = True
        server.save()
        self.message_user(request, '%s 已启用，新上传的文件将写入该位置' % server.name)

    @admin.action(description='同步本机文件')
    def sync_files(self, request, queryset):
        from syscfg.fileserver import sync_local_files
        for server in queryset:
            try:
                message = sync_local_files(server)
                self.message_user(request, '%s：%s' % (server.name, message))
            except Exception as exc:
                text = str(exc)
                if server.password:
                    text = text.replace(server.password, '******')
                self.message_user(request, '%s：%s' % (server.name, text[:160]), messages.ERROR)


class DatabaseServerAdmin(admin.ModelAdmin):
    form = DatabaseServerForm
    list_display = ['name', 'host', 'port', 'db_name', 'user', 'startup', 'in_use', 'last_message']
    search_fields = ['name', 'host', 'db_name']
    readonly_fields = ['last_check', 'last_message']
    actions = ['test_connection', 'use_on_startup']
    fieldsets = (
        (None, {'fields': ('name', 'host', 'port', 'db_name', 'user', 'password', 'startup', 'note')}),
        ('检测', {'fields': ('last_check', 'last_message')}),
    )

    @admin.display(description='正在使用', boolean=True)
    def in_use(self, obj):
        db = settings.DATABASES['default']
        return (
            obj.host == db.get('HOST')
            and str(obj.port) == str(db.get('PORT') or '')
            and obj.db_name == db.get('NAME')
            and obj.user == db.get('USER')
        )

    @admin.action(description='测试连接')
    def test_connection(self, request, queryset):
        from syscfg.fileserver import test_database
        for server in queryset:
            ok, message = test_database(server)
            self.message_user(request, '%s：%s' % (server.name, message), messages.SUCCESS if ok else messages.ERROR)

    @admin.action(description='设为下次启动使用')
    def use_on_startup(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, '请只选择一台数据库', messages.ERROR)
            return
        server = queryset.first()
        server.startup = True
        server.save()
        self.message_user(request, '已写入启动配置。请重启服务后才会改用这台数据库。')


class BackupPlanAdmin(admin.ModelAdmin):
    list_display = ['name', 'include_database', 'include_files', 'keep_count', 'run_hour', 'enabled', 'last_status', 'last_message']
    list_filter = ['enabled']
    readonly_fields = ['last_run', 'last_status', 'last_message']
    actions = ['backup_now']
    fieldsets = (
        (None, {'fields': ('name', 'include_database', 'include_files', 'file_server', 'backup_dir', 'keep_count', 'run_hour', 'enabled', 'note')}),
        ('最近一次', {'fields': ('last_run', 'last_status', 'last_message')}),
    )

    @admin.action(description='立即备份')
    def backup_now(self, request, queryset):
        from syscfg.backup import run_backup
        for plan in queryset:
            log = run_backup(plan)
            text = '%s：%s' % (plan.name, log.message)
            if log.path:
                text = '%s（%s）' % (text, log.path)
            self.message_user(request, text, messages.SUCCESS if log.status == 'ok' else messages.ERROR)


class BackupLogAdmin(admin.ModelAdmin):
    list_display = ['started', 'plan', 'status', 'path', 'message']
    list_filter = ['status', 'plan']
    readonly_fields = ['plan', 'started', 'finished', 'status', 'path', 'message']

    def has_add_permission(self, request):
        return False


admin.site.register(FileServer, FileServerAdmin)
admin.site.register(DatabaseServer, DatabaseServerAdmin)
admin.site.register(BackupPlan, BackupPlanAdmin)
admin.site.register(BackupLog, BackupLogAdmin)
