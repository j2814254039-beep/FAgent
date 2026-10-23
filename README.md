# MyAiAgent

命令行角色聊天：模型返回逐句配对的中文、日文，以及整轮唯一的情感，GPT-SoVITS 用同一参考模板合成这一轮的日文语音。

## 项目结构

- `agent.py`：入口。
- `app/cli.py`：聊天循环、逐句字幕、独立试听入口。
- `app/reply.py`：逐句配对的中文、日文和整轮情感结构。
- `app/brain.py`：Agent、结构化回复、SQLite 会话检查点。
- `app/model.py`、`app/person.py`：模型与角色提示词。
- `app/tool/Memory/memory.py`：长期记忆的保存与检索。
- `app/voice.py`：情绪模板与 GPT-SoVITS HTTP 请求。
- `app/audio.py`：输出设备选择、WAV 解码与淡入淡出、回调播放、下一句预取。
- `app/config.py`、`.env`：配置；`Data/`、`Memory/`：数据库；`Person/`：角色。
- `startVoiceService.bat`：启动独立的 GPT-SoVITS 服务。

## 启动

先启动 `startVoiceService.bat`，等服务就绪，然后运行：

```powershell
.venv\Scripts\python.exe agent.py
```

每句开始播放前，显示对应中文和日文；播完并短暂停顿后，再显示下一句。
中文由模型与日文逐句配对，避免两种语言按标点拆分后错位。
播放当前句时后台预生成下一句，可继续输入。
输入 `/stop` 停止当前播放，提交新消息也会停止旧播放；`quit` 退出。
取消播放不会取消服务端正在进行的推理；新语音请求需要等待旧请求返回或超时。

## 耳机输出

默认 `VOICE_OUTPUT_DEVICE=headphones`：仅在名称含 Headphones、Headset 或“耳机”的设备中选择，优先 WASAPI。
设备不可用时报错，不自动切到扬声器。查看设备：

```powershell
.venv\Scripts\python.exe agent.py --list-audio-devices
```

在 `.env` 中可配置完整名称、名称片段或设备编号，例如：

```dotenv
VOICE_OUTPUT_DEVICE=Headphones 1 (Realtek HD Audio 2nd output with SST)
VOICE_READ_TIMEOUT=60
```

编号可能随插拔、重启变化，长期配置建议使用名称。
若想跟随系统默认输出，可设置 `VOICE_OUTPUT_DEVICE=default`。
当前机器的 Realtek 耳机位于 WDM-KS 接口，因此使用回调播放；该接口不支持阻塞式写入。
Lian II 耳机优先使用 WASAPI。后台播放线程会初始化 COM；本机对照验证表明，
缺少这一步会导致 WASAPI 在主线程可用、后台线程启动失败。
初始化与释放按 [Microsoft 的线程初始化要求](https://learn.microsoft.com/en-us/windows/win32/learnwin32/initializing-the-com-library) 配对执行。

## 杂音、语速和停顿

默认参数已生效，不需要修改 `.env`。需要调整时，可以添加：

```dotenv
VOICE_SPEED=0.95
VOICE_SENTENCE_PAUSE_MS=350
VOICE_GAIN=0.85
VOICE_FADE_MS=8
```

| 参数 | 默认值 | 作用 |
| --- | --- | --- |
| `VOICE_SPEED` | `0.95` | TTS 语速，越小越慢；可试 `0.90`，范围 0.5–1.5 |
| `VOICE_SENTENCE_PAUSE_MS` | `350` | 两句之间额外停顿的毫秒数，可试 `500`，范围 0–2000 |
| `VOICE_GAIN` | `0.85` | 播放增益，为峰值留余量；可试 `0.70`，范围 0–1 |
| `VOICE_FADE_MS` | `8` | 每句首尾淡入淡出，减轻边沿突变声；范围 0–30 |

每句使用 `cut0`，不再用 `cut5` 把逗号、省略号处切成碎片。
TTS 的 `fragment_interval=0` 保留，由客户端统一添加句间停顿，避免重复添加。
句内停顿由标点和模型生成；这里不保证精确的逐字时间对齐。

播放前缓存完整的一句，回调只复制已准备好的 PCM，不等待网络、不加锁。
首尾淡入淡出、增益在回调之外处理，设备使用较宽裕的缓冲；出现设备欠载会输出诊断。
这些修改处理播放突变及峰值余量，不是对合成音频做通用降噪。
若整句持续有底噪，需要对比原始生成 WAV 和参考音频，继续定位音源或设备问题。

## 整轮情感、逐句输出与延迟

每轮 assistant 回复只选择一次情感，全部句子共享该情感和参考模板；下一轮回复可以重新选择。
模型输出结构为：

```json
{
  "emotion": "安慰",
  "sentences": [
    {"zh": "别着急。", "ja": "焦らないで。"},
    {"zh": "我们慢慢说。", "ja": "ゆっくり話しましょう。"}
  ]
}
```

播放器在整轮入队时固定情感，避免预取下一句时切换模板。
兼容旧的逐句情感数据：没有整轮标签时沿用第一句的标签，整轮统一使用；显式整轮标签优先。
CLI 不再一次打印完整回复，而是在每句播放前显示对应字幕。
语音失败时会显示尚未展示的剩余文本，已经显示的句子不重复。

单句合成使用 `streaming_mode=0`；只等待这一句，不等待整段回复的全部音频。
播放当前句时预取下一句，最多缓存当前句和下一句；若合成慢于播放，句间仍可能额外等待。
从服务端 WAV 读取实际采样率；WASAPI 允许系统做设备采样率/声道转换。
`use_cuda_graph=False` 保持原设置。

`VOICE_TIMINGS=1` 可显示首句准备耗时和实际使用的设备。
当前仍使用 `agent.invoke` 等待完整结构化回复，尚未实现模型 token 到语音的实时输出。
GPT-SoVITS 冷启动和首次推理也需要额外时间，服务可在多轮聊天间保持运行。

本机 2026-10-16 最新两句试听：首句准备约 0.85 秒，通过 Lian II 的 WASAPI 播放，
未记录到设备欠载。结果仅代表本次预热后的样本；电流声是否消失需实际试听确认。

## 验证

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

覆盖中日文配对结构、字幕顺序、下一句预取、句间停顿、取消后丢弃旧字幕、
音频失败后的文本保留、淡入淡出、截断 WAV、设备初始化和启动失败重试，
以及整轮情感、旧结构兼容和连续两轮不会相互继承情感。

启动语音服务后，不调用聊天模型、不写聊天记录，直接试听两句：

```powershell
.venv\Scripts\python.exe agent.py --test-voice
```

## 气声里的金属感与模板对照

2026-10-16 检查了现有 14 个参考模板：均为 32 kHz 单声道、16-bit PCM，时长约 4.48–8.29 秒，
未检测到接近满幅的削波样本。这不能证明没有气声、混响、背景音乐、降噪伪影或错误转写。
“吐槽”的参考文本含「痛い目で気弱そうな…」，与旧 ASR 对照也有出入，值得听原音核对，尚未修改。

旧角色提示词主动要求用句首促音、结巴和省略号制造吸气，现已改为自然标点和按需犹豫。
金属感还可能来自参考素材或模型的合成过程，不能只凭声音描述判断是哪一个环节。

已生成的 [对照试听](outputs/voice-compare-20261016-230259/README.md) 包含三种原始参考、
三种模板 × 两种步数的六条合成，以及普通标点/刻意换气标记的两条对照。
同一实验保持文本、seed=42、语速一致，直接保存服务端 WAV，未加均衡或降噪。
先比较同一步数的不同模板，再比较同一模板的 4/8 步。

本机 v5turbo 默认 4 步；[项目推理界面](https://github.com/RVC-Boss/GPT-SoVITS/blob/main/GPT_SoVITS/inference_webui_fast.py)
提供 4/8/16/32 步。更多步数不保证气声更自然，因此默认值仍交给服务端。
听过对照后，可在 `.env` 单独调整以下参数；每次改一个，重启聊天程序：

```dotenv
# 可选：临时让所有情绪使用同一个模板，便于定位；注释掉恢复情绪映射
# VOICE_REFERENCE_TEMPLATE=认真
# 可选：试用 8 步，注释掉恢复服务端默认
# VOICE_SAMPLE_STEPS=8
```

平静情绪目前复用“认真”模板，名称不代表已验证音质最佳。
挑参考时优先试听清晰的自然说话片段，检查气声本身、残留配乐/混响、切口是否截字及转写是否逐字吻合。
不用升采样伪造高频；不要为了去掉气声就先做强降噪。
所有模板都有类似问题时，再检查训练素材、模型与声码器，换模板未必足够。

重新生成对照（不改原参考文件、不写聊天数据库）：

```powershell
.venv\Scripts\python.exe -m scripts.compare_voice --compare-breath-markers
```

## DeepSeek 的聊天口吻

角色文件仍是 `Person/kurisu.md`，旧版已备份为 `Person/kurisu.before-natural-20261016-230056.md`。
保留聪明、好奇、偶尔嘴硬的角色气质；去掉长动作与身份争辩的固定演出，普通接话可以“平静”。
日常通常一两句，针对具体内容回应，中文按口语表达，不额外补一段说教或机械反问。
`sentences` 配对结构、逐句字幕和记忆功能继续保留。

`CHAT_TEMPERATURE=0.9` 为当前默认，可在 `.env` 调整；温度只控制采样随机性，不是“去 AI 感”开关。
当前 `REASONING_EFFOR=none` 保持不变。[DeepSeek API 文档](https://api-docs.deepseek.com/api/create-chat-completion/)
说明 temperature 在思考模式下不生效，frequency_penalty/presence_penalty 已不生效，故未加重复惩罚参数。

旧对话中的习惯表达也可能继续影响输出。可用新会话检验口吻，旧记录保留：

```powershell
.venv\Scripts\python.exe agent.py --thread-id natural-style-test
```

提供文字对照脚本，但本次尚未完成 DeepSeek 在线对照：当前环境限制了外部网络，
自动审批拒绝发送本地角色提示词。需获得对提示词外发的明确授权后再执行。
该脚本会将旧/新完整提示词与四条测试消息发送到已配置的模型服务，产生少量 API 用量；
它不读取或写入会话、记忆数据库，结果保存在被 Git 忽略的 `outputs/` 下。

```powershell
.venv\Scripts\python.exe -m scripts.compare_dialogue --baseline Person/kurisu.before-natural-20261016-230056.md
```
