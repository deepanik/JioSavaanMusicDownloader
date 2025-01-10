@echo off
echo Cleaning previous builds...
call clean.bat

echo Building JioSaavn AI Downloader...
python build.py

echo Build complete!

echo Moving executable to release folder...
if not exist "release" mkdir release
move /y "dist\JioSaavn_AI_Downloader.exe" "release\"

echo Done!
pause 