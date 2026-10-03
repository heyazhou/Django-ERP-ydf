from django.urls import re_path
from django.contrib import admin
import invent.views

urlpatterns = [
    re_path(r"^stockin/(?P<object_id>\d+)/cin$", admin.site.admin_view(invent.views.action_in)),
    re_path(r"^initialinventory/(?P<object_id>\d+)/cin$", admin.site.admin_view(invent.views.action_init)),
    re_path(r"^stockout/(?P<object_id>\d+)/out$", admin.site.admin_view(invent.views.action_out)),
    re_path(r"^warereturn/(?P<object_id>\d+)/cin$", admin.site.admin_view(invent.views.action_return)),
    re_path(r"^wareadjust/(?P<object_id>\d+)/adjust$", admin.site.admin_view(invent.views.action_adjust)),
]
