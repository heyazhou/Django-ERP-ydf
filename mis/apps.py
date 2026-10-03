from django.contrib.admin.apps import AdminConfig


class MisAdminConfig(AdminConfig):
    default_site = 'mis.admin.AdminSite'

    def ready(self):
        super().ready()
        from mis.chinese import apply_chinese_labels
        apply_chinese_labels()
        from django.contrib import admin
        from django.contrib.auth.models import User
        user_admin = admin.site._registry.get(User)
        if user_admin is not None:
            user_admin.list_display = ('last_name', 'first_name', 'is_staff', 'is_superuser')
