from pathlib import Path
import os
import math
from dotenv import load_dotenv


env_path = Path(__file__).parent.parent/ ".env"
load_dotenv(dotenv_path=env_path)


def getFloatSetting(name, default, minimum, maximum):
    value = float(os.getenv(name, str(default)))
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError(f"{name} 必须在 {minimum} 到 {maximum} 之间")
    return value

def getIfUseVector():
    return os.getenv("USE_VECTOR")
def getVoiceFloat(name, default, minimum, maximum):
    return getFloatSetting(name, default, minimum, maximum)
def getActionPath():
    return os.getenv("ACTION_PATH")
def getVoicePath():
    return os.getenv("VOICE_PATH")
def getReasoningEffor():
    return os.getenv("REASONING_EFFOR")
def getAudioTemplatePath():
    return os.getenv("VOICE_TEMPLATE_PATH")
def getTextLang():
    return os.getenv("TEXT_LANG")
def getVoiceOutputLang():
    return os.getenv("VOICE_OUTPUT_LANG")
def getMediaType():
    return os.getenv("MEDIA_TYPE")

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
