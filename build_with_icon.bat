@echo off
echo Cleaning previous builds...
call clean.bat

echo Installing requirements...
pip install -r requirements.txt

echo Creating new build...
pyinstaller --clean ^
    --name="JioSaavn_AI_Downloader" ^
    --icon=app_icon.ico ^
    --onefile ^
    --windowed ^
    --add-data="app_icon.ico;." ^
    --hidden-import=requests ^
    --hidden-import=mutagen ^
    --hidden-import=sanitize_filename ^
    guiu.py

echo Build complete!
pause 