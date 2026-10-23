import threading

from app.action import AvatarWindow


def show_sentence(sentence, index, total):
    print(f"\n[{index}/{total}] 中文：{sentence.zh}\n日语：{sentence.ja}", flush=True)


def startAgent():
    import argparse
    from time import perf_counter
    from app.audio import VoicePlayer, list_output_devices

    parser = argparse.ArgumentParser()
    parser.add_argument("--list-audio-devices", action="store_true", help="列出可用输出设备")
    parser.add_argument("--test-voice", action="store_true", help="不用聊天模型，试听两句中日文配对台词")
    parser.add_argument("--thread-id", default="kurisu-001", help="会话标识；指定新值可测试新提示词而不删除旧记录")
    args = parser.parse_args()
    if args.list_audio_devices:
        list_output_devices()
        return
    if args.test_voice:
        from app.audio import SpeechLine
        player = VoicePlayer(on_sentence=show_sentence)
        try:
            player.speak_sentences([
                SpeechLine("别着急，我们慢慢说。", "焦らないで、ゆっくり話しましょう。"),
                SpeechLine("这样一边听，一边看中文就能理解了吧。", "これなら、声を聞きながら中国語を読めるでしょう。"),
            ])
            while not player.wait(0.1):
                pass
        except KeyboardInterrupt:
            pass
        finally:
            player.close()
        return

    from app.brain import buildAgent
    agent = buildAgent()
    avatar = AvatarWindow()
    player = VoicePlayer(on_sentence=show_sentence)
    try:
        while True:
            tmpInput = input("请输入消息（quit 退出，/stop 停止语音）>>>>:\n").strip()
            if tmpInput == "quit":
                break
            if not tmpInput:
                continue
            player.stop()
            if tmpInput == "/stop":
                continue
            started_at = perf_counter()
            response = agent.invoke({
                "messages": tmpInput,
            }, config={"configurable": {"thread_id": args.thread_id}})
            answer = response["structured_response"]
            print(f"[模型] 回复耗时：{perf_counter() - started_at:.2f}s", flush=True)
            avatar.play(getattr(answer, "action", "平静"))
            player.speak_sentences(answer.sentences, emotion=getattr(answer, "emotion", None))
    except (EOFError, KeyboardInterrupt):
        pass
    finally:
        player.close()
    print("聊天结束")
