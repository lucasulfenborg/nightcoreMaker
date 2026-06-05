@echo off
REM ============================================================
REM  Nightcore Maker - one-click build to a standalone .exe
REM  Run this on Windows. It will:
REM    1) install PyInstaller (needs Python from python.org)
REM    2) download a static ffmpeg + ffprobe
REM    3) bundle everything into dist\NightcoreMaker.exe
REM  After it finishes, the .exe needs nothing else installed.
REM ============================================================
setlocal
cd /d "%~dp0"

echo.
echo === Nightcore Maker build ===
echo.

REM --- check python ---
where python >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python was not found.
  echo Install it from https://www.python.org/downloads/  ^(tick "Add Python to PATH"^)
  echo then run this script again.
  pause
  exit /b 1
)

REM --- pyinstaller ---
echo Installing PyInstaller...
python -m pip install --upgrade pip >nul
python -m pip install pyinstaller || (echo [ERROR] pip install failed & pause & exit /b 1)

REM --- get ffmpeg if not already here ---
if exist "ffmpeg.exe" if exist "ffprobe.exe" goto have_ffmpeg

echo Downloading ffmpeg ^(this is the audio engine, ~80 MB^)...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$url='https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip';" ^
  "Invoke-WebRequest -Uri $url -OutFile ffmpeg.zip;" ^
  "Expand-Archive -Path ffmpeg.zip -DestinationPath ffmpeg_tmp -Force;" ^
  "$bin=Get-ChildItem -Path ffmpeg_tmp -Recurse -Filter ffmpeg.exe | Select-Object -First 1 | Split-Path;" ^
  "Copy-Item (Join-Path $bin 'ffmpeg.exe') 'ffmpeg.exe' -Force;" ^
  "Copy-Item (Join-Path $bin 'ffprobe.exe') 'ffprobe.exe' -Force;" ^
  "Remove-Item ffmpeg.zip,ffmpeg_tmp -Recurse -Force"
if errorlevel 1 (
  echo [ERROR] ffmpeg download failed. Check your internet connection and retry,
  echo or manually place ffmpeg.exe and ffprobe.exe next to this script.
  pause
  exit /b 1
)

:have_ffmpeg
echo.
echo Building the .exe ...
REM Build from the .spec so the app icon and bundled icon files are included.
python -m PyInstaller --noconfirm NightcoreMaker.spec
if errorlevel 1 (echo [ERROR] build failed & pause & exit /b 1)

echo.
echo === Done! ===
echo Your program is here:  "%~dp0dist\NightcoreMaker.exe"
echo You can move that single .exe anywhere - it needs nothing installed.
echo.
pause
endlocal
