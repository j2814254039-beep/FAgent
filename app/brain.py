import sqlite3
from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langgraph.checkpoint.sqlite import SqliteSaver
from app.reply import Reply, REPLY_FORMAT_INSTRUCTIONS

from app.config import getDataPath
from app.model import buildModel
from app.person import getPrompt
from app.tool.Memory.memory import remember, recall, buildStore

def buildAgent():
    model=buildModel()
    prompt=getPrompt() + REPLY_FORMAT_INSTRUCTIONS
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
