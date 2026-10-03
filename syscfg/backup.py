# coding=utf-8
import os
import shutil
import subprocess
import tempfile

from django.conf import settings
from django.utils import timezone

from syscfg.models import BackupLog


def _hide_secret(text, secret):
    if secret:
        return text.replace(secret, '******')
    return text


def mysqldump_exe():
    base = os.path.join(settings.BASE_DIR, '.mysql')
    if os.path.isdir(base):
        for root, dirs, files in os.walk(base):
            if 'mysqldump.exe' in files:
                return os.path.join(root, 'mysqldump.exe')
    return 'mysqldump'


def dump_database(folder):
    db = settings.DATABASES['default']
    host = db['HOST']
    port = str(db.get('PORT') or 3306)
    name = db['NAME']
    user = db['USER']
    password = db.get('PASSWORD') or ''
    exe = mysqldump_exe()
    handle = tempfile.NamedTemporaryFile('w', suffix='.cnf', delete=False, encoding='utf-8')
    cnf = handle.name
    try:
        handle.write('[client]\n')
        handle.write('host=%s\n' % host)
        handle.write('port=%s\n' % port)
        handle.write('user=%s\n' % user)
        handle.write('password=%s\n' % password.replace('\n', ''))
        handle.close()
        output = os.path.join(folder, '数据库.sql')
        command = [
            exe,
            '--defaults-extra-file=%s' % cnf,
            '--default-character-set=utf8mb4',
            '--single-transaction',
            '--result-file=%s' % output,
            name,
        ]
        completed = subprocess.run(command, capture_output=True, timeout=600)
        if completed.returncode != 0:
            err = (completed.stderr or b'').decode('utf-8', errors='replace')
            raise OSError(_hide_secret(err, password).strip()[:160] or '数据库导出失败')
        if not os.path.isfile(output) or os.path.getsize(output) == 0:
            raise OSError('数据库导出文件是空的')
    finally:
        if os.path.exists(cnf):
            os.remove(cnf)


def copy_files(folder):
    from syscfg.storage import live_root
    source = live_root() or settings.MEDIA_ROOT
    target = os.path.join(folder, '文件')
    if not os.path.isdir(source):
        os.makedirs(target, exist_ok=True)
        return
    os.makedirs(target, exist_ok=True)
    target_abs = os.path.abspath(target)
    for dirpath, dirnames, filenames in os.walk(source):
        current = os.path.abspath(dirpath)
        if current == target_abs or current.startswith(target_abs + os.sep):
            dirnames[:] = []
            continue
        dirnames[:] = [name for name in dirnames if name != '备份']
        relative = os.path.relpath(dirpath, source)
        dest = target if relative == '.' else os.path.join(target, relative)
        os.makedirs(dest, exist_ok=True)
        for name in filenames:
            shutil.copy2(os.path.join(dirpath, name), os.path.join(dest, name))


def prune_old(dest_root, keep):
    if not os.path.isdir(dest_root) or not keep:
        return
    names = []
    for name in os.listdir(dest_root):
        path = os.path.join(dest_root, name)
        if os.path.isdir(path) and len(name) == 15 and name[8] == '-':
            names.append(name)
    names.sort()
    if len(names) <= keep:
        return
    for name in names[:-keep]:
        shutil.rmtree(os.path.join(dest_root, name), ignore_errors=True)


def run_backup(plan):
    started = timezone.now()
    log = BackupLog(plan=plan, status='fail', message='')
    try:
        folder = os.path.join(plan.destination(), started.strftime('%Y%m%d-%H%M%S'))
        os.makedirs(folder, exist_ok=True)
        parts = []
        if plan.include_database:
            dump_database(folder)
            parts.append('数据库已导出')
        if plan.include_files:
            copy_files(folder)
            parts.append('文件已复制')
        if not parts:
            raise OSError('没有选择要备份的内容')
        prune_old(plan.destination(), plan.keep_count)
        log.status = 'ok'
        log.path = folder[:400]
        log.message = '；'.join(parts)[:200]
    except Exception as exc:
        log.status = 'fail'
        log.message = str(exc)[:200] or '备份失败'
    log.finished = timezone.now()
    log.save()
    plan.last_run = log.finished
    plan.last_status = log.status
    plan.last_message = log.message
    plan.save(update_fields=['last_run', 'last_status', 'last_message'])
    return log
