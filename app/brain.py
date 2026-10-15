import sqlite3
from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langgraph.checkpoint.sqlite import SqliteSaver
from pydantic import BaseModel, Field
from typing import Literal
from app.config import getDataPath
from app.model import buildModel
from app.person import getPrompt
from app.tool.memory import remember, recall, buildStore

class Reply(BaseModel):
    zh: str = Field(description="给用户看的中文回复，可以带 *动作描写*")
    ja: str = Field(description="用于语音朗读的日文台词，不要动作描写")
    emotion:  Literal[                                   # ← str 改成 Literal
        "傲娇", "心虚", "害羞", "吐槽", "安慰", "悲伤",
        "冷静吐槽", "无语说教", "认真", "说教", "温和说教", "超认真", "震惊",
    ] = Field(description="这句台词的情绪")
def buildAgent():
    model=buildModel()
    prompt=getPrompt()
    conn = sqlite3.connect(getDataPath(), check_same_thread=False)
    store=buildStore()
    agent=create_agent(
        model=model,
        system_prompt=prompt,
        checkpointer=SqliteSaver(conn),
        tools=[remember,recall],
        store=store,
        response_format=ToolStrategy(Reply)
    )
    return agent
