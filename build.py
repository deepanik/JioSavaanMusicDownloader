import PyInstaller.__main__
import os
import sys

def build_app():
    # Get the current directory
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Define paths
    icon_path = os.path.join(current_dir, 'icon.ico')
    dist_path = os.path.join(current_dir, 'dist')
    build_path = os.path.join(current_dir, 'build')
    
    # Build command
    build_args = [
        'guiu.py',
        '--name=JioSaavn_AI_Downloader',
        '--onefile',
        '--windowed',
        '--clean',
        '--noconfirm',
        f'--distpath={dist_path}',
        f'--workpath={build_path}',
        f'--specpath={current_dir}',
        '--hidden-import=requests',
        '--hidden-import=mutagen',
        '--hidden-import=sanitize_filename',
    ]
    
    # Add icon if it exists
    if os.path.exists(icon_path):
        build_args.extend([
            f'--icon={icon_path}',
            f'--add-data={icon_path};.'
        ])
    
    # Run PyInstaller
    PyInstaller.__main__.run(build_args)

if __name__ == "__main__":
    build_app() 