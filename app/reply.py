"""模型直接配对中日文，避免按标点机械拆分后翻译错位。"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


Emotion = Literal[
    "平静", "傲娇", "傲娇提醒", "伤感", "微微生气",
     "心虚", "心虚掩饰", "害羞", "吐槽", "吐槽受不了", "安慰", "悲伤", "微微悲伤", "冷静吐槽",
    "无语说教", "认真", "说教", "克制说教", "温和劝告", "温和说教", "超认真",
]
Action = Literal[
    "walk"
]

REPLY_FORMAT_INSTRUCTIONS = (
    "\n最终回复请使用 emotion 和 sentences 结构化格式。"
    "action 是本轮应该的动作，至少选择一个行为"
    "emotion 是本轮整段回复唯一的情感，根据整段内容选择一次，所有句子共用；下一轮可以重新选择。"
    "sentences 每项只包含一句日文 ja 及其对应中文 zh，不要为每句话设置 emotion。"
    "按自然句意分句，保留句内停顿标点。角色示例仅作语气参考，不要照搬整段输出格式。"
)


class ReplySentence(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    zh: str = Field(min_length=1, description="这句日文对应的自然中文口语，保留语气而非逐词硬译，不额外补充说教。动作描写可省略。")
    ja: str = Field(min_length=1, max_length=180, description="一句贴合用户刚才所说内容的日文口语。不含动作描写，不刻意添加喘气、结巴或句首促音。")


class Reply(BaseModel):
    emotion: Emotion = Field(description="本轮整段回复唯一的情感，所有句子使用同一情感和参考模板。普通接话用平静，低落失意用伤感，轻微难过用微微悲伤（悲伤为兼容标签），轻度不满或抱怨用微微生气；嘴硬并掩饰关心或害羞时可用傲娇，带埋怨但仍关心的提醒可用傲娇提醒；慌张否认用心虚，故作轻松掩饰用心虚掩饰；明显嫌弃或不耐烦时可用吐槽受不了；克制地表达不满并提醒时用克制说教，关心地劝人休息或不要勉强时用温和劝告（温和说教为兼容标签）；下一轮可重新选择。")
    action: Action = Field(description="本轮需要的角色动作，所有句子就一个行为即可")
    sentences: list[ReplySentence] = Field(
        min_length=1, max_length=12,
        description="按说话顺序排列，中文和日文逐句对应。日常接话通常1到2句，回应到点就停；解释问题按需展开。不按逗号切碎，不把整段翻译放进最后一项。",
    )

    @model_validator(mode="before")
    @classmethod
    def read_legacy_sentence_emotions(cls, value):
        """旧会话中的逐句情感归并到首个标签；显式整轮标签优先。"""
        if not isinstance(value, dict) or not isinstance(value.get("sentences"), list):
            return value
        sentences = value["sentences"]
        legacy = [s for s in sentences if isinstance(s, dict) and "emotion" in s]
        if not legacy:
            return value
        normalized = dict(value)
        if "emotion" not in normalized:
            normalized["emotion"] = legacy[0]["emotion"]
        normalized["sentences"] = [
            {key: item for key, item in sentence.items() if key != "emotion"}
            if isinstance(sentence, dict) else sentence
            for sentence in sentences
        ]
        return normalized
