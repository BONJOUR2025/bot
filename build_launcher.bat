@echo off
echo ============================================
echo  BONJOUR Bot Service Launcher - Build
echo ============================================
echo.

REM Check if PyInstaller is installed
python -m pyinstaller --version >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installing PyInstaller...
    pip install pyinstaller
)

echo [INFO] Building launcher.exe...
echo.

python -m pyinstaller ^
    --onefile ^
    --windowed ^
    --name "Launcher" ^
    --clean ^
    launcher.py

if errorlevel 1 (
    echo.
    echo [ERROR] Build failed!
    pause
    exit /b 1
)

echo.
echo ============================================
echo  Done! Executable: dist\Launcher.exe
echo  Copy Launcher.exe to the project root and
echo  double-click to start the service.
echo ============================================
pause
