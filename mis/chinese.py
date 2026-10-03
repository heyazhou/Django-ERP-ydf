# -*- coding: utf-8 -*-
"""把仍显示为英文的模型名、字段名改成中文。"""


LABELS = {
    'activity': '活动',
    'app label': '应用',
    'content type': '内容类型',
    'creation': '创建时间',
    'employee departure': '离职',
    'employee departures': '离职',
    'employee transfer': '调动',
    'employee transfers': '调动',
    'enroll': '报名',
    'enrolls': '报名',
    'feedback': '反馈',
    'feedbacks': '反馈',
    'group code': '分组编号',
    'in out detail': '出入库明细',
    'in out details': '出入库明细',
    'inoutdetail ptr': '出入库明细',
    'master': '主单',
    'material': '物料',
    'material parameter': '物料参数',
    'object id': '对象编号',
    'param name': '参数名',
    'param value': '参数值',
    'user': '用户',
    'accept enroll': '接受报名',
    'answer': '答复',
    'create time': '创建时间',
    'enroll deadline': '报名截止',
    'enroll time': '报名时间',
    'entry count': '入库数量',
    'entry status': '入库状态',
    'event time': '业务时间',
    'executed': '已执行',
    'feedback time': '反馈时间',
    'is clear': '已结清',
    'is in stock': '已入库',
    'left count': '剩余数量',
    'pay time': '付款时间',
    'pay user': '付款人',
    'publish date': '发布日期',
    'publish time': '发布时间',
    'rank': '等级',
    'size': '大小',
    'suggest': '意见',
    'technical name': '技术参数',
    'wo item': '工单明细',
    'workorder': '工单',
    'DROP': '作废',
    'ALREADY STOCK IN': '已入库',
    'ALREADY STOCK OUT': '已出库',
    'ID': '编号',
}

_APPLIED = False


def _localize(value):
    shown = str(value)
    return LABELS.get(shown, value)


def _record_text(self):
    for attr in ('name', 'title', 'code', 'material'):
        value = getattr(self, attr, None)
        if value not in (None, ''):
            return str(value)
    return '记录%s' % self.pk


def apply_chinese_labels():
    global _APPLIED
    if _APPLIED:
        return
    from django.apps import apps
    from django.db.models import Model

    for model in apps.get_models():
        if model.__str__ is Model.__str__:
            model.__str__ = _record_text
        model._meta.verbose_name = _localize(model._meta.verbose_name)
        model._meta.verbose_name_plural = _localize(model._meta.verbose_name_plural)
        for field in model._meta.get_fields():
            if not hasattr(field, 'verbose_name'):
                continue
            field.verbose_name = _localize(field.verbose_name)
            choices = getattr(field, 'choices', None)
            if not choices or callable(choices):
                continue
            updated = []
            changed = False
            for item in choices:
                if isinstance(item, (list, tuple)) and len(item) == 2:
                    label = _localize(item[1])
                    changed = changed or label != item[1]
                    updated.append((item[0], label))
                else:
                    updated.append(item)
            if changed:
                field.choices = updated
                field.__dict__.pop('flatchoices', None)
    _APPLIED = True
