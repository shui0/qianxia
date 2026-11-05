@echo off
chcp 65001 >nul
setlocal
rem ── 复制成 start-voice.bat 再按自己的环境改（那个文件已被 .gitignore 忽略）──
rem 用法：把下面的路径换成你自己的，然后双击运行。

set PY=<你的 python.exe 路径，例如 D:\conda\envs\gptsovits\python.exe>
set REPO=<GPT-SoVITS 仓库路径，例如 D:\gptsovits\repo>
set ADAPTER=%~dp0apps\voice

echo [1/3] 启动 GPT-SoVITS 推理服务 (127.0.0.1:9880) ...
start "GPT-SoVITS" /D "%REPO%" cmd /k ""%PY%" api_v2.py -a 127.0.0.1 -p 9880 -c GPT_SoVITS/configs/tts_infer.yaml"

echo [2/3] 等模型加载（约 20 秒）...
timeout /t 20 /nobreak >nul

echo [3/3] 启动语音适配层 (127.0.0.1:8000) ...
set GPT_SOVITS_URL=http://127.0.0.1:9880/tts
rem 参考音频：请使用你有权使用的音源（自己录的 / 明确授权的 / 原创虚拟歌手）
rem 参考文本：适配层会读与 wav 同名的 .txt（UTF-8）
set REF_AUDIO_QINGXIA=<参考音频路径，例如 D:\refs\my_voice.wav>
set REF_TEXT_QINGXIA=<该段音频对应的文字>
set REF_LANG_QINGXIA=zh
set DEFAULT_SPEAKER=qingxia
start "语音适配层" /D "%ADAPTER%" cmd /k ""%PY%" -m uvicorn app:app --host 127.0.0.1 --port 8000

echo.
echo 两个服务已在新窗口启动。关掉窗口即停止。
echo 验证: http://127.0.0.1:8000/healthz
pause
