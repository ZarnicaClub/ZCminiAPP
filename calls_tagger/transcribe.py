"""Расшифровка записи звонка: faster-whisper локально, без внешних сервисов.

Модель грузится один раз на процесс (это ~600 МБ памяти и несколько секунд),
поэтому расшифровка идёт пачкой в одном цикле, а не отдельным процессом на звонок.
"""
from __future__ import annotations

import logging
import os

log = logging.getLogger("calls_tagger.transcribe")

MODEL_NAME = os.getenv("TAGGER_MODEL") or "small"
DEVICE = os.getenv("TAGGER_DEVICE") or "cpu"
COMPUTE = os.getenv("TAGGER_COMPUTE") or "int8"
MODEL_DIR = os.getenv("TAGGER_MODEL_DIR") or "/opt/zcminiapp/models"

_model = None


def get_model():
    """Ленивая загрузка модели: первый вызов в цикле, дальше — уже в памяти."""
    global _model
    if _model is None:
        from faster_whisper import WhisperModel

        log.info("загружаю модель %s (%s/%s) из %s", MODEL_NAME, DEVICE, COMPUTE, MODEL_DIR)
        _model = WhisperModel(MODEL_NAME, device=DEVICE, compute_type=COMPUTE,
                              download_root=MODEL_DIR)
    return _model


def transcribe(path: str) -> str:
    """Путь к MP3 -> текст разговора одной строкой."""
    segments, _info = get_model().transcribe(
        str(path), language="ru", vad_filter=True, beam_size=1,
        condition_on_previous_text=False,
    )
    return " ".join(s.text.strip() for s in segments).strip()


def model_title() -> str:
    return f"whisper-{MODEL_NAME}-{COMPUTE}"
