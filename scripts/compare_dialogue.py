"""同一模型/温度/结构下比较两版提示词，不加载或写入聊天与记忆数据库。"""
import argparse
import json
from datetime import datetime
from pathlib import Path

from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy

from app.model import buildModel
from app.person import getPrompt
from app.reply import Reply, REPLY_FORMAT_INSTRUCTIONS


CASES = ["今天终于把那个 bug 修了。", "今天有点累，就想坐一会儿。", "我刚买的奶茶洒了。", "你是不是在等我？"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or Path("outputs") / datetime.now().strftime("dialogue-compare-%Y%m%d-%H%M%S")
    output.mkdir(parents=True, exist_ok=False)
    model = buildModel()
    rows = []
    format_prompt = REPLY_FORMAT_INSTRUCTIONS
    for version, prompt in (("before", args.baseline.read_text(encoding="utf-8")), ("after", getPrompt())):
        agent = create_agent(model=model, tools=[], system_prompt=prompt + format_prompt, response_format=ToolStrategy(Reply))
        for message in CASES:
            result = agent.invoke({"messages": [{"role": "user", "content": message}]}, config={"recursion_limit": 8})
            reply = result["structured_response"]
            rows.append(dict(version=version, user=message, **reply.model_dump()))
            print(version, message, "=>", " / ".join(s.zh for s in reply.sentences), flush=True)
            (output / "results.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# 文字口吻对照", "", "使用同一模型、温度、逐句 schema，仅更换角色提示词。每个场景为独立会话。",
             "每项仅采样一次，不能作为稳定性或全面质量的统计结论；未读取或写入聊天/记忆数据库。", ""]
    for message in CASES:
        lines += [f"## 用户：{message}", ""]
        for row in (r for r in rows if r["user"] == message):
            lines += [f"### {row['version']}（整轮情感：{row['emotion']}）", ""]
            for sentence in row["sentences"]:
                lines.extend([f"- 中：{sentence['zh']}", f"- 日：{sentence['ja']}"])
            lines.append("")
    (output / "README.md").write_text("\n".join(lines), encoding="utf-8")
    print("文字对照：", output.resolve())


if __name__ == "__main__":
    main()
