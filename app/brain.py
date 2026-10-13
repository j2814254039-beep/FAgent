import sqlite3
from langchain.agents import create_agent
from langgraph.checkpoint.sqlite import SqliteSaver
from app.config import getDataPath, getMemoryPath
from app.model import buildModel
from app.person import getPrompt
from app.tool.memory import remember, recall, buildStore


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
        store=store
    )
    return agent
