import sqlite3
from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langgraph.checkpoint.sqlite import SqliteSaver
from openai.types.beta.agent_browser_authentication_submit_param import Field
from pydantic import BaseModel

from app.config import getDataPath
from app.model import buildModel
from app.person import getPrompt
from app.tool.memory import remember, recall, buildStore

class Reply(BaseModel):
    zh: str = Field(description="给用户看的中文回复，可以带 *动作描写*")
    ja: str = Field(description="用于语音朗读的日文台词，不要动作描写")
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
