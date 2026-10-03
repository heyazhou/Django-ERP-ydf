# coding=utf-8
import os
import time

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible

_cached_root = None
_cached_at = 0


def clear_file_root_cache():
    global _cached_root, _cached_at
    _cached_root = None
    _cached_at = 0


def live_root():
    """已启用且目录存在的文件服务器路径。不可用时返回空，调用方改用本机 upload。"""
    global _cached_root, _cached_at
    now = time.time()
    if _cached_at and now - _cached_at < 15:
        return _cached_root
    root = None
    try:
        from django.apps import apps
        if apps.ready:
            FileServer = apps.get_model('syscfg', 'FileServer')
            server = FileServer.objects.filter(enabled=True).order_by('id').first()
            if server is not None:
                path = server.storage_path()
                if path and os.path.isdir(path):
                    root = os.path.abspath(path)
    except Exception:
        root = None
    _cached_root = root
    _cached_at = now
    return root


@deconstructible(path='syscfg.storage.LanFileStorage')
class LanFileStorage(FileSystemStorage):
    """上传目录跟随已启用的文件服务器，共享不存在时仍写入本机 upload。"""

    def __init__(self, location=None, base_url=None, file_permissions_mode=None,
                 directory_permissions_mode=None, allow_overwrite=False):
        super().__init__(
            location=None,
            base_url=base_url,
            file_permissions_mode=file_permissions_mode,
            directory_permissions_mode=directory_permissions_mode,
            allow_overwrite=allow_overwrite,
        )

    @property
    def location(self):
        return live_root() or os.path.abspath(settings.MEDIA_ROOT)
