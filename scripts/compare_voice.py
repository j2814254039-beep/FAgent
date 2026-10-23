"""固定文本/随机种子，只改变模板或采样步数，导出原始 WAV 供盲听对比。"""
import argparse
import json
import shutil
import wave
from datetime import datetime
from pathlib import Path
from time import perf_counter

import numpy as np
import requests

from app.config import getVoicePath
from app.voice import TEMPLATES, buildVoicePayload


def inspect_wav(path):
    with wave.open(str(path), "rb") as wav:
        result = dict(seconds=round(wav.getnframes() / wav.getframerate(), 3),
                      sample_rate=wav.getframerate(), channels=wav.getnchannels(),
                      sample_width=wav.getsampwidth())
        if wav.getsampwidth() == 2 and wav.getnframes():
            pcm = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2").astype(np.float64) / 32768
            result["peak_dbfs"] = round(float(20 * np.log10(max(np.abs(pcm).max(), 1e-10))), 2)
            result["rms_dbfs"] = round(float(20 * np.log10(max(np.sqrt(np.mean(pcm * pcm)), 1e-10))), 2)
            result["near_full_scale_fraction"] = round(float(np.mean(np.abs(pcm) >= 0.999)), 6)
    return result


def comparison_cases(text, folders, steps, seed=42):
    cases = []
    for index, folder in enumerate(folders):
        ref_path, prompt = TEMPLATES[folder]
        for count in steps:
            payload = buildVoicePayload(text)
            payload.update(ref_audio_path=ref_path, prompt_text=prompt,
                           sample_steps=count, seed=seed, media_type="wav")
            cases.append((f"ref{index}-steps{count}.wav", folder, payload))
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--text", default="今日はもう遅いから、少し休んだら。")
    parser.add_argument("--folders", nargs="+", default=["傲娇+害羞", "认真", "安慰"])
    parser.add_argument("--steps", nargs="+", type=int, choices=[4, 8, 16, 32], default=[4, 8])
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--compare-breath-markers", action="store_true")
    args = parser.parse_args()
    missing = set(args.folders) - TEMPLATES.keys()
    if missing:
        parser.error("缺少模板：" + ", ".join(sorted(missing)))
    output = args.output or Path("outputs") / datetime.now().strftime("voice-compare-%Y%m%d-%H%M%S")
    output.mkdir(parents=True, exist_ok=False)
    audit = {name: dict(path=path, prompt=text, **inspect_wav(path))
             for name, (path, text) in TEMPLATES.items()}
    (output / "template-audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    for index, folder in enumerate(args.folders):
        shutil.copyfile(TEMPLATES[folder][0], output / f"reference-{index}.wav")
    cases = comparison_cases(args.text, args.folders, args.steps, args.seed)
    if args.compare_breath_markers:
        # 单独一对实验；两条文本仅在句首促音/省略号方面不同。
        plain = "今日はもう遅いから、少し休んだら。"
        breathy = "っ、今日は……もう遅いから……少し休んだら。"
        for label, text in (("plain", plain), ("breathy", breathy)):
            _, folder, payload = comparison_cases(text, args.folders[:1], [args.steps[0]], args.seed)[0]
            cases.append((f"markers-{label}.wav", folder, payload))
    results = []
    with requests.Session() as session:
        for filename, folder, payload in cases:
            row = dict(file=filename, template=folder, text=payload["text"],
                       steps=payload["sample_steps"], seed=args.seed, speed=payload["speed_factor"])
            started = perf_counter()
            try:
                with session.post(getVoicePath(), json=payload, timeout=(3, 90)) as response:
                    response.raise_for_status()
                    (output / filename).write_bytes(response.content)
                row.update(inspect_wav(output / filename))
                row["generation_seconds"] = round(perf_counter() - started, 3)
                print(f"{filename}: {folder}, {row['generation_seconds']}s", flush=True)
            except (requests.RequestException, ValueError, wave.Error, EOFError) as exc:
                row["error"] = str(exc)
                print(f"{filename}: {exc}", flush=True)
            results.append(row)
            (output / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# 气声金属感对照试听", "", "先听原始参考，再以相同音量比较合成音频。这里未加滤波或播放增益。",
             "统计指标不能衡量气声是否自然；以下不自动评判最佳模板。", "", "## 参考音频", ""]
    for i, folder in enumerate(args.folders):
        lines.append(f"- [{folder}](reference-{i}.wav)：{TEMPLATES[folder][1]}")
    lines += ["", "## 合成结果", "", "| 文件 | 模板 | 步数 | 生成秒数 |", "| --- | --- | --- | --- |"]
    for row in results:
        lines.append(f"| [{row['file']}]({row['file']}) | {row['template']} | {row['steps']} | {row.get('generation_seconds', '失败')} |")
    lines += ["", f"模板对比台词：{args.text}", "", f"固定 seed={args.seed}。同一模板比较步数，同一步数比较模板。",
              "markers-plain 与 markers-breathy 用于单独比较促音和省略号，文本见 results.json。",
              "请求顺序、缓存和随机数消耗都会影响结果。步数更多不保证更好，耗时也不是严格基准。",
              "如果所有模板都有同样金属感，继续排查训练素材、模型和声码器；不要仅凭文件名替换参考。", ""]
    (output / "README.md").write_text("\n".join(lines), encoding="utf-8")
    print("试听目录：", output.resolve())
    if any("error" in row for row in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
