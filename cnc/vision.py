# coding=utf-8
import os
import re
import threading
from urllib.parse import unquote

import cv2
import numpy as np

FACE_MATCH = 0.363
OBJECT_MATCH = 0.82
FACE_MODEL = 'face_recognition_sface_2021dec.onnx'
OBJECT_MODEL = 'image_classification_mobilenetv2_2022apr.onnx'
_DETECTOR = None
_RECOGNIZER = None
_OBJECT_NET = None
_LOCK = threading.Lock()
_MODEL_DIR = os.path.join(os.path.dirname(__file__), 'data')


def _models():
    global _DETECTOR, _RECOGNIZER
    if _RECOGNIZER is not None:
        return _DETECTOR, _RECOGNIZER
    detect_path = os.path.join(_MODEL_DIR, 'face_detection_yunet_2023mar.onnx')
    recog_path = os.path.join(_MODEL_DIR, 'face_recognition_sface_2021dec.onnx')
    if not (os.path.exists(detect_path) and os.path.exists(recog_path)):
        return None, None
    _DETECTOR = cv2.FaceDetectorYN.create(detect_path, '', (320, 320), 0.6, 0.3, 5000)
    _RECOGNIZER = cv2.FaceRecognizerSF.create(recog_path, '')
    return _DETECTOR, _RECOGNIZER


def _object_net():
    global _OBJECT_NET
    if _OBJECT_NET is not None:
        return _OBJECT_NET
    path = os.path.join(_MODEL_DIR, OBJECT_MODEL)
    if not os.path.exists(path):
        return None
    _OBJECT_NET = cv2.dnn.readNet(path)
    return _OBJECT_NET


def read_image(data):
    if not data:
        return None
    array = np.frombuffer(data, dtype=np.uint8)
    return cv2.imdecode(array, cv2.IMREAD_COLOR)


def decode_texts(image):
    found = []
    if image is None:
        return found
    qr = cv2.QRCodeDetector()
    text, _points, _straight = qr.detectAndDecode(image)
    if text:
        found.append(text)
    try:
        ok, texts, _points, _straight = qr.detectAndDecodeMulti(image)
        if ok:
            found.extend([item for item in texts if item])
    except Exception:
        pass
    try:
        barcode = cv2.barcode.BarcodeDetector()
        result = barcode.detectAndDecode(image)
        payload = result[0] if isinstance(result, tuple) else result
        if isinstance(payload, str) and payload:
            found.append(payload)
        elif payload is not None and not isinstance(payload, str):
            for item in payload:
                if item:
                    found.append(str(item))
    except Exception:
        pass
    unique = []
    for item in found:
        if item not in unique:
            unique.append(item)
    return unique


def token_from_text(text):
    text = (text or '').strip()
    matched = re.search(r'/m/q/([^/?#]+)', text)
    if matched:
        return unquote(matched.group(1))
    return text


def face_vector(image):
    if image is None:
        return None
    detector, recognizer = _models()
    if detector is None or recognizer is None:
        return None
    height, width = image.shape[:2]
    if height < 20 or width < 20:
        return None
    with _LOCK:
        detector.setInputSize((width, height))
        _ok, faces = detector.detect(image)
        if faces is None or len(faces) == 0:
            return None
        best = max(faces, key=lambda row: float(row[2]) * float(row[3]))
        aligned = recognizer.alignCrop(image, best)
        feature = recognizer.feature(aligned)
    vector = np.asarray(feature, dtype='float32').reshape(-1)
    norm = float(np.linalg.norm(vector))
    if norm == 0:
        return None
    return vector / norm


def object_vector(image):
    if image is None:
        return None
    net = _object_net()
    if net is None:
        return None
    blob = cv2.dnn.blobFromImage(image, 1.0 / 255.0, (224, 224), (0, 0, 0), swapRB=True, crop=True)
    with _LOCK:
        net.setInput(blob)
        raw = net.forward().reshape(-1).astype('float32')
    raw -= float(raw.mean())
    norm = float(np.linalg.norm(raw))
    if norm == 0:
        return None
    return raw / norm


def dump_vector(vector):
    return ','.join('%.5f' % value for value in vector)


def load_vector(text):
    if not text:
        return None
    return np.asarray([float(part) for part in text.split(',') if part], dtype='float32')


def similarity(left, right):
    if left is None or right is None or len(left) != len(right):
        return 0.0
    return float(np.dot(left, right))
