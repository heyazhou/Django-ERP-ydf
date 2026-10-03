from django.contrib import admin


class AdminSite(admin.AdminSite):
    site_header = '数控机加工厂生产管理系统'
    site_title = '数控生产'
    index_title = '数控机加工厂'
