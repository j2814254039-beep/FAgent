import io
import os
import threading
import time
import unittest
import wave
from unittest.mock import Mock, patch

import numpy as np
from pydantic import ValidationError

from app import audio, voice
from app.reply import Reply


def wav_bytes(samples=None, channels=1, rate=48000):
    if samples is None:
        samples = np.full((4800, channels), 12000, dtype=np.int16)
    result = io.BytesIO()
    with wave.open(result, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(np.asarray(samples, dtype='<i2').tobytes())
    return result.getvalue()


def response(data=None):
    result = Mock()
    result.content = wav_bytes() if data is None else data
    result.__enter__ = Mock(return_value=result)
    result.__exit__ = Mock(return_value=False)
    return result


class AudioTests(unittest.TestCase):
    def test_com_initialized_and_released_on_the_playback_thread(self):
        for result in (0, 1, -2147417850):
            with self.subTest(result=result):
                ole32 = Mock()
                ole32.CoInitializeEx.return_value = result
                with patch.object(audio.os, 'name', 'nt'), \
                        patch.object(audio.ctypes, 'WinDLL', return_value=ole32, create=True):
                    with audio.audio_thread_context():
                        ole32.CoInitializeEx.assert_called_once_with(None, 0)
                self.assertEqual(ole32.CoUninitialize.call_count, 1 if result in (0, 1) else 0)

    def test_failed_stream_start_retries_without_duplicate_subtitle(self):
        clip = audio.prepare_wav(wav_bytes(np.arange(8, dtype=np.int16)))
        streams = []
        subtitles = []

        class FakeStream:
            active = True

            def __init__(self, **kwargs):
                self.kwargs = kwargs
                self.closed = False
                streams.append(self)

            def start(self):
                if self.kwargs['device'] == 10:
                    raise audio.sd.PortAudioError('start failed')
                try:
                    self.kwargs['callback'](np.zeros((8, 1), dtype=np.int16), 8, None, None)
                except audio.sd.CallbackStop:
                    self.kwargs['finished_callback']()

            def close(self):
                self.closed = True

        with patch.object(audio, 'device_candidates', return_value=[10, 11]), \
                patch.object(audio.sd, 'query_devices', return_value={'hostapi': 0, 'name': 'Headphones'}), \
                patch.object(audio.sd, 'query_hostapis', return_value={'name': 'Windows WASAPI'}), \
                patch.object(audio.sd, 'OutputStream', FakeStream):
            audio.play_clip(clip, threading.Event(), on_start=lambda: subtitles.append('shown'))
        self.assertEqual(subtitles, ['shown'])
        self.assertTrue(all(stream.closed for stream in streams))
        self.assertEqual(len(streams), 2)

    def test_headphones_never_fall_back_to_speakers(self):
        devices = [(3, {"name": "Speaker"}, "Windows WASAPI")]
        with patch.dict(os.environ, {"VOICE_OUTPUT_DEVICE": "headphones"}), \
                patch.object(audio, "output_devices", return_value=devices), \
                self.assertRaises(RuntimeError):
            audio.device_candidates()

    def test_headphone_preference_and_explicit_selection(self):
        devices = [(3, {"name": "Speaker"}, "MME"),
                   (13, {"name": "Headphones KS"}, "Windows WDM-KS"),
                   (10, {"name": "Headphones USB"}, "Windows WASAPI")]
        with patch.object(audio, "output_devices", return_value=devices):
            with patch.dict(os.environ, {"VOICE_OUTPUT_DEVICE": "headphones"}):
                self.assertEqual(audio.device_candidates(), [10, 13])
            with patch.dict(os.environ, {"VOICE_OUTPUT_DEVICE": "13"}):
                self.assertEqual(audio.device_candidates(), [13])

    def test_gain_and_fade_do_not_wrap_or_change_duration(self):
        samples = np.full((4800, 2), 32767, dtype=np.int16)
        samples[:, 1] = -32768
        with patch.dict(os.environ, {"VOICE_GAIN": "0.85", "VOICE_FADE_MS": "8"}):
            clip = audio.prepare_wav(wav_bytes(samples, channels=2))
        self.assertEqual(clip.rate, 48000)
        self.assertEqual(clip.samples.shape, samples.shape)
        self.assertEqual(clip.samples.dtype, np.dtype('int16'))
        self.assertTrue(np.all(clip.samples[0] == 0))
        self.assertTrue(np.all(clip.samples[-1] == 0))
        self.assertTrue(np.all(clip.samples[:, 0] >= 0))
        self.assertTrue(np.all(clip.samples[:, 1] <= 0))
        self.assertLessEqual(np.max(np.abs(clip.samples.astype(np.int32))), 27853)

    def test_bad_truncated_and_empty_wav_rejected(self):
        for data in (b'', b'{"error":true}', wav_bytes()[:-1], wav_bytes(np.zeros(0))):
            with self.subTest(length=len(data)), self.assertRaises(ValueError):
                audio.prepare_wav(data)

    def test_invalid_gain_rejected(self):
        for gain in ('nan', 'inf', '-1', '2'):
            with patch.dict(os.environ, {"VOICE_GAIN": gain}), self.assertRaises(ValueError):
                audio.prepare_wav(wav_bytes())

    def test_request_preserves_sentence_and_applies_speed(self):
        with patch.object(voice, "TEMPLATES", {"微微傲娇": ("ref.wav", "参考文本")}), \
                patch.dict(os.environ, {"VOICE_SPEED": "0.95"}):
            payload = voice.buildVoicePayload("そうね、でも……。*笑*", "unknown")
        self.assertEqual(payload["text"], "そうね、でも……。")
        self.assertEqual(payload["ref_audio_path"], "ref.wav")
        self.assertEqual(payload["streaming_mode"], 0)
        self.assertEqual(payload["text_split_method"], "cut0")
        self.assertEqual(payload["fragment_interval"], 0)
        self.assertEqual(payload["speed_factor"], 0.95)

    def test_http_error_closes_response(self):
        session = Mock()
        session.post.return_value.status_code = 500
        with patch.object(voice, "buildVoicePayload", return_value={}), \
                self.assertRaisesRegex(RuntimeError, "500"):
            voice.openVoiceResponse(session, "test")
        session.post.return_value.close.assert_called_once()

    def test_schema_requires_translated_pairs(self):
        reply = Reply.model_validate({'emotion': '平静', 'sentences': [
            {'zh': '早上好。', 'ja': 'おはよう。'},
            {'zh': '你睡得好吗？', 'ja': 'よく眠れた？'},
        ]})
        self.assertEqual(reply.sentences[1].zh, '你睡得好吗？')
        for invalid in ({'emotion': '平静', 'sentences': []}, {'emotion': '平静', 'sentences': [{'ja': 'hello'}]},
                        {'emotion': '平静', 'sentences': [{'zh': '  ', 'ja': 'hello'}]}):
            with self.assertRaises(ValidationError):
                Reply.model_validate(invalid)

    def test_callback_preserves_all_pcm_and_caption_precedes_play(self):
        clip = audio.prepare_wav(wav_bytes(np.arange(32, dtype=np.int16)))
        delivered = []
        events = []
        settings = []

        class FakeStream:
            active = True

            def __init__(self, **kwargs):
                self.kwargs = kwargs
                settings.append(kwargs)

            def start(self):
                events.append('play')
                for _ in range(8):
                    out = np.zeros((8, 1), dtype=np.int16)
                    stop = False
                    try:
                        self.kwargs['callback'](out, 8, None, None)
                    except audio.sd.CallbackStop:
                        stop = True
                    delivered.append(out.copy())
                    if stop:
                        self.kwargs['finished_callback']()
                        return

            def close(self):
                pass

        with patch.object(audio, 'device_candidates', return_value=[10]), \
                patch.object(audio.sd, 'query_devices', return_value={'hostapi': 0}), \
                patch.object(audio.sd, 'query_hostapis', return_value={'name': 'Windows WASAPI'}), \
                patch.object(audio.sd, 'OutputStream', FakeStream):
            audio.play_clip(clip, threading.Event(), on_start=lambda: events.append('subtitle'))
        self.assertEqual(events, ['subtitle', 'play'])
        np.testing.assert_array_equal(np.concatenate(delivered), clip.samples)
        self.assertEqual(settings[0]['latency'], 'high')

    def test_sentence_prefetch_alignment_and_pause(self):
        second_requested = threading.Event()
        order = []
        shown_at = []
        reports = []
        calls = []

        def request(session, text, emotion, **kwargs):
            calls.append(text)
            if text == 'ja2':
                second_requested.set()
            return response()

        def subtitle(line, index, total):
            order.append('subtitle' + str(index))
            shown_at.append(time.perf_counter())

        def play(clip, cancelled, on_start, report):
            on_start()
            if len(shown_at) == 1:
                self.assertTrue(second_requested.wait(1), '播放当前句时没有预取下一句')
                self.assertEqual(calls, ['ja1', 'ja2'])
            order.append('done' + str(len(shown_at)))

        with patch.object(audio, 'openVoiceResponse', side_effect=request), \
                patch.object(audio, 'play_clip', side_effect=play), \
                patch.dict(os.environ, {'VOICE_SENTENCE_PAUSE_MS': '50'}):
            player = audio.VoicePlayer(report=reports.append, on_sentence=subtitle)
            try:
                player.speak_sentences([audio.SpeechLine('zh1', 'ja1'), audio.SpeechLine('zh2', 'ja2')])
                self.assertTrue(player.wait(3))
            finally:
                player.close()
        self.assertEqual(reports, [])
        self.assertEqual(order, ['subtitle1', 'done1', 'subtitle2', 'done2'])
        self.assertGreaterEqual(shown_at[1] - shown_at[0], 0.045)

    def test_cancel_discards_prefetched_audio_and_subtitles(self):
        first_playing = threading.Event()
        shown = []
        reports = []

        def subtitle(line, index, total):
            shown.append(line.zh)

        def play(clip, cancelled, on_start, report):
            on_start()
            if shown[-1] == 'old1':
                first_playing.set()
                cancelled.wait(2)

        with patch.object(audio, 'openVoiceResponse', side_effect=lambda *a, **k: response()), \
                patch.object(audio, 'play_clip', side_effect=play), \
                patch.dict(os.environ, {'VOICE_SENTENCE_PAUSE_MS': '0'}):
            player = audio.VoicePlayer(report=reports.append, on_sentence=subtitle)
            try:
                player.speak_sentences([audio.SpeechLine('old1', 'ja1'), audio.SpeechLine('old2', 'ja2')])
                self.assertTrue(first_playing.wait(1))
                player.speak_sentences([audio.SpeechLine('new', 'ja3')])
                self.assertTrue(player.wait(3))
            finally:
                player.close()
        self.assertEqual(shown, ['old1', 'new'])
        self.assertEqual(reports, [])

    def test_service_failure_preserves_all_unshown_text(self):
        shown = []
        reports = []
        with patch.object(audio, 'openVoiceResponse', side_effect=RuntimeError('offline')):
            player = audio.VoicePlayer(report=reports.append,
                                       on_sentence=lambda line, *args: shown.append(line.zh))
            try:
                player.speak_sentences([audio.SpeechLine('zh1', 'ja1'), audio.SpeechLine('zh2', 'ja2')])
                self.assertTrue(player.wait(2))
            finally:
                player.close()
        self.assertEqual(shown, ['zh1', 'zh2'])
        self.assertEqual(len(reports), 1)
        self.assertIn('offline', reports[0])

    def test_background_latest_reply_replaces_pending_work(self):
        started = threading.Event()
        release = threading.Event()
        calls = []
        reports = []

        def request(session, text, emotion, **kwargs):
            calls.append(text)
            if text == 'first':
                started.set()
                release.wait(2)
            raise RuntimeError(text)

        with patch.object(audio, 'openVoiceResponse', side_effect=request):
            player = audio.VoicePlayer(report=reports.append)
            try:
                player.speak('first')
                self.assertTrue(started.wait(1))
                player.speak('discard')
                player.speak('last')
                release.set()
                self.assertTrue(player.wait(2))
            finally:
                release.set()
                player.close()
        self.assertEqual(calls, ['first', 'last'])
        self.assertFalse(any('first' in r for r in reports))


if __name__ == '__main__':
    unittest.main()
