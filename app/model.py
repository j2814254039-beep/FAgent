from langchain.chat_models import init_chat_model
from openai.types.shared_params import reasoning_effort

from app.config import getModelName, getKey, getReasoningEffor


def buildModel():
    modelName=getModelName()
    key=getKey()
    return init_chat_model(model=modelName,api_key=key,reasoning_effort=getReasoningEffor())