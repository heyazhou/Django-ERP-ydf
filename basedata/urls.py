from django.urls import re_path
from django.contrib import admin
import basedata.views

urlpatterns = [
    re_path(r"^dataimport/(?P<object_id>\d+)/action$", admin.site.admin_view(basedata.views.action_import)),
]
