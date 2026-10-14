import sqlite3
from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime
from uuid import uuid4

from langgraph.store.sqlite import SqliteStore

from app.config import getMemoryPath

NAMESPACE = ("facts", "me")
def buildStore() -> SqliteStore:
    """造一个存磁盘的仓库。跟你写过的 checkpointer 一个套路，只是换了类。"""
    conn = sqlite3.connect(
        str(getMemoryPath()),
        check_same_thread=False,
        isolation_level=None,   # 必须！不加 store 一写入就报 transaction 错
    )
    return SqliteStore(conn)

@tool
def remember(fact: str, runtime: ToolRuntime) -> str:
    """当用户和你交流，你觉得很有意思，或者你觉得
    用户对这个事情有很强烈的情绪的时候，就可以考虑用这个函数记下来
    当然，你觉得你自己很感兴趣现在的聊天，不希望忘记，也可以记下来。
    但是记住，记忆是有限的，不要滥用这个方法。你可以在多轮对话后，
    总结关键点再记忆，如果当前这个事情非常非常非常关键，你希望清晰
    记忆，就可以直接不概括，直接记忆当前节点内容，否则不要频繁调用该工具，
    滥用你的记忆。
    Args: fact: 要记得的东西，一般长段内容需要概括总结。关键点可以直接记忆
          runtime: 调用工具的时间
        """
    key = str(uuid4())
    runtime.store.put(NAMESPACE, key, {"fact": fact})
    return f"记忆中……{fact}"

@tool
def recall(runtime: ToolRuntime) -> str:
    """
    当回答关于用户的内容，或者用户表现出你应该知道这件事，而当前上下文
    找不到相关内容时，就可以调用这个函数。一定是上下文找不到内容再启用，
    否则浪费用户时间来等待回应
    """
    items = runtime.store.search(NAMESPACE)
    if not items:
        return "还没有记住关于他的任何事。"
    return "\n".join(f"- {item.value['fact']}" for item in items)