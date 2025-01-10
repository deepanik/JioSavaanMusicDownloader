import PyInstaller.__main__
import os
import shutil
import time

def build_app():
    # Get the current directory
    current_dir = os.path.dirname(os.path.abspath(__file__))
    icon_path = os.path.join(current_dir, 'icon.ico')
    
    # Define build arguments with updated filename
    build_args = [
        'JioMusicDLD.py',
        '--name=JioSaavn_AI_Downloader',
        '--onefile',
        '--windowed',
        f'--icon={icon_path}',
        '--clean',
        f'--distpath={os.path.join(current_dir, "dist")}',
        f'--workpath={os.path.join(current_dir, "build")}',
        '--noconfirm',
        '--hidden-import=requests',
        '--hidden-import=mutagen',
        '--hidden-import=sanitize_filename',
    ]
    
    try:
        # Remove old build files
        for path in ['build', 'dist']:
            if os.path.exists(path):
                shutil.rmtree(path)
                time.sleep(1)  # Wait for file system
                
        # Run PyInstaller
        PyInstaller.__main__.run(build_args)
        
    except PermissionError:
        print("Error: Cannot access files. Please close any running instances of the application.")
        input("Press Enter to try again...")
        build_app()  # Retry
    except Exception as e:
        print(f"Build error: {str(e)}")
        input("Press Enter to exit...")

if __name__ == "__main__":
    build_app() 