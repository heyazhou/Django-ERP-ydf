# coding=utf-8
from django.conf import settings
from django.views.static import serve


def serve_upload(request, path):
    """按当前文件服务器目录提供 /upload/ 下的文件。"""
    from syscfg.storage import live_root
    root = live_root() or settings.MEDIA_ROOT
    return serve(request, path, document_root=root)
