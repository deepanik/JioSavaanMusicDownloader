from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.label import Label
from kivy.uix.progressbar import ProgressBar
from kivy.uix.image import AsyncImage
from kivy.core.window import Window
from kivy.clock import Clock
from kivy.lang import Builder
from kivy.properties import StringProperty, NumericProperty
from kivymd.app import MDApp
from kivymd.uix.button import MDIconButton
from kivymd.uix.dialog import MDDialog
from kivymd.uix.button import MDFlatButton
import webbrowser
import requests
import json
import re
import os
from threading import Thread
import queue
from html import unescape
from sanitize_filename import sanitize
from mutagen.mp4 import MP4, MP4Cover
from io import BytesIO

# Set window size
Window.size = (800, 700)

KV = '''
#:import utils kivy.utils

<DownloaderGUI>:
    orientation: 'vertical'
    padding: 20
    spacing: 10
    canvas.before:
        Color:
            rgba: utils.get_color_from_hex('#f4f4f9')
        Rectangle:
            pos: self.pos
            size: self.size
    
    # Social Media Links Bar
    BoxLayout:
        size_hint_y: None
        height: '50dp'
        spacing: 10
        pos_hint: {'center_x': .5}
        
        MDIconButton:
            icon: "github"
            on_release: root.open_link("https://github.com/yourusername")
            theme_icon_color: "Custom"
            icon_color: utils.get_color_from_hex('#000000')
            
        MDIconButton:
            icon: "linkedin"
            on_release: root.open_link("https://linkedin.com/in/yourusername")
            theme_icon_color: "Custom"
            icon_color: utils.get_color_from_hex('#0077B5')
            
        MDIconButton:
            icon: "telegram"
            on_release: root.open_link("https://t.me/yourusername")
            theme_icon_color: "Custom"
            icon_color: utils.get_color_from_hex('#0088cc')
            
        MDIconButton:
            icon: "update"
            on_release: root.check_updates()
            theme_icon_color: "Custom"
            icon_color: utils.get_color_from_hex('#5c42f3')
    
    BoxLayout:
        size_hint_y: None
        height: '50dp'
        spacing: 10
        Label:
            text: 'Enter JioSaavn URL:'
            size_hint_x: None
            width: '120dp'
            color: 0, 0, 0, 1
        
        TextInput:
            id: url_input
            multiline: False
            size_hint_x: 1
            
        Button:
            text: 'Download'
            size_hint_x: None
            width: '100dp'
            on_press: root.start_download()
            background_color: utils.get_color_from_hex('#5c42f3')
            
    BoxLayout:
        size_hint_y: None
        height: '50dp'
        spacing: 10
        Label:
            text: 'Download Directory:'
            size_hint_x: None
            width: '120dp'
            color: 0, 0, 0, 1
            
        TextInput:
            id: dir_input
            multiline: False
            text: root.download_dir
            
        Button:
            text: 'Browse'
            size_hint_x: None
            width: '100dp'
            on_press: root.browse_directory()
            background_color: utils.get_color_from_hex('#5c42f3')
            
    ProgressBar:
        id: progress_bar
        max: 100
        height: '20dp'
        size_hint_y: None
        
    AsyncImage:
        id: album_art
        source: root.current_album_art
        size_hint: None, None
        size: '250dp', '250dp'
        pos_hint: {'center_x': .5}
        
    ScrollableLabel:
        id: status_text
        size_hint_y: 1
'''

class ScrollableLabel(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'
        self.text_widget = TextInput(
            multiline=True,
            readonly=True,
            background_color=[1, 1, 1, 0.8],
            foreground_color=[0, 0, 0, 1]
        )
        self.add_widget(self.text_widget)

class DownloaderGUI(BoxLayout):
    download_dir = StringProperty(os.path.join(os.getcwd(), "Downloads"))
    current_album_art = StringProperty('')
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.song_api = "https://www.jiosaavn.com/api.php?__call=webapi.get&token={}&type=song"
        self.album_api = "https://www.jiosaavn.com/api.php?__call=webapi.get&token={}&type=album"
        self.playlist_api = "https://www.jiosaavn.com/api.php?__call=webapi.get&token={}&type=playlist&_format=json"
        self.lyrics_api = "https://www.jiosaavn.com/api.php?__call=lyrics.getLyrics&ctx=web6dot0&api_version=4&_format=json&_marker=0%3F_marker%3D0&lyrics_id="
        self.album_song_rx = re.compile(r"https://www\.jiosaavn\.com/(album|song)/.+?/(.+)")
        self.playlist_rx = re.compile(r"https://www\.jiosaavn\.com/s/playlist/.+/(.+)")
        self.json_rx = re.compile(r"({.+})")
        self.message_queue = queue.Queue()
        self.session = requests.Session()
        Clock.schedule_interval(self.check_queue, 0.1)
        self.dialog = None

        # Create Downloads directory if it doesn't exist
        if not os.path.exists(self.download_dir):
            os.makedirs(self.download_dir)

    def open_link(self, url):
        """Open social media links in default browser"""
        webbrowser.open(url)

    def check_updates(self):
        """Check for updates on GitHub"""
        try:
            # Replace with your actual GitHub repository API URL
            response = requests.get("https://api.github.com/repos/yourusername/yourrepo/releases/latest")
            if response.status_code == 200:
                latest_version = response.json()["tag_name"]
                current_version = "v1.0.0"  # Replace with your current version
                
                if latest_version > current_version:
                    self.show_update_dialog(latest_version)
                else:
                    self.show_update_dialog(None)
        except Exception as e:
            self.update_status(f"Error checking updates: {str(e)}")

    def show_update_dialog(self, new_version):
        """Show update dialog"""
        if not self.dialog:
            if new_version:
                self.dialog = MDDialog(
                    title="Update Available!",
                    text=f"A new version {new_version} is available. Would you like to download it?",
                    buttons=[
                        MDFlatButton(
                            text="CANCEL",
                            on_release=lambda x: self.close_dialog()
                        ),
                        MDFlatButton(
                            text="UPDATE",
                            on_release=lambda x: self.download_update(new_version)
                        ),
                    ],
                )
            else:
                self.dialog = MDDialog(
                    title="No Updates",
                    text="You are running the latest version!",
                    buttons=[
                        MDFlatButton(
                            text="OK",
                            on_release=lambda x: self.close_dialog()
                        ),
                    ],
                )
            self.dialog.open()

    def close_dialog(self):
        """Close the dialog and clean up"""
        if self.dialog:
            self.dialog.dismiss()
            self.dialog = None

    def download_update(self, version):
        """Download the latest version"""
        self.close_dialog()
        update_url = f"https://github.com/yourusername/yourrepo/releases/download/{version}/JioSaavnDownloader.zip"
        webbrowser.open(update_url)

    def update_status(self, message):
        self.message_queue.put(("status", message))

    def update_progress(self, value):
        self.message_queue.put(("progress", value))

    def update_preview(self, image_url):
        self.message_queue.put(("preview", image_url))

    def check_queue(self, dt):
        try:
            while True:
                message_type, message = self.message_queue.get_nowait()
                if message_type == "status":
                    self.ids.status_text.text_widget.text += message + "\n"
                    self.ids.status_text.text_widget.cursor = (0, 0)  # Scroll to bottom
                elif message_type == "progress":
                    self.ids.progress_bar.value = message
                elif message_type == "preview":
                    self.current_album_art = message
        except queue.Empty:
            pass

    def start_download(self):
        url = self.ids.url_input.text.strip()
        if not url:
            self.update_status("Please enter a valid URL")
            return
        
        self.ids.status_text.text_widget.text = ""
        self.ids.progress_bar.value = 0
        self.current_album_art = ''
        Thread(target=self.download_content, args=(url,), daemon=True).start()

    def download_content(self, url):
        try:
            if "/album/" in url or "/song/" in url:
                kind, id_ = self.album_song_rx.search(url).groups()
                if kind == 'song':
                    self.process_track(id_)
                elif kind == 'album':
                    self.process_album(id_)
            elif '/playlist/' in url:
                playlist_id = self.playlist_rx.search(url).group(1)
                self.process_playlist(playlist_id)
            else:
                self.update_status("Invalid URL format")
        except Exception as e:
            self.update_status(f"Error: {str(e)}")

    def process_album(self, album_id):
        try:
            album_json = self.session.get(self.album_api.format(album_id)).text
            album_json = json.loads(self.json_rx.search(album_json).group(1))
            
            album_name = sanitize(unescape(album_json['title']))
            album_artist = album_json['primary_artists']
            total_tracks = len(album_json['songs'])
            
            self.update_status(f"\nAlbum: {album_name}")
            self.update_status(f"Artist: {album_artist}")
            self.update_status(f"Tracks: {total_tracks}")
            
            for idx, song in enumerate(album_json['songs'], 1):
                song_id = self.album_song_rx.search(song['perma_url']).group(2)
                self.process_track(song_id, album_artist, idx, total_tracks)
                self.update_progress((idx / total_tracks) * 100)
        except Exception as e:
            self.update_status(f"Error processing album: {str(e)}")

    def process_track(self, song_id, album_artist=None, song_pos=1, total_tracks=1):
        try:
            metadata = self.session.get(self.song_api.format(song_id)).text
            metadata = json.loads(self.json_rx.search(metadata).group(1))
            song_json = metadata[f'{list(metadata.keys())[0]}']
            
            self.update_preview(song_json["image"].replace("150", "500"))
            self.update_status(f"\nDownloading: {song_json['song']}")
            
            # Get the highest quality URL available
            download_url = None
            if 'media_url' in song_json:
                download_url = song_json['media_url']
            elif 'media_preview_url' in song_json:
                download_url = song_json['media_preview_url'].replace('preview', 'aac')
                
            if not download_url:
                self.update_status("Error: Could not find download URL")
                return
                
            filename = f"{sanitize(song_json['song'])}.m4a"
            filepath = os.path.join(self.download_dir, filename)
            
            # Download with proper headers
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': '*/*',
                'Accept-Encoding': 'gzip, deflate, br',
                'Range': 'bytes=0-',
            }
            
            response = self.session.get(download_url, stream=True, headers=headers)
            total_size = int(response.headers.get('content-length', 0))
            
            with open(filepath, 'wb') as f:
                if total_size == 0:
                    f.write(response.content)
                else:
                    dl = 0
                    for data in response.iter_content(chunk_size=4096):
                        dl += len(data)
                        f.write(data)
                        done = int(100 * dl / total_size)
                        self.update_progress(done)
            
            self.update_status("Download complete. Adding metadata...")
            try:
                self.add_metadata(filepath, song_json, album_artist, song_pos, total_tracks)
                self.update_status("Metadata added successfully.")
            except Exception as e:
                self.update_status(f"Warning: Could not add metadata: {str(e)}")
                self.update_status("File downloaded successfully but without metadata.")
                
        except Exception as e:
            self.update_status(f"Error downloading: {str(e)}")

    def process_playlist(self, playlist_id):
        try:
            playlist_json = self.session.get(self.playlist_api.format(playlist_id)).text
            playlist_json = json.loads(self.json_rx.search(playlist_json).group(1))
            
            playlist_name = playlist_json['name']
            total_tracks = len(playlist_json['songs'])
            
            self.update_status(f"\nPlaylist: {playlist_name}")
            self.update_status(f"Tracks: {total_tracks}")
            
            for idx, song in enumerate(playlist_json['songs'], 1):
                song_id = self.album_song_rx.search(song['perma_url']).group(2)
                self.process_track(song_id, song_pos=idx, total_tracks=total_tracks)
                self.update_progress((idx / total_tracks) * 100)
        except Exception as e:
            self.update_status(f"Error processing playlist: {str(e)}")

    def add_metadata(self, filepath, song_json, album_artist=None, song_pos=1, total_tracks=1):
        try:
            audio = MP4(filepath)
            audio['\xa9nam'] = song_json['song']
            audio['\xa9ART'] = song_json['primary_artists'] if not album_artist else album_artist
            audio['\xa9alb'] = song_json['album']
            audio['aART'] = song_json['singers']
            audio['\xa9day'] = song_json['year']
            audio['trkn'] = [(song_pos, total_tracks)]
            audio['cprt'] = song_json['label']
            if 'music' in song_json:
                audio['\xa9wrt'] = song_json['music']
            
            # Adding album art
            try:
                img_data = self.session.get(song_json['image'].replace("150", "500")).content
                audio['covr'] = [MP4Cover(img_data)]
            except Exception as e:
                self.update_status(f"Warning: Could not add album art: {str(e)}")
            
            audio.save()
        except Exception as e:
            raise Exception(f"Error adding metadata: {str(e)}")

    def browse_directory(self):
        from plyer import filechooser
        try:
            directory = filechooser.choose_dir()[0]
            if directory:
                self.download_dir = directory
                self.ids.dir_input.text = directory
                # Create directory if it doesn't exist
                if not os.path.exists(directory):
                    os.makedirs(directory)
        except Exception as e:
            self.update_status(f"Error selecting directory: {str(e)}")
            self.update_status("Using default download directory.")

class JioSaavnApp(MDApp):
    def build(self):
        self.theme_cls.primary_palette = "Purple"
        Builder.load_string(KV)
        return DownloaderGUI()

    def on_start(self):
        """Called when the application starts."""
        if not os.path.exists(os.path.join(os.getcwd(), "Downloads")):
            os.makedirs(os.path.join(os.getcwd(), "Downloads"))

if __name__ == '__main__':
    JioSaavnApp().run()
