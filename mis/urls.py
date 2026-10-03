from django.urls import include, re_path
from django.conf.urls.static import static
from django.contrib import admin
from mis import settings
from syscfg.views import serve_upload
import workflow.views
import invent.urls
import basedata.urls
import selfhelp.urls
import mis.views
import cnc.urls

urlpatterns = [
    re_path(r'^$', mis.views.home),
    re_path(r'^m/', include(cnc.urls)),
    re_path(r"^admin/(?P<app>\w+)/(?P<model>\w+)/(?P<object_id>\d+)/change/start$", admin.site.admin_view(workflow.views.start)),
    re_path(r"^admin/(?P<app>\w+)/(?P<model>\w+)/(?P<object_id>\d+)/change/approve/(?P<operation>\d+)$", admin.site.admin_view(workflow.views.approve)),
    re_path(r"^admin/(?P<app>\w+)/(?P<model>\w+)/(?P<object_id>\d+)/change/restart/(?P<instance>\d+)$", admin.site.admin_view(workflow.views.restart)),
    re_path(r'^admin/invent/', include(invent.urls)),
    re_path(r'^admin/basedata/', include(basedata.urls)),
    re_path(r'^admin/selfhelp/', include(selfhelp.urls)),
    re_path(r'^admin/', admin.site.urls),
]
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
if settings.DEBUG:
    urlpatterns += [
        re_path(r'^upload/(?P<path>.*)$', serve_upload),
    ]
