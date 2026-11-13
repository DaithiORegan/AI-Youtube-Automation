@echo off
setlocal
cd /d "%~dp0"
set "STORYFORGE_COMFY=tools\ComfyUI_windows_portable"
if not exist "%STORYFORGE_COMFY%\python_embeded\python.exe" (
  echo Extract the official NVIDIA portable ComfyUI bundle under tools\ComfyUI_windows_portable
  echo Or run your existing ComfyUI installation with --lowvram.
  echo See docs\WINDOWS_FIRST_FILM.md
  pause
  exit /b 1
)
cd /d "%STORYFORGE_COMFY%"
python_embeded\python.exe -s ComfyUI\main.py --windows-standalone-build --lowvram
pause
