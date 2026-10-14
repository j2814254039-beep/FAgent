import re
from typing import Iterator

import requests

from app.config import getTextLang, getVoiceOutputLang, getAudioTemplatePath, getMediaType


def voiceTextHandle(test:str):
    return re.sub(r'\*[^*]*\*',"",test)


def sendVoiceRequest(text:str):
    text=voiceTextHandle(text)
    text_lang = getTextLang()
    audio_path = getAudioTemplatePath()
    prompt_lang = getVoiceOutputLang()
    media_type = getMediaType()
    response = requests.post(
        url="http://127.0.0.1:9880/tts",
        json={
            "text": text,
            "text_lang": text_lang,
            "ref_audio_path": audio_path,
            "prompt_lang": prompt_lang,
            "media_type": media_type,
            "text_split_method": "cut3",     # ← 不切
            "fragment_interval": 0.3,
        },
        timeout=180
    )
    if response.status_code != 200:
        raise RuntimeError(f"Request failed with status code {response.status_code}")
    return response.content