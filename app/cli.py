
import threading
import time

from app.brain import buildAgent
from app.voice import playAudio, synthesizeSentences


def typewriter(text: str, delay: float = 0.06) -> None:
    """逐字打印，模拟打字机。delay 是每个字之间的间隔（秒）。"""
    for ch in text:
        print(ch, end="", flush=True)
        time.sleep(delay)
    print()


def startAgent():
    agent = buildAgent()
    while True:
        print("请输入消息>>>>:")
        tmpInput = input()
        if (tmpInput == "quit"):
            break
        response = agent.invoke({
            "messages": tmpInput,
        }, config={
            "configurable": {"thread_id": "kurisu-001"}
        })
        answer = response["structured_response"]

        # 后台线程：中文逐字浮现。不占主线程，所以音频能同时播。
        typer = threading.Thread(target=typewriter, args=(answer.zh,), daemon=True)
        typer.start()

        # 主线程：日语「合成一句 → 播完 → 再合成下一句」。
        # playAudio 会阻塞到整句放完，所以句与句不会重叠。
        try:
            for audio in synthesizeSentences(answer.ja, answer.emotion):
                playAudio(audio)
        except Exception as exc:
            # 声音是增强，不是核心 —— 挂了也要能继续聊天
            print(f"\n（语音不可用：{type(exc).__name__}）")

        typer.join()   # 等中文打完，再进入下一轮
        print()

    print("聊天结束")
