import re
import os
from pathlib import Path

import requests

from app.config import getTextLang, getVoiceOutputLang, getAudioTemplatePath, getMediaType, getVoicePath, getVoiceFloat

EMOTION_MAP = {
    "傲娇":     "傲娇帮忙",       # 用户认可第三轮01：FCRS_0198
    "傲娇提醒": "傲娇提醒",       # 用户认可第三轮03：FCRS_0425
    "平静":     "平静",           # 已试听通过的6.28秒连续游戏对白
    "伤感":     "伤感",           # 用户试听归类：FCRS_1113
    "微微生气": "微微生气",       # 用户确认05-B：FCRS_0161
    "心虚":     "傲娇强",      # 被说中
    "心虚掩饰": "心虚掩饰",       # 用户确认08-C：掩饰带过
    "吐槽":     "吐槽",           # 用户确认15-B：FCRS_1003
    "吐槽受不了": "吐槽+受不了",   # 用户确认16-A：FCRS_1053
    "安慰":     "安慰",
    "悲伤":     "悲伤",
    "微微悲伤": "悲伤",           # 用户归类07-A，悲伤旧标签兼容沿用
    "冷静吐槽": "情绪稳定+吐槽",   # 理性调侃
    "无语说教": "无语+说教",       # 拿他没办法
    "认真":     "认真",
    "说教":     "说教",           # 训人
    "克制说教": "说教2",          # 用户确认17-C：FCRS_0837
    "温和劝告": "温和劝告",       # 用户确认17-D：FCRS_0366连续裁剪
    "温和说教": "温和劝告",       # 兼容原标签，使用已确认17-D
    "超认真":   "超认真",
}
DEFAULT_EMOTION = "平静"

def voiceTextHandle(test:str):
    return re.sub(r'\*[^*]*\*',"",test)

def loadTemplate() -> dict[str,tuple[str,str]]:
    """扫描 Template/，返回 {文件夹名: (wav路径, 参考文本)}。

        没有 text.txt 的文件夹会被跳过 —— v5turbo 强制要求参考文本。
    """
    root = Path(getAudioTemplatePath() or "Template")
    index={}
    if not root.is_dir():
        return index
    for d in root.iterdir():
        if not d.is_dir():
            continue
        wav = next(iter(sorted(d.glob("*.wav"))), None)
        txt = d / "text.txt"
        if wav and txt.exists():
            index[d.name]=(str(wav),txt.read_text(encoding="utf-8").strip())
    return index

TEMPLATES = loadTemplate()

def buildVoicePayload(text: str, emotion: str = DEFAULT_EMOTION, *, streaming=False):
    folder = os.getenv("VOICE_REFERENCE_TEMPLATE", "").strip() or EMOTION_MAP.get(emotion, EMOTION_MAP[DEFAULT_EMOTION])
    ref = TEMPLATES.get(folder)
    if not ref:
        raise RuntimeError(f"缺少情绪模板：{folder}，请检查 VOICE_TEMPLATE_PATH 下的 wav 和 text.txt")
    payload = {
        "text": voiceTextHandle(text),
        "text_lang": getTextLang(),
        "prompt_lang": getVoiceOutputLang(),
        "media_type": "wav" if streaming else getMediaType(),
        # 调用方已按中日文对应关系分句，保留句内逗号、省略号的韵律。
        "streaming_mode": 1 if streaming else 0,
        "text_split_method": "cut0",
        "batch_size": 1,
        "split_bucket": False,
        "fragment_interval": 0,  # 句间停顿由播放器统一添加，避免叠加两次。
        "speed_factor": getVoiceFloat("VOICE_SPEED", 0.95, 0.5, 1.5),
        "use_cuda_graph": False
    }

    payload["ref_audio_path"], payload["prompt_text"] = ref
    steps = os.getenv("VOICE_SAMPLE_STEPS", "").strip()
    if steps:
        if steps not in {"4", "8", "16", "32"}:
            raise ValueError("VOICE_SAMPLE_STEPS 必须为 4、8、16 或 32")
        payload["sample_steps"] = int(steps)
    P = Path(__file__).parent.parent / "emoLog.txt"
    with P.open("a", encoding="utf-8") as log:
        log.write(payload["ref_audio_path"] + "\n")
    return payload


def openVoiceResponse(session:requests.Session, text, emotion=DEFAULT_EMOTION, *, streaming=False):
    response = session.post(
        getVoicePath(), json=buildVoicePayload(text, emotion, streaming=streaming),
        stream=streaming, timeout=(3, float(os.getenv("VOICE_READ_TIMEOUT", "60"))),
    )
    if response.status_code != 200:
        status = response.status_code
        response.close()
        raise RuntimeError(f"语音服务返回 HTTP {status}")
    return response


def sendVoiceRequest(text: str, emotion: str = DEFAULT_EMOTION):
    """返回一句完整音频，播放时并行预取下一句。"""
    with requests.Session() as session:
        with openVoiceResponse(session, text, emotion) as response:
            return response.content
