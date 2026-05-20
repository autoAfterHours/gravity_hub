@echo off
REM ============================================================
REM  build_exe.bat — Build Orbit360 as a self-contained .exe
REM
REM  Just double-click this file. That's it.
REM  The finished package will be at:  dist\orbit360\orbit360.exe
REM ============================================================

setlocal

REM Always run from the folder this script lives in,
REM regardless of where it was launched from.
cd /d "%~dp0"

echo.
echo ============================================================
echo   Orbit360 ^— EXE Build
echo ============================================================
echo.

REM ── Auto-install build tools if missing ──────────────────────
echo Checking build tools...
pip show pyinstaller >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo   PyInstaller not found ^— installing...
    pip install pyinstaller pyinstaller-hooks-contrib
    if %ERRORLEVEL% neq 0 (
        echo.
        echo ERROR: pip install failed. Make sure Python is installed and on your PATH.
        pause
        exit /b 1
    )
)

REM ── Install app dependencies ──────────────────────────────────
echo   Installing app dependencies...
pip install -r requirements.txt --quiet

REM ── Clean previous build ──────────────────────────────────────
echo   Cleaning previous build...
if exist "build"         rmdir /s /q "build"
if exist "dist\orbit360" rmdir /s /q "dist\orbit360"

echo.
echo Building... (this takes a minute or two)
echo.

pyinstaller orbit360.spec --noconfirm --clean

if %ERRORLEVEL% neq 0 (
    echo.
    echo BUILD FAILED ^— see errors above.
    pause
    exit /b %ERRORLEVEL%
)

REM ── Copy systems/ as a sidecar next to the exe ────────────────
REM paths.py prefers a sidecar systems\ folder next to orbit360.exe
REM over the bundled copy inside _internal\. This makes scripts
REM visible, editable, and updatable without rebuilding the exe.
echo Copying systems\ as sidecar next to exe...
xcopy /E /I /Y "systems" "dist\orbit360\systems" > nul
if %ERRORLEVEL% neq 0 (
    echo WARNING: Could not copy systems\ sidecar — scripts will use the bundled copy.
)

echo.
echo ============================================================
echo   BUILD SUCCEEDED
echo   Package: dist\orbit360\
echo ============================================================
echo.
echo Hand the entire dist\orbit360\ folder to users.
echo They just double-click orbit360.exe — no Python needed.
echo.
echo REMINDER: Users must run this once before first use:
echo   playwright install chromium
echo   (installs the browser ^— only needed one time per machine)
echo.
pause
endlocal
