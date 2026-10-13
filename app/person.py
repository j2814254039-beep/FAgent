from app.config import getPersonPath
def getPrompt()->str:
    return getPersonPath().read_text(encoding="utf-8")
