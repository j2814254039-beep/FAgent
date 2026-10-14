
from app.brain import buildAgent
from app.voice import sendVoiceRequest
import winsound
winsound.PlaySound



def startAgent():
    agent = buildAgent()
    while True:
        print("请输入消息>>>>:")
        tmpInput = input()
        if (tmpInput == "quit"):
            break
        response = agent.invoke({
            "messages": tmpInput,
        },config={
            "configurable":{"thread_id":"kurisu-001"}
        })
        answer=response["structured_response"]
        print(">>>>>>日语"+answer.ja)

        voice=sendVoiceRequest(answer.ja)
        winsound.PlaySound(voice,winsound.SND_MEMORY)
        print(answer.zh)
    print("聊天结束")
