# coding=utf-8
import os

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _
from common import const
from common import generic
from common.generic import ToStringMixin


class Site(ToStringMixin, models.Model):
    """
    站点，一个站点下可有多个公司，处于同一个站点下的用户逻辑上位于同一个组织
    """
    index_weight = 1
    begin = models.DateField(_('begin date'), blank=True, null=True)
    end = models.DateField(_('end date'), blank=True, null=True)
    # 站点名称
    name = models.CharField(_('site name'), max_length=const.DB_CHAR_NAME_40)
    # 描述信息
    description = models.TextField(_('site description'), blank=True, null=True)
    user = models.ManyToManyField(User, verbose_name=_('administrator'))

    def __unicode__(self):
        return u'%s' % self.name

    class Meta:
        verbose_name = _('Site')
        verbose_name_plural = _('Site')


class Module(generic.BO):
    """
    模块管理
    """
    index_weight = 2
    # 模块编号
    code = models.CharField(_("module code"), max_length=const.DB_CHAR_CODE_6, blank=True, null=True)
    # 模块名称
    name = models.CharField(_("module name"), max_length=const.DB_CHAR_NAME_40)
    # URL
    url = models.URLField(_("module url"), blank=True, null=True, max_length=const.DB_CHAR_NAME_80)
    # 权重
    weight = models.IntegerField(_("weight"), blank=True, null=True, default=99)
    icon = models.CharField(_("style class"), blank=True, null=True, max_length=const.DB_CHAR_NAME_40)
    # 父级
    parent = models.ForeignKey('self', blank=True, null=True, verbose_name=_("parent"), on_delete=models.CASCADE)
    # 是否在用
    status = models.BooleanField(_("in use"), default=True)

    class Meta:
        verbose_name = _("module")
        verbose_name_plural = _("module")


class Menu(generic.BO):
    """
    菜单管理
    """
    index_weight = 3
    # 关联的模块
    module = models.ForeignKey(Module, verbose_name=_("module"), on_delete=models.CASCADE)
    # 编号
    code = models.CharField(_("menu code"), max_length=const.DB_CHAR_CODE_6, blank=True, null=True)
    # 名称
    name = models.CharField(_("menu name"), max_length=const.DB_CHAR_NAME_40)
    # URL
    url = models.URLField(_("menu url"), blank=True, null=True, max_length=const.DB_CHAR_NAME_80)
    # 权重
    weight = models.IntegerField(_("weight"), blank=True, null=True, default=99)
    icon = models.CharField(_("style class"), blank=True, null=True, max_length=const.DB_CHAR_NAME_40)
    status = models.BooleanField(_("in use"), default=True)

    class Meta:
        verbose_name = _("menu")
        verbose_name_plural = _("menu")


class Role(generic.BO):
    """
    角色管理，分配用户所拥有的菜单
    """
    index_weight = 4
    # 角色编号
    code = models.CharField(_("role code"), max_length=const.DB_CHAR_CODE_6, blank=True, null=True)
    # 角色名称
    name = models.CharField(_("role name"), max_length=const.DB_CHAR_NAME_40)
    # 描述
    description = models.CharField(_("description"), max_length=const.DB_CHAR_NAME_80, blank=True, null=True)
    # 是否在用
    status = models.BooleanField(_("in use"), default=True)
    # 父级角色
    parent = models.ForeignKey('self', blank=True, null=True, verbose_name=_("parent"), on_delete=models.CASCADE)
    users = models.ManyToManyField(User, verbose_name=_("role users"), blank=True)
    menus = models.ManyToManyField(Menu, verbose_name=_("role menus"), blank=True)

    class Meta:
        verbose_name = _("role")
        verbose_name_plural = _("role")


class FileServer(ToStringMixin, models.Model):
    """局域网文件服务器。启用后，图纸、程序和附件写入该位置。"""

    index_weight = 5
    KIND = (
        ('local', '本机目录'),
        ('share', '局域网共享'),
    )
    name = models.CharField('名称', max_length=40)
    kind = models.CharField('类型', max_length=10, choices=KIND, default='share')
    host = models.CharField('服务器地址', max_length=80, blank=True, default='', help_text='局域网地址，例如 192.168.1.20')
    share = models.CharField('共享名', max_length=80, blank=True, default='', help_text='文件服务器上已共享的文件夹名')
    directory = models.CharField('目录', max_length=200, blank=True, default='', help_text='共享下的子目录。本机目录则填写完整路径，留空表示本机 upload')
    username = models.CharField('访问账号', max_length=40, blank=True, default='', help_text='留空则使用当前 Windows 登录账号')
    password = models.CharField('访问密码', max_length=80, blank=True, default='')
    enabled = models.BooleanField('启用', default=False, help_text='启用后，新上传的文件写入这里。请先测试写入。')
    last_check = models.DateTimeField('最近检测', blank=True, null=True)
    last_message = models.CharField('检测结果', max_length=200, blank=True, default='')
    note = models.CharField('说明', max_length=200, blank=True, default='')

    class Meta:
        verbose_name = '文件服务器'
        verbose_name_plural = '文件服务器'

    def __str__(self):
        return self.name

    def share_unc(self):
        host = (self.host or '').strip().strip('\\')
        share = (self.share or '').strip().strip('\\/')
        return '\\\\%s\\%s' % (host, share)

    def storage_path(self):
        from django.conf import settings
        if self.kind == 'local':
            return self.directory.strip() or settings.MEDIA_ROOT
        path = self.share_unc()
        sub = (self.directory or '').strip().strip('\\/')
        if sub:
            path = os.path.join(path, sub)
        return path

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.enabled:
            FileServer.objects.exclude(pk=self.pk).update(enabled=False)
        from syscfg.storage import clear_file_root_cache
        clear_file_root_cache()


class DatabaseServer(ToStringMixin, models.Model):
    """数据库所在机器。勾选下次启动后，重启服务才改用这里的连接。"""

    index_weight = 6
    name = models.CharField('名称', max_length=40)
    host = models.CharField('服务器地址', max_length=80, default='127.0.0.1')
    port = models.PositiveIntegerField('端口', default=3306, validators=[MinValueValidator(1), MaxValueValidator(65535)])
    db_name = models.CharField('数据库名', max_length=64)
    user = models.CharField('账号', max_length=40)
    password = models.CharField('密码', max_length=80, blank=True, default='')
    startup = models.BooleanField('下次启动使用', default=False, help_text='勾选并保存后写入启动配置，重启服务才生效')
    last_check = models.DateTimeField('最近检测', blank=True, null=True)
    last_message = models.CharField('检测结果', max_length=200, blank=True, default='')
    note = models.CharField('说明', max_length=200, blank=True, default='')

    class Meta:
        verbose_name = '数据库'
        verbose_name_plural = '数据库'

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        update_fields = kwargs.get('update_fields')
        super().save(*args, **kwargs)
        if update_fields is not None and 'startup' not in update_fields:
            return
        if self.startup:
            DatabaseServer.objects.exclude(pk=self.pk).update(startup=False)
            write_database_file(self)
        elif not DatabaseServer.objects.filter(startup=True).exists():
            remove_database_file()


class BackupPlan(ToStringMixin, models.Model):
    """把数据库和文件备份到文件服务器，并只保留最近若干份。"""

    index_weight = 7
    name = models.CharField('名称', max_length=40)
    include_database = models.BooleanField('备份数据库', default=True)
    include_files = models.BooleanField('备份文件', default=True)
    file_server = models.ForeignKey(
        FileServer, verbose_name='存放位置', blank=True, null=True, on_delete=models.SET_NULL,
        help_text='留空则备份到本机 backup 目录')
    backup_dir = models.CharField('备份目录', max_length=200, blank=True, default='', help_text='留空则使用文件服务器下的「备份」文件夹')
    keep_count = models.PositiveIntegerField('保留份数', default=7, validators=[MinValueValidator(1)])
    run_hour = models.PositiveSmallIntegerField(
        '每天几点', default=2, validators=[MinValueValidator(0), MaxValueValidator(23)],
        help_text='0 到 23。到点执行需要在这台电脑建立计划任务，运行 manage.py run_backup')
    enabled = models.BooleanField('启用', default=False)
    last_run = models.DateTimeField('最近备份', blank=True, null=True)
    last_status = models.CharField('最近结果', max_length=10, blank=True, default='', choices=(
        ('', '未执行'),
        ('ok', '成功'),
        ('fail', '失败'),
    ))
    last_message = models.CharField('最近说明', max_length=200, blank=True, default='')
    note = models.CharField('说明', max_length=200, blank=True, default='')

    class Meta:
        verbose_name = '备份方案'
        verbose_name_plural = '备份方案'

    def __str__(self):
        return self.name

    def destination(self):
        from django.conf import settings
        if self.backup_dir.strip():
            return self.backup_dir.strip()
        if self.file_server_id:
            return os.path.join(self.file_server.storage_path(), '备份')
        return os.path.join(settings.BASE_DIR, 'backup')


class BackupLog(ToStringMixin, models.Model):
    index_weight = 8
    STATUS = (
        ('ok', '成功'),
        ('fail', '失败'),
    )
    plan = models.ForeignKey(BackupPlan, verbose_name='备份方案', on_delete=models.CASCADE)
    started = models.DateTimeField('开始时间', auto_now_add=True)
    finished = models.DateTimeField('结束时间', blank=True, null=True)
    status = models.CharField('结果', max_length=10, choices=STATUS, default='fail')
    path = models.CharField('备份位置', max_length=400, blank=True, default='')
    message = models.CharField('说明', max_length=200, blank=True, default='')

    class Meta:
        verbose_name = '备份记录'
        verbose_name_plural = '备份记录'
        ordering = ['-id']

    def __str__(self):
        return '%s %s' % (self.plan, self.get_status_display())


def database_file_path():
    from django.conf import settings
    return os.path.join(settings.BASE_DIR, 'mis', 'database.local.json')


def write_database_file(server):
    import json
    payload = {
        'host': server.host,
        'port': server.port,
        'name': server.db_name,
        'user': server.user,
        'password': server.password,
    }
    path = database_file_path()
    with open(path, 'w', encoding='utf-8') as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def remove_database_file():
    path = database_file_path()
    if os.path.exists(path):
        os.remove(path)
