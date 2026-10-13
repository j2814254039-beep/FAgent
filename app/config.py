from pathlib import Path
import os
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent/ ".env"
load_dotenv(dotenv_path=env_path)


def getMemoryPath():
    P=Path(__file__).parent.parent/"Memory"/"remember.db"
    if not os.path.exists(P):
        P.parent.mkdir(parents=True,exist_ok=True)
    return P
def getDataPath():
    P=Path(__file__).parent.parent/"Data"/"chat.db"
    if not os.path.exists(P):
        P.parent.mkdir(parents=True, exist_ok=True)
    return P
def getPersonPath():
    P = Path(__file__).parent.parent/ "Person" / "kurisu.md"
    return P
def getKey():
    API_KEY = os.getenv("API_KEY")
    return API_KEY
def getModelName():
    MODEL_NAME = os.getenv("MODEL_NAME")
    return MODEL_NAME