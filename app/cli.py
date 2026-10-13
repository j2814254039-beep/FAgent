
from app.brain import buildAgent


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
        print(response["messages"][-1].content)
    print("聊天结束")
