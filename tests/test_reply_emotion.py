import copy
import io
import os
import sys
import unittest
import wave
from types import SimpleNamespace
from unittest.mock import MagicMock, mock_open, patch

from pydantic import ValidationError

from app import audio, cli, voice
from app.reply import Reply, ReplySentence


class ReplyEmotionTests(unittest.TestCase):
    def test_new_reply_requires_one_top_level_emotion(self):
        payload = {'emotion': '安慰', 'sentences': [
            {'zh': '别急。', 'ja': '焦らないで。'},
            {'zh': '慢慢说。', 'ja': 'ゆっくり話しましょう。'},
        ]}
        reply = Reply.model_validate(payload)
        self.assertEqual(reply.model_dump(), payload)
        schema = Reply.model_json_schema()
        self.assertIn('emotion', schema['required'])
        self.assertNotIn('emotion', schema['$defs']['ReplySentence']['properties'])
        for emotion in (None, '未知情感'):
            with self.subTest(emotion=emotion), self.assertRaises(ValidationError):
                Reply.model_validate(dict(payload, emotion=emotion))
        with self.assertRaises(ValidationError):
            Reply.model_validate({'sentences': payload['sentences']})

    def test_legacy_mixed_emotions_become_one_without_mutating_input(self):
        legacy = {'sentences': [
            {'zh': '第一句。', 'ja': '一つ目。', 'emotion': '认真'},
            {'zh': '第二句。', 'ja': '二つ目。', 'emotion': '震惊'},
        ]}
        original = copy.deepcopy(legacy)
        reply = Reply.model_validate(legacy)
        self.assertEqual(reply.emotion, '认真')
        self.assertEqual(legacy, original)
        self.assertTrue(all('emotion' not in sentence for sentence in reply.model_dump()['sentences']))
        explicit = Reply.model_validate(dict(legacy, emotion='安慰'))
        self.assertEqual(explicit.emotion, '安慰')
        with self.assertRaises(ValidationError):
            Reply.model_validate(dict(legacy, emotion='未知情感'))

    def play_turns(self, turns):
        content = io.BytesIO()
        with wave.open(content, 'wb') as destination:
            destination.setnchannels(1)
            destination.setsampwidth(2)
            destination.setframerate(48000)
            destination.writeframes(b'\x00\x00' * 48)
        session = MagicMock()
        session.__enter__.return_value = session

        def post(*args, **kwargs):
            response = MagicMock()
            response.status_code = 200
            response.content = content.getvalue()
            response.__enter__.return_value = response
            return response

        session.post.side_effect = post
        captions, reports = [], []
        templates = {'微微傲娇': ('default.wav', '默认参考'),
                     '认真': ('serious.wav', '认真参考'), '安慰': ('comfort.wav', '安慰参考')}
        settings = {'VOICE_REFERENCE_TEMPLATE': '', 'VOICE_SAMPLE_STEPS': '', 'VOICE_SENTENCE_PAUSE_MS': '0',
                    'TEXT_LANG': 'ja', 'VOICE_OUTPUT_LANG': 'ja', 'MEDIA_TYPE': 'wav'}
        with patch.object(audio.requests, 'Session', return_value=session), \
                patch.object(voice, 'TEMPLATES', templates), \
                patch('app.voice.Path.open', mock_open()), \
                patch.object(audio, 'play_clip', side_effect=lambda clip, cancelled, on_start, report: on_start()), \
                patch.dict(os.environ, settings):
            player = audio.VoicePlayer(report=reports.append, on_sentence=lambda line, *args: captions.append(line))
            try:
                for lines, options in turns:
                    player.speak_sentences(lines, **options)
                    self.assertTrue(player.wait(3))
            finally:
                player.close()
        self.assertEqual(reports, [])
        return [call.kwargs['json'] for call in session.post.call_args_list], captions

    def test_full_turn_uses_one_template_and_next_turn_can_change(self):
        mixed = [audio.SpeechLine('第一句', '一つ目。', '认真'), audio.SpeechLine('第二句', '二つ目。', '震惊')]
        plain = [ReplySentence(zh='第三句', ja='三つ目。'), ReplySentence(zh='第四句', ja='四つ目。')]
        requests, captions = self.play_turns([
            (mixed, {'emotion': '安慰'}),
            (plain, {'emotion': '平静'}),
            ([ReplySentence(zh='第五句', ja='五つ目。')], {}),
        ])
        self.assertEqual([r['ref_audio_path'] for r in requests], ['comfort.wav', 'comfort.wav', 'serious.wav', 'serious.wav', 'default.wav'])
        self.assertEqual([r['prompt_text'] for r in requests], ['安慰参考', '安慰参考', '认真参考', '认真参考', '默认参考'])
        self.assertEqual([r['text'] for r in requests], ['一つ目。', '二つ目。', '三つ目。', '四つ目。', '五つ目。'])
        self.assertEqual([line.emotion for line in captions], ['安慰', '安慰', '平静', '平静', voice.DEFAULT_EMOTION])
        self.assertEqual([line.emotion for line in mixed], ['认真', '震惊'])

    def test_legacy_player_call_locks_the_first_emotion(self):
        requests, captions = self.play_turns([([
            audio.SpeechLine('第一句', '一つ目。', '认真'), audio.SpeechLine('第二句', '二つ目。', '震惊')
        ], {})])
        self.assertEqual([r['ref_audio_path'] for r in requests], ['serious.wav', 'serious.wav'])
        self.assertEqual([line.emotion for line in captions], ['认真', '认真'])

    def test_cli_passes_the_emotion_for_each_complete_reply(self):
        replies = [Reply(emotion=emotion, sentences=[{'zh': '好的。', 'ja': 'わかった。'}]) for emotion in ('认真', '安慰')]
        agent, player = MagicMock(), MagicMock()
        agent.invoke.side_effect = [{'structured_response': reply} for reply in replies]
        module = SimpleNamespace(buildAgent=lambda: agent)
        with patch.dict(sys.modules, {'app.brain': module}), \
                patch.object(audio, 'VoicePlayer', return_value=player), \
                patch.object(sys, 'argv', ['agent.py']), \
                patch('builtins.input', side_effect=['第一条用户消息', '第二条用户消息', 'quit']), \
                patch('builtins.print'):
            cli.startAgent()
        self.assertEqual([call.kwargs['emotion'] for call in player.speak_sentences.call_args_list], ['认真', '安慰'])
        self.assertEqual([call.args[0] for call in player.speak_sentences.call_args_list], [reply.sentences for reply in replies])
        player.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
