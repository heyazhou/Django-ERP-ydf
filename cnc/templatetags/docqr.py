from django import template

from cnc.qrutil import ensure_token

register = template.Library()


_NO_QR = {
    'syscfg.fileserver',
    'syscfg.databaseserver',
    'syscfg.backupplan',
    'syscfg.backuplog',
    'quality.controlpoint',
    'quality.standarditem',
    'quality.measure',
    'quality.defect',
    'cnc.facesample',
    'cnc.objectsample',
}


@register.inclusion_tag('admin/includes/doc_qr.html')
def document_qr(original):
    if original is None or not getattr(original, 'pk', None):
        return {'token': ''}
    label = '%s.%s' % (original._meta.app_label, original._meta.model_name)
    if label in _NO_QR or getattr(original, 'qr_token', None):
        return {'token': ''}
    return {'token': ensure_token(original)}
