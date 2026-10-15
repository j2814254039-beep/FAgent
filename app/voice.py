import io
import re
import wave
from pathlib import Path
from typing import Iterator

import numpy as np
import requests
import sounddevice as sd

from app.config import getTextLang, getVoiceOutputLang, getAudioTemplatePath, getMediaType, getVoicePath

EMOTION_MAP = {
    "傲娇":     "傲娇+害羞",      # 嘴硬心软
    "心虚":     "傲娇+心虚",      # 被说中
    "害羞":     "害羞",
    "吐槽":     "吐槽",           # 挖苦
    "安慰":     "安慰",
    "悲伤":     "悲伤",
    "冷静吐槽": "情绪稳定+吐槽",   # 理性调侃
    "无语说教": "无语+说教",       # 拿他没办法
    "认真":     "认真",
    "说教":     "说教",           # 训人
    "温和说教": "说教2",          # 循循善诱
    "超认真":   "超认真",
    "震惊":     "震惊",
}
DEFAULT_EMOTION = "傲娇"

def voiceTextHandle(test:str):
    return re.sub(r'\*[^*]*\*',"",test)

def loadTemplate() -> dict[str,tuple[str,str]]:
    """扫描 Template/，返回 {文件夹名: (wav路径, 参考文本)}。

        没有 text.txt 的文件夹会被跳过 —— v5turbo 强制要求参考文本。
    """
    root = Path(getAudioTemplatePath())
    index={}
    if not root.is_dir():
        return index
    for d in root.iterdir():
        if not d.is_dir():
            continue
        wav = next(d.glob("*.wav"),None)
        txt = d / "text.txt"
        if wav and txt.exists():
            index[d.name]=(str(wav),txt.read_text(encoding="utf-8").strip())
    return index
TEMPLATES = loadTemplate()

def sendVoiceRequest(text:str,emotion:str = DEFAULT_EMOTION):
    folder = EMOTION_MAP.get(emotion,DEFAULT_EMOTION)
    ref = TEMPLATES[folder]
    payload = {
        "text": voiceTextHandle(text),
        "text_lang": getTextLang(),
        "prompt_lang": getVoiceOutputLang(),
        "media_type": getMediaType(),
        "text_split_method": "cut0",  # 客户端已切句
        "fragment_interval": 0,
        "use_cuda_graph": False
    }
    if ref:
        payload["ref_audio_path"],payload["prompt_text"]=ref
    else:
        raise RuntimeError(f"模板音频路径不存在")
    response = requests.post(
        url=getVoicePath(),
        json=payload,
        timeout=180
    )
    if response.status_code != 200:
        raise RuntimeError(f"TTS 失败 {response.status_code}: {response.text[:300]}")
    return response.content


def splitSentences(text: str) -> list[str]:
    """按句号切句，句号保留在每句末尾。"""
    parts = re.split(r'(?<=。)', text)
    return [p.strip() for p in parts if p.strip()]


def synthesizeSentences(text: str, emotion: str = DEFAULT_EMOTION) -> Iterator[bytes]:
    """按句号切句，逐句合成，逐个吐出音频字节。

    是个生成器：调用方拿到第一段就能开始播，后面的还在合成。
    """
    for sentence in splitSentences(text):
        yield sendVoiceRequest(sentence, emotion)


def playAudio(data: bytes) -> None:
    """播放【单段】wav 字节（走系统默认输出设备）。播完才返回。"""
    w = wave.open(io.BytesIO(data))
    sr, ch = w.getframerate(), w.getnchannels()
    samples = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).reshape(-1, ch)

    stream = sd.OutputStream(samplerate=sr, channels=ch, dtype="int16")
    stream.start()
    stream.write(samples)
    stream.stop()    # 阻塞：等缓冲区里的音频全部放完
    stream.close()


def playSentences(audios: Iterator[bytes]) -> None:
    """把逐句生成的音频写进【同一条】输出流，播完才返回。

    比"每句开关一条流"好在两点：
      · 句间无缝 —— 上一句写完紧接着写下一句，不会插入开关流的延迟
      · 绝不重叠 —— 只有一条流，写进去的音频天然是顺序的
    """
    stream = None
    try:
        for data in audios:
            w = wave.open(io.BytesIO(data))
            sr, ch = w.getframerate(), w.getnchannels()
            samples = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).reshape(-1, ch)

            if stream is None:          # 第一句：开流
                stream = sd.OutputStream(samplerate=sr, channels=ch, dtype="int16")
                stream.start()
            stream.write(samples)       # 后续句子：续着写
    finally:
        if stream is not None:
            stream.stop()               # 阻塞：等缓冲区全部放完
            stream.close()