"""逐句预取与播放；音频回调不等待网络、不加锁、不做音频处理。"""
import io
import ctypes
import os
import queue
import threading
import wave
from dataclasses import dataclass
from contextlib import contextmanager
from time import perf_counter

import numpy as np
import requests
import sounddevice as sd

from app.config import getVoiceFloat
from app.voice import DEFAULT_EMOTION, openVoiceResponse, voiceTextHandle


@dataclass(frozen=True)
class SpeechLine:
    zh: str
    ja: str
    emotion: str = DEFAULT_EMOTION


@dataclass(frozen=True)
class AudioClip:
    rate: int
    samples: np.ndarray


def output_devices():
    apis = sd.query_hostapis()
    return [(i, d, apis[d["hostapi"]]["name"])
            for i, d in enumerate(sd.query_devices()) if d["max_output_channels"] > 0]


def list_output_devices():
    for index, device, api in output_devices():
        print(f"{index}: {device['name']} [{api}]")


def device_candidates():
    selection = os.getenv("VOICE_OUTPUT_DEVICE", "headphones").strip()
    devices = output_devices()
    if selection.lower() == "default":
        return [int(sd.default.device[1])]
    if selection.isdigit():
        matches = [d for d in devices if d[0] == int(selection)]
    elif selection.lower() == "headphones":
        matches = [d for d in devices if any(
            word in d[1]["name"].lower() for word in ("headphone", "headset", "耳机"))]
    else:
        matches = [d for d in devices if selection.lower() in d[1]["name"].lower()]
    if not matches:
        raise RuntimeError(f"找不到输出设备 {selection!r}；运行 python agent.py --list-audio-devices 查看设备")
    matches.sort(key=lambda d: 0 if d[2] == "Windows WASAPI" else 1)
    return [d[0] for d in matches]


def prepare_wav(data):
    """完整的一句再解码；所有增益和边沿处理均在音频回调外完成。"""
    try:
        with wave.open(io.BytesIO(data), "rb") as wav:
            channels, width, rate, frames = (wav.getnchannels(), wav.getsampwidth(),
                                            wav.getframerate(), wav.getnframes())
            if channels not in (1, 2) or width != 2 or not 8000 <= rate <= 192000:
                raise ValueError("只支持 16-bit PCM 单声道或双声道 WAV")
            if not 0 < frames <= rate * 120:
                raise ValueError("语音为空或单句超过两分钟")
            pcm = wav.readframes(frames)
            if len(pcm) != frames * channels * width:
                raise ValueError("语音 PCM 数据不完整")
    except (wave.Error, EOFError) as exc:
        raise ValueError("语音服务未返回有效的完整 WAV 音频") from exc
    samples = np.frombuffer(pcm, dtype="<i2").reshape(-1, channels).astype(np.float32)
    samples *= getVoiceFloat("VOICE_GAIN", 0.85, 0.0, 1.0)
    fade = min(round(rate * getVoiceFloat("VOICE_FADE_MS", 8, 0, 30) / 1000), frames // 2)
    if fade:
        envelope = np.linspace(0, 1, fade, dtype=np.float32)[:, None]
        samples[:fade] *= envelope
        samples[-fade:] *= envelope[::-1]
    return AudioClip(rate, np.rint(samples).astype(np.int16))


@contextmanager
def audio_thread_context():
    """WASAPI 的 COM 接口需要在实际调用它的线程中初始化。"""
    if os.name != "nt":
        yield
        return
    ole32 = ctypes.WinDLL("ole32")
    ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    ole32.CoInitializeEx.restype = ctypes.c_long
    ole32.CoUninitialize.argtypes = []
    ole32.CoUninitialize.restype = None
    result = ole32.CoInitializeEx(None, 0)  # COINIT_MULTITHREADED
    # RPC_E_CHANGED_MODE 表示此线程已按另一模式初始化，不重复释放。
    if result not in (0, 1, -2147417850):
        raise RuntimeError(f"音频线程 COM 初始化失败：{result:#x}")
    try:
        yield
    finally:
        if result in (0, 1):
            ole32.CoUninitialize()


def play_clip(clip, cancelled, on_start=None, report=print):
    with audio_thread_context():
        _play_clip(clip, cancelled, on_start, report)


def _play_clip(clip, cancelled, on_start=None, report=print):
    """只读取预先准备好的 PCM；整句播放期间不会因 HTTP 分片而补零。"""
    if cancelled.is_set():
        return
    pcm = clip.samples
    finished = threading.Event()
    position = 0
    underflows = 0
    stream = None
    errors = []
    subtitle_shown = False

    def callback(outdata, frames, time_info, status):
        nonlocal position, underflows
        outdata.fill(0)
        if cancelled.is_set():
            raise sd.CallbackAbort
        if status and status.output_underflow:
            underflows += 1
        count = min(frames, len(pcm) - position)
        outdata[:count] = pcm[position:position + count]
        position += count
        if position == len(pcm):
            raise sd.CallbackStop

    for device in device_candidates():
        candidate = None
        try:
            finished.clear()
            position = 0
            info = sd.query_devices(device)
            api = sd.query_hostapis(info["hostapi"])["name"]
            extra = sd.WasapiSettings(auto_convert=True) if api == "Windows WASAPI" else None
            # 回调兼容 WDM-KS；较宽裕的设备缓冲减少系统调度造成的欠载。
            candidate = sd.OutputStream(
                device=device, samplerate=clip.rate, channels=pcm.shape[1], dtype="int16",
                latency="high", callback=callback, finished_callback=finished.set,
                extra_settings=extra,
            )
            if cancelled.is_set():
                candidate.close()
                return
            if not subtitle_shown and on_start is not None:
                on_start()
                subtitle_shown = True
            candidate.start()
            stream = candidate
            if os.getenv("VOICE_TIMINGS") == "1":
                report(f"[语音] 输出：{info['name']} [{api}]")
            break
        except sd.PortAudioError as exc:
            if candidate is not None:
                candidate.close()
            errors.append(f"设备 {device}: {exc}")
        except BaseException:
            if candidate is not None:
                candidate.close()
            raise
    if stream is None:
        raise RuntimeError("无法打开所选耳机/输出设备：" + "; ".join(errors))
    try:
        while not finished.wait(0.02):
            if cancelled.is_set():
                break
            if not stream.active and not finished.wait(0.05):
                raise RuntimeError("音频设备意外停止")
        if not cancelled.is_set() and position < len(pcm):
            raise RuntimeError("音频未播放完，输出设备已停止")
    finally:
        if not finished.is_set():
            stream.abort()
        stream.close()
    if underflows:
        report(f"[语音] 音频设备发生 {underflows} 次欠载；可固定 VOICE_OUTPUT_DEVICE 为耳机的 WASAPI 设备。")


class VoicePlayer:
    """播放当前句时预取下一句；新消息会丢弃旧回复剩余的字幕与音频。"""

    def __init__(self, report=print, on_sentence=None):
        self.report = report
        self.on_sentence = on_sentence
        self._condition = threading.Condition()#锁
        self._pending = None#多余的任务属性
        self._current = None#当前线程执行的Event对象
        self._closed = False
        self._idle = threading.Event()#当前播放器主类是否工作标记
        self._idle.set()#默认true为未工作即空闲
        self._thread = threading.Thread(target=self._run, name="voice-player", daemon=True)
        self._thread.start()

    def stop(self):
        with self._condition:
            if self._current is not None:
                self._current.set()
            self._pending = None
            if self._current is None:
                self._idle.set()

    def speak(self, text, emotion=DEFAULT_EMOTION):
        self.speak_sentences([SpeechLine("", text)], emotion=emotion)

    def speak_sentences(self, sentences, *, emotion=None):
        """整轮共用一个情感；旧调用未传标签时沿用第一句的标签。"""
        sentences = tuple(sentences)
        if emotion is None:
            emotion = getattr(sentences[0], "emotion", DEFAULT_EMOTION) if sentences else DEFAULT_EMOTION
        lines = tuple(SpeechLine(s.zh, s.ja, emotion) for s in sentences)
        with self._condition:
            self.stop()
            if not self._closed and lines:
                self._idle.clear()
                self._pending = lines
                self._condition.notify()

    def wait(self, timeout=None):
        return self._idle.wait(timeout)

    def close(self):
        with self._condition:
            self.stop()
            self._closed = True
            self._condition.notify()
        self._thread.join(timeout=0.2)

    def _play_reply(self, session, lines, cancelled):
        reply_emotion = lines[0].emotion if lines else DEFAULT_EMOTION
        ready = queue.Queue(maxsize=1)
        producer_done = threading.Event()
        gap = getVoiceFloat("VOICE_SENTENCE_PAUSE_MS", 350, 0, 2000) / 1000
        shown = set()
        started_at = perf_counter()

        def produce():
            try:
                for index, line in enumerate(lines):
                    # 队列满时不再发请求：当前句之外最多缓存/生成下一句。
                    while ready.full():
                        if cancelled.wait(0.02):
                            return
                    if cancelled.is_set():
                        return
                    try:
                        clip = None
                        if voiceTextHandle(line.ja).strip():
                            with openVoiceResponse(session, line.ja, reply_emotion) as response:
                                if cancelled.is_set():
                                    return
                                clip = prepare_wav(response.content)
                        if cancelled.is_set():
                            return
                        ready.put_nowait((index, clip, None))
                    except Exception as exc:
                        if not cancelled.is_set():
                            ready.put_nowait((index, None, exc))
                        return
            finally:
                producer_done.set()

        def show(index):
            with self._condition:
                if index not in shown and not cancelled.is_set():
                    shown.add(index)
                    if index == 0 and os.getenv("VOICE_TIMINGS") == "1":
                        self.report(f"[语音] 首句准备耗时：{perf_counter() - started_at:.2f}s")
                    if self.on_sentence is not None:
                        self.on_sentence(lines[index], index + 1, len(lines))

        producer = threading.Thread(target=produce, name="voice-prefetch", daemon=True)
        producer.start()
        try:
            for index in range(len(lines)):
                if cancelled.is_set():
                    return
                while not cancelled.is_set():
                    try:
                        _, clip, error = ready.get(timeout=0.05)
                        break
                    except queue.Empty:
                        if producer_done.is_set():
                            raise RuntimeError("语音预取意外结束")
                if cancelled.is_set():
                    return
                if error is not None:
                    raise error
                if clip is None:
                    show(index)
                else:
                    play_clip(clip, cancelled, on_start=lambda i=index: show(i), report=self.report)
                if index < len(lines) - 1 and cancelled.wait(gap):
                    return
        except Exception as exc:
            if not cancelled.is_set():
                self.report(f"\n[语音失败] {exc}；剩余回复以文字显示。")
                for index in range(len(lines)):
                    show(index)
        finally:
            cancelled.set()
            # 不并发堆积已取消的推理；这里只等待后台，不阻塞 CLI 输入。
            producer.join()

    def _run(self):
        with requests.Session() as session:
            while True:
                with self._condition:
                    self._condition.wait_for(lambda: self._closed or self._pending is not None)
                    if self._closed:
                        return
                    lines = self._pending#取出剩余语句
                    self._pending = None#清除
                    self._current = cancelled = threading.Event()#更新当前在跑的线程Event
                try:
                    self._play_reply(session, lines, cancelled)#播放
                except Exception as exc:
                    if not cancelled.is_set():#如果被取消
                        self.report(f"[语音失败] {exc}")
                        if self.on_sentence:
                            for i, line in enumerate(lines, 1):
                                if cancelled.is_set():
                                    break
                                self.on_sentence(line, i, len(lines))
                finally:
                    with self._condition:
                        self._current = None
                        if self._pending is None:
                            self._idle.set()
