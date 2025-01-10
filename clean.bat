@echo off
echo Cleaning up...

:: Kill any running instances
taskkill /F /IM JioSaavn_AI_Downloader.exe 2>nul

:: Wait a moment
timeout /t 2 /nobreak >nul

:: Remove old files
if exist "dist" rd /s /q "dist"
if exist "build" rd /s /q "build"
if exist "*.spec" del /f /q *.spec

echo Cleanup complete! 