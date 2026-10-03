# coding=utf-8
import os
import shutil
import subprocess

from django.conf import settings
from django.utils import timezone


def _decode(data):
    if not data:
        return ''
    return data.decode('gbk', errors='replace')


def _hide_secret(text, secret):
    if secret:
        return text.replace(secret, '******')
    return text


def connect_share(server):
    """用访问账号连接局域网共享。已经连上则直接使用。"""
    if server.kind != 'share' or not server.username:
        return
    unc = server.share_unc()
    command = ['net', 'use', unc, server.password or '', '/user:%s' % server.username, '/persistent:yes']
    completed = subprocess.run(command, capture_output=True, stdin=subprocess.DEVNULL, timeout=20)
    if completed.returncode == 0 or os.path.isdir(unc):
        return
    text = _hide_secret(_decode(completed.stdout) + _decode(completed.stderr), server.password)
    raise OSError(text.strip()[:160] or '无法连接共享')


def _require_share(server):
    if server.kind == 'share' and not ((server.host or '').strip() and (server.share or '').strip()):
        raise OSError('请先填写服务器地址和共享名')


def test_file_server(server):
    message = '可以写入'
    try:
        _require_share(server)
        connect_share(server)
        path = server.storage_path()
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, '.写入检测')
        with open(probe, 'w', encoding='utf-8') as handle:
            handle.write('ok')
        os.remove(probe)
        if not server.enabled:
            message = '可以写入。勾选启用后，新文件将保存到这里'
    except Exception as exc:
        message = '失败：' + _hide_secret(str(exc), server.password)[:160]
        server.last_check = timezone.now()
        server.last_message = message[:200]
        server.save(update_fields=['last_check', 'last_message'])
        return False, message
    server.last_check = timezone.now()
    server.last_message = message[:200]
    server.save(update_fields=['last_check', 'last_message'])
    return True, message


def sync_local_files(server):
    """把本机 upload 复制到文件服务器，不删除本机文件。"""
    _require_share(server)
    connect_share(server)
    source = settings.MEDIA_ROOT
    target = server.storage_path()
    if os.path.abspath(source) == os.path.abspath(target):
        return '文件已在本机目录'
    if not os.path.isdir(source):
        return '本机还没有上传文件'
    os.makedirs(target, exist_ok=True)
    copied = 0
    for dirpath, dirnames, filenames in os.walk(source):
        relative = os.path.relpath(dirpath, source)
        folder = target if relative == '.' else os.path.join(target, relative)
        os.makedirs(folder, exist_ok=True)
        for name in filenames:
            shutil.copy2(os.path.join(dirpath, name), os.path.join(folder, name))
            copied += 1
    return '已复制 %s 个文件，本机文件仍保留' % copied


def test_database(server):
    import MySQLdb
    message = '可以连接'
    try:
        connection = MySQLdb.connect(
            host=server.host,
            port=int(server.port),
            user=server.user,
            passwd=server.password or '',
            db=server.db_name,
            connect_timeout=5,
            charset='utf8mb4',
        )
        cursor = connection.cursor()
        cursor.execute('SELECT 1')
        cursor.close()
        connection.close()
    except Exception as exc:
        message = '失败：' + _hide_secret(str(exc), server.password)[:160]
        server.last_check = timezone.now()
        server.last_message = message[:200]
        server.save(update_fields=['last_check', 'last_message'])
        return False, message
    server.last_check = timezone.now()
    server.last_message = message[:200]
    server.save(update_fields=['last_check', 'last_message'])
    return True, message
