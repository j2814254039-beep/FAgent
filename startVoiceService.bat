@echo off
chcp 65001 >nul
title GPT-SoVITS 语音服务 (v5turbo / 9881)

rem ============================================================
rem  语音服务启动器
rem
rem  作用：把 GPT-SoVITS 的 API 服务跑起来，供 app/voice.py 调用。
rem  它是独立进程，跟 agent 分开 —— agent 随便重启，它不用重启。
rem
rem  用完关闭：直接关掉这个窗口，或者在窗口里按 Ctrl+C。
rem ============================================================

rem 【必须】解决显存碎片导致的 CUDA out of memory
set PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

rem 切到 GPT-SoVITS 目录 —— api_v2.py 用的是相对路径，不切会找不到文件
cd /d "D:\GPTV5\GPT-SoVITS"

echo ============================================================
echo   正在启动语音服务 (v5turbo)
echo.
echo   - 模型加载约需 30 秒，请耐心等待
echo   - 看到 "Uvicorn running on http://127.0.0.1:9881" 即成功
echo   - 成功后【不要关这个窗口】，它要一直开着
echo ============================================================
echo.

rem 【关键】必须用 GPT-SoVITS 自带的 runtime python，
rem        不是 D:\MyAiAgent\.venv 里那个（那个没装 torch）
"D:\GPT-SoVITS-v2pro-20250604-nvidia50\runtime\python.exe" api_v2.py -a 127.0.0.1 -p 9881

echo.
echo 服务已退出。
pause
