import os
import unittest
from unittest.mock import Mock, mock_open, patch

from app import model, voice
from app.reply import Reply
from scripts.compare_voice import comparison_cases


class VoiceTuningTests(unittest.TestCase):
    def setUp(self):
        self.templates = {"微微傲娇": ("default.wav", "默认台词"),
                          "认真": ("neutral.wav", "另一句台词")}
        self.env = patch.dict(os.environ, {"VOICE_REFERENCE_TEMPLATE": "", "VOICE_SAMPLE_STEPS": ""})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.log_file = mock_open()
        self.log_patch = patch("app.voice.Path.open", self.log_file)
        self.log_patch.start()
        self.addCleanup(self.log_patch.stop)

    def test_reference_override_keeps_audio_and_transcript_paired(self):
        with patch.object(voice, "TEMPLATES", self.templates), \
                patch.dict(os.environ, {"VOICE_REFERENCE_TEMPLATE": "认真"}):
            payload = voice.buildVoicePayload("こんにちは。", "傲娇")
        self.assertEqual((payload["ref_audio_path"], payload["prompt_text"]), self.templates["认真"])

    def test_neutral_emotion_is_valid_and_has_a_real_template_mapping(self):
        reply = Reply(emotion="平静", sentences=[{"zh": "修好了。", "ja": "直ったよ。"}])
        with patch.object(voice, "TEMPLATES", self.templates):
            self.assertEqual(voice.buildVoicePayload(reply.sentences[0].ja, reply.emotion)["ref_audio_path"], "neutral.wav")

    def test_steps_omitted_by_default_and_validated_when_configured(self):
        with patch.object(voice, "TEMPLATES", self.templates):
            self.assertNotIn("sample_steps", voice.buildVoicePayload("hello"))
            with patch.dict(os.environ, {"VOICE_SAMPLE_STEPS": "8"}):
                self.assertEqual(voice.buildVoicePayload("hello")["sample_steps"], 8)
            for value in ("0", "6", "8.5", "nan"):
                with patch.dict(os.environ, {"VOICE_SAMPLE_STEPS": value}), self.assertRaises(ValueError):
                    voice.buildVoicePayload("hello")

    def test_configured_steps_reach_outbound_requests(self):
        with patch.object(voice, "TEMPLATES", self.templates):
            for steps in (4, 8, 16, 32):
                for streaming in (False, True):
                    with self.subTest(steps=steps, streaming=streaming), \
                            patch.dict(os.environ, {"VOICE_SAMPLE_STEPS": str(steps)}):
                        session = Mock()
                        session.post.return_value.status_code = 200
                        response = voice.openVoiceResponse(session, "こんにちは。", streaming=streaming)
                        self.assertIs(response, session.post.return_value)
                        request = session.post.call_args.kwargs
                        self.assertEqual(request["json"]["sample_steps"], steps)
                        self.assertEqual(request["stream"], streaming)
                        self.assertEqual(request["json"]["ref_audio_path"], "default.wav")

    def test_invalid_steps_do_not_send_or_log_a_request(self):
        session = Mock()
        with patch.object(voice, "TEMPLATES", self.templates), \
                patch.dict(os.environ, {"VOICE_SAMPLE_STEPS": "6"}), \
                self.assertRaisesRegex(ValueError, "VOICE_SAMPLE_STEPS"):
            voice.openVoiceResponse(session, "こんにちは。")
        session.post.assert_not_called()
        self.log_file.assert_not_called()

    def test_reference_log_is_closed_after_writing(self):
        with patch.object(voice, "TEMPLATES", self.templates):
            voice.buildVoicePayload("こんにちは。")
        self.log_file.assert_called_once_with("a", encoding="utf-8")
        self.log_file().write.assert_called_once_with("default.wav\n")
        self.log_file().__exit__.assert_called_once()

    def test_missing_template_override_is_not_silently_ignored(self):
        with patch.object(voice, "TEMPLATES", self.templates), \
                patch.dict(os.environ, {"VOICE_REFERENCE_TEMPLATE": "missing"}), \
                self.assertRaisesRegex(RuntimeError, "missing"):
            voice.buildVoicePayload("hello")

    def test_comparison_changes_only_steps_with_same_template(self):
        with patch.object(voice, "TEMPLATES", self.templates), \
                patch("scripts.compare_voice.TEMPLATES", self.templates):
            cases = comparison_cases("同一句。", ["认真"], [4, 8], seed=123)
        first, second = cases[0][2], cases[1][2]
        self.assertEqual(first["seed"], 123)
        self.assertEqual(first["ref_audio_path"], "neutral.wav")
        self.assertEqual({k for k in first if first[k] != second[k]}, {"sample_steps"})

    def test_temperature_does_not_change_model_or_reasoning_setting(self):
        with patch.object(model, "getModelName", return_value="deepseek-flash"), \
                patch.object(model, "getKey", return_value="test-only"), \
                patch.object(model, "getReasoningEffor", return_value="none"), \
                patch.object(model, "init_chat_model") as factory, \
                patch.dict(os.environ, {"CHAT_TEMPERATURE": "0.8"}):
            model.buildModel()
        factory.assert_called_once_with(model="deepseek-flash", api_key="test-only", reasoning_effort="none", temperature=0.8)


if __name__ == "__main__":
    unittest.main()
