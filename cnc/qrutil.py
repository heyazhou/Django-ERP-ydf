from django.conf import settings


TRACKED_MODELS = (
    ('WO', 'cnc.WorkOrder'),
    ('OP', 'cnc.WorkOperation'),
    ('MC', 'cnc.Machine'),
    ('TL', 'cnc.Tool'),
    ('FX', 'cnc.Fixture'),
    ('LT', 'cnc.MaterialLot'),
    ('QC', 'cnc.Inspection'),
    ('NC', 'cnc.NcProgram'),
    ('DR', 'cnc.Drawing'),
    ('OS', 'cnc.OutsourceOrder'),
    ('RT', 'cnc.Routing'),
    ('AR', 'cnc.ShopArea'),
    ('AB', 'cnc.AssemblyBom'),
    ('AO', 'cnc.AssemblyOrder'),
    ('AU', 'cnc.AssemblyUnit'),
    ('MN', 'cnc.MaintainOrder'),
    ('QM', 'quality.CheckRecord'),
    ('QS', 'quality.Standard'),
    ('EM', 'basedata.Employee'),
    ('MT', 'basedata.Material'),
)


def public_base(request):
    configured = getattr(settings, 'CNC_BASE_URL', '') or ''
    configured = configured.strip().rstrip('/')
    if configured:
        return configured
    return request.build_absolute_uri('/').rstrip('/')


def object_url(request, token):
    return '%s/m/q/%s/' % (public_base(request), token)


def ensure_token(obj):
    """CNC 对象用自己的码，其余后台单据生成 ZZ 码。"""
    own = getattr(obj, 'qr_token', None)
    if own:
        return own
    if not getattr(obj, 'pk', None):
        return None
    from django.contrib.contenttypes.models import ContentType
    from cnc.models import DocLink
    content_type = ContentType.objects.get_for_model(obj.__class__)
    link, _created = DocLink.objects.get_or_create(
        content_type=content_type,
        object_id=obj.pk,
        defaults={'token': 'ZZ%s-%s' % (content_type.pk, obj.pk)},
    )
    return link.token


def object_for_doc_token(token):
    from cnc.models import DocLink
    link = DocLink.objects.filter(token=token).select_related('content_type').first()
    if link is None and token.startswith('ZZ') and '-' in token:
        content_id, object_id = token[2:].split('-', 1)
        if content_id.isdigit() and object_id.isdigit():
            link = DocLink.objects.filter(
                content_type_id=int(content_id), object_id=int(object_id)).first()
    if link is None:
        return None
    model = link.content_type.model_class()
    if model is None:
        return None
    return model.objects.filter(pk=link.object_id).first()


def find_by_token(token):
    from django.apps import apps
    token = (token or '').strip()
    if not token:
        return None
    if token.startswith('ZZ'):
        return object_for_doc_token(token)
    prefix = token[:2].upper()
    for code, label in TRACKED_MODELS:
        if prefix == code:
            model = apps.get_model(label)
            found = model.objects.filter(qr_token=token).first()
            if found is not None:
                return found
    from cnc.models import Tracked
    for model in Tracked.__subclasses__():
        found = model.objects.filter(qr_token=token).first()
        if found:
            return found
    from basedata.models import Employee, Material
    found = Material.objects.filter(barcode=token).exclude(barcode__isnull=True).exclude(barcode='').first()
    if found is not None:
        return found
    for model, field in (
        (Employee, 'code'),
        (Material, 'code'),
    ):
        found = model.objects.filter(**{field: token}).first()
        if found is not None:
            return found
    return None


def log_event(token, action, summary, user):
    from cnc.models import ShopEvent
    ShopEvent.objects.create(
        token=(token or '')[:32],
        action=(action or '')[:20],
        summary=(summary or '')[:200],
        user=user if getattr(user, 'is_authenticated', False) else None,
    )
