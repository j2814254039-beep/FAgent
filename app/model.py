from langchain.chat_models import init_chat_model

from app.config import getModelName, getKey


def buildModel():
    modelName=getModelName()
    key=getKey()
    return init_chat_model(model=modelName,api_key=key)