# coding=utf-8
import os

import cv2
import numpy as np
from django.core.files.base import ContentFile

from cnc.vision import (
    FACE_MATCH, OBJECT_MATCH, dump_vector, face_vector, load_vector, object_vector, read_image,
)

_DIR = os.path.join(os.path.dirname(__file__), 'data')
FACE_FILE = os.path.join(_DIR, 'face_trained.npz')
OBJECT_FILE = os.path.join(_DIR, 'object_trained.npz')
_CACHE = {}


def _views(image):
    if image is None:
        return []
    return [image, cv2.flip(image, 1)]


def _mean_vector(extractor, image):
    vectors = []
    for item in _views(image):
        vector = extractor(item)
        if vector is not None:
            vectors.append(vector)
    if not vectors:
        return None
    mean = np.mean(np.stack(vectors), axis=0).astype('float32')
    norm = float(np.linalg.norm(mean))
    if norm == 0:
        return None
    return mean / norm


def face_embed(image):
    return _mean_vector(face_vector, image)


def object_embed(image):
    return _mean_vector(object_vector, image)


def _read_photo(field):
    field.open('rb')
    try:
        return field.read()
    finally:
        field.close()


def _store_profile(model, owner_field, owner, photo_field, embed):
    model.objects.filter(**{owner_field: owner, 'origin': 'profile'}).delete()
    photo = getattr(owner, photo_field)
    if not photo:
        return 'cleared'
    image = read_image(_read_photo(photo))
    vector = embed(image)
    if vector is None:
        return 'empty'
    sample = model(**{owner_field: owner, 'feature': dump_vector(vector), 'origin': 'profile'})
    sample.photo.save(photo.name.rsplit('/', 1)[-1] or 'sample.jpg', ContentFile(_read_photo(photo)), save=True)
    return 'ok'


def refresh_profile_face(employee):
    from cnc.models import FaceSample
    return _store_profile(FaceSample, 'employee', employee, 'photo', face_embed)


def refresh_profile_object(material):
    from cnc.models import ObjectSample
    return _store_profile(ObjectSample, 'material', material, 'photo', object_embed)


def complete_samples(model, owner_field, owner, embed):
    skipped = 0
    for sample in model.objects.filter(**{owner_field: owner, 'feature': ''}):
        if not sample.photo:
            sample.delete()
            continue
        vector = embed(read_image(_read_photo(sample.photo)))
        if vector is None:
            sample.delete()
            skipped += 1
            continue
        sample.feature = dump_vector(vector)
        sample.origin = sample.origin or 'train'
        sample.save(update_fields=['feature', 'origin'])
    return skipped


def _write(path, groups, threshold):
    _CACHE.pop(path, None)
    if not groups:
        if os.path.exists(path):
            os.remove(path)
        return 0, 0
    labels = []
    vectors = []
    photos = 0
    for label, rows in groups.items():
        photos += len(rows)
        mean = np.mean(np.stack(rows), axis=0).astype('float32')
        norm = float(np.linalg.norm(mean))
        if norm == 0:
            continue
        labels.append(int(label))
        vectors.append(mean / norm)
    if not labels:
        if os.path.exists(path):
            os.remove(path)
        return 0, 0
    np.savez(
        path,
        labels=np.asarray(labels, dtype='int32'),
        vectors=np.stack(vectors).astype('float32'),
        threshold=np.float32(threshold),
    )
    return len(labels), photos


def _groups(samples, owner_attr):
    groups = {}
    for sample in samples:
        vector = load_vector(sample.feature)
        if vector is None:
            continue
        groups.setdefault(getattr(sample, owner_attr), []).append(vector)
    return groups


def train_faces():
    from cnc.models import FaceSample
    people, photos = _write(
        FACE_FILE,
        _groups(FaceSample.objects.exclude(feature=''), 'employee_id'),
        FACE_MATCH,
    )
    return '\u672c\u5730\u4eba\u8138\u6a21\u578b\u5df2\u8bad\u7ec3 %s \u4eba\u3001%s \u5f20\u7167\u7247' % (people, photos)


def train_objects():
    from cnc.models import ObjectSample
    kinds, photos = _write(
        OBJECT_FILE,
        _groups(ObjectSample.objects.exclude(feature=''), 'material_id'),
        OBJECT_MATCH,
    )
    return '\u672c\u5730\u7269\u4f53\u6a21\u578b\u5df2\u8bad\u7ec3 %s \u79cd\u7269\u6599\u3001%s \u5f20\u7167\u7247' % (kinds, photos)


def _load(path):
    stamp = os.path.getmtime(path)
    cached = _CACHE.get(path)
    if cached and cached[0] == stamp:
        return cached[1]
    with np.load(path) as data:
        payload = (
            np.array(data['labels']),
            np.array(data['vectors'], dtype='float32'),
            float(data['threshold']),
        )
    _CACHE[path] = (stamp, payload)
    return payload


def match_id(vector, path, margin):
    if vector is None or not os.path.exists(path):
        return None
    labels, vectors, threshold = _load(path)
    if len(labels) == 0 or vectors.shape[1] != len(vector):
        return None
    scores = vectors @ vector.astype('float32')
    index = int(np.argmax(scores))
    best = float(scores[index])
    if best < threshold:
        return None
    if margin and len(scores) > 1:
        second = float(np.partition(scores, -2)[-2])
        if best - second < margin:
            return None
    return int(labels[index])


def match_employee(image):
    from basedata.models import Employee
    found = match_id(face_vector(image), FACE_FILE, 0)
    if found is None:
        return None
    return Employee.objects.filter(pk=found).first()


def match_material(image):
    from basedata.models import Material
    found = match_id(object_vector(image), OBJECT_FILE, 0.04)
    if found is None:
        return None
    return Material.objects.filter(pk=found).first()


def status_text():
    def count(path):
        if not os.path.exists(path):
            return 0
        labels, _vectors, _threshold = _load(path)
        return int(len(labels))
    return '\u4eba\u8138\u6a21\u578b SFace \u5df2\u8bad\u7ec3 %s \u4eba\uff1b\u7269\u4f53\u6a21\u578b MobileNetV2 \u5df2\u8bad\u7ec3 %s \u79cd\u7269\u6599' % (
        count(FACE_FILE), count(OBJECT_FILE))
