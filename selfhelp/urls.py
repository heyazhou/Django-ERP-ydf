from django.urls import re_path
from django.contrib import admin
import selfhelp.views

urlpatterns = [
    re_path(r"^(?P<model>\w+)/(?P<object_id>\d+)/pay$", admin.site.admin_view(selfhelp.views.pay_action)),
]
