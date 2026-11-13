@echo off
setlocal
cd /d "%~dp0"
echo Storyforge - local Windows setup. No paid APIs.
echo This installs Python packages and downloads about 350 MB of voice models.
echo See docs\WINDOWS_FIRST_FILM.md for Ollama and ComfyUI setup.
if not exist ".venv\Scripts\python.exe" (
  py -3.12 -m venv .venv
  if errorlevel 1 py -3 -m venv .venv
)
if not exist ".venv\Scripts\python.exe" (
  echo Install Python 3.12 from python.org with the Python launcher enabled.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pip install -e ".[voice]"
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m studio models
if errorlevel 1 goto failed
echo.
echo Python and narration setup complete. Next: follow docs\WINDOWS_FIRST_FILM.md
echo Start Ollama and ComfyUI, then double-click START_STUDIO.bat
pause
exit /b 0
:failed
echo Setup stopped. Read the error above, fix it, then run this file again.
pause
exit /b 1
