from langchain.chat_models import init_chat_model
from app.config import getModelName, getKey, getReasoningEffor, getFloatSetting


def buildModel():
    modelName=getModelName()
    key=getKey()
    return init_chat_model(
        model=modelName, api_key=key, reasoning_effort=getReasoningEffor(),
        temperature=getFloatSetting("CHAT_TEMPERATURE", 0.9, 0.0, 2.0),
    )
