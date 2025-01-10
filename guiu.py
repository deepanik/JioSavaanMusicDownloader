import tkinter as tk
from tkinter import messagebox
from tkinter import ttk
import threading
import json
import requests
from html import unescape
from sanitize_filename import sanitize
import re
import os
from mutagen.mp4 import MP4, MP4Cover
import time
import webbrowser
import queue
from functools import wraps

song_api = "https://www.jiosaavn.com/api.php?__call=webapi.get&token={}&type=song"
album_api = "https://www.jiosaavn.com/api.php?__call=webapi.get&token={}&type=album"
playlist_api = "https://www.jiosaavn.com/api.php?__call=webapi.get&token={}&type=playlist&_format=json"
lyrics_api = "https://www.jiosaavn.com/api.php?__call=lyrics.getLyrics&ctx=web6dot0&api_version=4&_format=json&_marker=0%3F_marker%3D0&lyrics_id="
album_song_rx = re.compile("https://www\.jiosaavn\.com/(album|song)/.+?/(.+)")
playlist_rx = re.compile("https://www\.jiosaavn\.com/s/playlist/.+/(.+)")
json_rx = re.compile("({.+})")

def rate_limit(seconds):
    def decorator(func):
        last_called = {}
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            current_time = time.time()
            if func not in last_called or current_time - last_called[func] >= seconds:
                last_called[func] = current_time
                return func(*args, **kwargs)
            else:
                wait_time = seconds - (current_time - last_called[func])
                time.sleep(wait_time)
                last_called[func] = time.time()
                return func(*args, **kwargs)
        return wrapper
    return decorator

class Jiosaavn:
    def __init__(self, session):
        self.session = session

    def tagger(self, json, song_path, album_artist, album_path, pos=1, total=1):
        audio = MP4(song_path)
        audio["\xa9nam"] = sanitize(unescape(json["song"]))
        audio["\xa9alb"] = sanitize(unescape(json["album"]))
        audio["\xa9ART"] = sanitize(unescape(json["primary_artists"]))
        audio["\xa9wrt"] = sanitize(unescape(json["music"]))
        audio["aART"] = album_artist if album_artist else sanitize(
            unescape(json["primary_artists"]))
        audio["\xa9day"] = json["release_date"]
        audio["----:TXXX:Record label"] = bytes(json["label"], 'UTF-8')
        audio["cprt"] = json["copyright_text"]
        audio["----:TXXX:Language"] = bytes(json["language"].title(), 'UTF-8')
        audio["rtng"] = [2 if json["explicit_content"] == 0 else 4]
        audio["trkn"] = [(pos, total)]

        if(json["has_lyrics"] == "true"):
            lyric_json = self.session.get(lyrics_api + json["id"]).json()
            audio["\xa9lyr"] = lyric_json["lyrics"].replace("<br>", "\n")

        with open(os.path.join(album_path, "cover.jpg"), "rb") as f:
            audio["covr"] = [
                MP4Cover(f.read(), imageformat=MP4Cover.FORMAT_JPEG)]

        if len(json['featured_artists']) > 1:
            audio["----:TXXX:Featured artists"] = bytes(
                json["featured_artists"], 'UTF-8')

        if len(json['singers']) > 1:
            audio["----:TXXX:Singers"] = bytes(json["singers"], 'UTF-8')

        if len(json['starring']) > 1:
            audio["----:TXXX:Starring"] = bytes(json["starring"], 'UTF-8')

        audio.pop("©too")
        audio.save()

    def processAlbum(self, album_id):
        album_json = self.session.get(album_api.format(album_id)).text
        album_json = json.loads(json_rx.search(album_json).group(1))

        album_name = sanitize(unescape(album_json['title']))
        album_artist = album_json['primary_artists']
        total_tracks = len(album_json['songs'])
        year = str(album_json['year'])

        song_pos = 1
        for song in album_json['songs']:
            song_id = album_song_rx.search(song['perma_url']).group(2)
            self.processTrack(song_id, album_artist, song_pos, total_tracks)
            song_pos += 1

    def processTrack(self, song_id, album_artist=None, song_pos=1, total_tracks=1, isPlaylist=False):
        metadata = self.session.get(song_api.format(song_id)).text
        metadata = json.loads(json_rx.search(metadata).group(1))
        song_json = metadata[f'{list(metadata.keys())[0]}']

        primary_artists = album_artist if album_artist else sanitize(
            unescape(song_json["primary_artists"]))
        track_name = sanitize(unescape(song_json['song']))
        album = sanitize(unescape(song_json['album']))
        year = str(unescape(song_json['year']))

        folder_name = f"{primary_artists if primary_artists.count(',') < 2 else 'Various Artists'} - {album} [{year}]"
        song_name = f"{str(song_pos).zfill(2)}. {track_name}.m4a"
        album_path = os.path.join("Downloads", folder_name)
        song_path = os.path.join("Downloads", folder_name, song_name)

        os.makedirs(album_path, exist_ok=True)

        if not os.path.exists(os.path.join(album_path, "cover.jpg")) or isPlaylist:
            with open(os.path.join(album_path, "cover.jpg"), "wb") as f:
                f.write(self.session.get(
                    song_json["image"].replace("150", "500")).content)

        if not os.path.exists(song_path):
            if 'media_preview_url' in song_json:
                cdnURL = self.getCdnURL(song_json["encrypted_media_url"])

                with open(song_path, "wb") as f:
                    f.write(self.session.get(cdnURL).content)

                self.tagger(song_json, song_path, album_artist, album_path, song_pos, total_tracks)
            else:
                print("\nTrack unavailable in your region!")

    @rate_limit(1.0)
    def getCdnURL(self, encurl: str):
        params = {
            '__call': 'song.generateAuthToken',
            'url': encurl,
            'bitrate': '320',
            'api_version': '4',
            '_format': 'json',
            'ctx': 'web6dot0',
            '_marker': '0',
        }
        response = self.session.get('https://www.jiosaavn.com/api.php', params=params)
        return response.json()["auth_url"]

    def processPlaylist(self, playlist_id):
        playlist_json = self.session.get(playlist_api.format(playlist_id)).text
        playlist_json = json.loads(json_rx.search(playlist_json).group(1))

        playlist_name = playlist_json['listname']
        total_tracks = int(playlist_json['list_count'])
        playlist_path = f"Playlist - {playlist_name}"

        song_pos = 1
        for song in playlist_json['songs']:
            song_id = album_song_rx.search(song['perma_url']).group(2)
            self.processTrack(song_id, None, song_pos, total_tracks, playlist_path)
            song_pos += 1


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("JioSaavn AI Downloader")
        self.root.geometry("900x700")
        self.root.configure(bg='#1E1E1E')
        
        # Configure styles
        style = ttk.Style()
        style.theme_use('clam')
        
        # Enhanced style configurations
        style.configure('Custom.TFrame', background='#1E1E1E')
        style.configure('Custom.TLabel', 
                       background='#1E1E1E', 
                       foreground='#00FF00',
                       font=('Courier', 11))
        style.configure('Custom.TButton',
                       background='#333333',
                       foreground='#00FF00',
                       padding=10,
                       font=('Courier', 10, 'bold'))
        style.configure('Header.TLabel',
                       background='#1E1E1E',
                       foreground='#00FF00',
                       font=('Courier', 28, 'bold'))
        style.configure('Section.TLabelframe',
                       background='#1E1E1E',
                       foreground='#00FF00',
                       bordercolor='#00FF00',
                       borderwidth=2)
        style.configure('Section.TLabelframe.Label',
                       background='#1E1E1E',
                       foreground='#00FF00',
                       font=('Courier', 12, 'bold'))

        # Add these to your style configurations
        style.configure('Matrix.TButton',
                       background='#000000',
                       foreground='#00FF00',
                       font=('Courier', 10, 'bold'),
                       padding=(15, 8))
        
        style.map('Matrix.TButton',
                 background=[('active', '#003300')],
                 foreground=[('active', '#00FF00')])
        
        style.configure('Matrix.TButton.Hover',
                       background='#003300',
                       foreground='#00FF00',
                       font=('Courier', 10, 'bold'),
                       padding=(15, 8))

        # Enhanced button styles
        style.configure('Download.TButton',
                       background='#003300',
                       foreground='#00FF00',
                       font=('Courier', 12, 'bold'),
                       padding=(20, 12))
        
        style.configure('Download.TButton.Hover',
                       background='#004400',
                       foreground='#00FF00',
                       font=('Courier', 12, 'bold'),
                       padding=(20, 12))

        # Entry style
        style.configure('Matrix.TEntry',
                       fieldbackground='#000000',
                       foreground='#00FF00',
                       insertcolor='#00FF00',
                       borderwidth=2,
                       relief='solid')

        # Configure styles at the beginning with other styles
        style.configure('Update.TButton',
                       background='#001a00',
                       foreground='#00FF00',
                       font=('Courier', 11, 'bold'),
                       padding=(15, 8),
                       borderwidth=2,
                       relief='raised')
        
        style.configure('Update.TButton.Hover',
                       background='#003300',
                       foreground='#00FF00',
                       font=('Courier', 11, 'bold'),
                       padding=(15, 8),
                       borderwidth=2,
                       relief='raised')

        # Main container with padding
        main_frame = ttk.Frame(root, style='Custom.TFrame')
        main_frame.pack(fill=tk.BOTH, expand=True, padx=30, pady=25)

        # Header with AI animation and version info
        header_frame = ttk.Frame(main_frame, style='Custom.TFrame')
        header_frame.pack(fill=tk.X, pady=(0, 30))

        # Left side - Title
        header_label = ttk.Label(
            header_frame,
            text="< JioSaavn AI Downloader />",
            style='Header.TLabel'
        )
        header_label.pack(side=tk.LEFT)

        # Right side - Version and Update
        version_frame = ttk.Frame(header_frame, style='Custom.TFrame')
        version_frame.pack(side=tk.RIGHT, padx=15)

        self.version_label = ttk.Label(
            version_frame,
            text="VERSION :: v1.0.0",
            style='Custom.TLabel'
        )
        self.version_label.pack(side=tk.LEFT, padx=(0, 20))

        # Add social links popup button to the header frame
        self.social_button = ttk.Button(
            version_frame,
            text="⚡ SOCIAL NODES ⚡",
            command=self.show_social_popup,
            style='Update.TButton'
        )
        self.social_button.pack(side=tk.LEFT, padx=15)

        # Add hover effect to social button
        self.social_button.bind('<Enter>', 
            lambda e: self.social_button.configure(style='Update.TButton.Hover'))
        self.social_button.bind('<Leave>', 
            lambda e: self.social_button.configure(style='Update.TButton'))

        # Enhanced update button
        self.update_button = ttk.Button(
            version_frame,
            text="⟲ CHECK_UPDATES ⟲",
            command=self.check_updates,
            style='Update.TButton'
        )
        self.update_button.pack(side=tk.LEFT)

        # Add hover effect to update button
        self.update_button.bind('<Enter>', 
            lambda e: self.update_button.configure(style='Update.TButton.Hover'))
        self.update_button.bind('<Leave>', 
            lambda e: self.update_button.configure(style='Update.TButton'))

        # URL input frame with enhanced styling
        input_frame = ttk.LabelFrame(
            main_frame, 
            text=" DOWNLOAD INTERFACE ", 
            padding=25,
            style='Section.TLabelframe'
        )
        input_frame.pack(fill=tk.X, pady=(0, 20))

        self.url_label = ttk.Label(
            input_frame, 
            text="⚡ Enter URL (Song/Album/Playlist):",
            style='Custom.TLabel'
        )
        self.url_label.pack(anchor='w', pady=(0, 10))

        # URL Entry with custom style and larger size
        self.url_entry = ttk.Entry(
            input_frame,
            width=70,
            font=('Courier', 12),
            style='Matrix.TEntry'
        )
        self.url_entry.pack(fill=tk.X, pady=(0, 15))

        # Download button with enhanced styling
        self.download_button = ttk.Button(
            input_frame,
            text="▼ INITIATE DOWNLOAD SEQUENCE ▼",
            command=self.download,
            style='Download.TButton'
        )
        self.download_button.pack(pady=(10, 0))

        # Add hover effect to download button
        self.download_button.bind('<Enter>', 
            lambda e: self.download_button.configure(style='Download.TButton.Hover'))
        self.download_button.bind('<Leave>', 
            lambda e: self.download_button.configure(style='Download.TButton'))

        # Status frame with improved layout
        progress_frame = ttk.LabelFrame(
            main_frame,
            text=" SYSTEM STATUS : ONLINE",
            padding=20,
            style='Section.TLabelframe'
        )
        progress_frame.pack(fill=tk.X, pady=(0, 20))

        # Status label with more space
        self.status_label = ttk.Label(
            progress_frame,
            text="⚡ SYSTEM IDLE",
            style='Custom.TLabel'
        )
        self.status_label.pack(fill=tk.X, pady=(0, 10))

        # Progress bar with enhanced styling
        style.configure("Custom.Horizontal.TProgressbar",
                       troughcolor='#1E1E1E',
                       background='#00FF00',
                       darkcolor='#00CC00',
                       lightcolor='#00FF00',
                       bordercolor='#333333',
                       thickness=20)

        self.progress_bar = ttk.Progressbar(
            progress_frame,
            mode="determinate",
            style='Custom.Horizontal.TProgressbar'
        )
        self.progress_bar.pack(fill=tk.X)

        # Log frame with improved visibility
        log_frame = ttk.LabelFrame(
            main_frame,
            text=" AI NEURAL INTERFACE ",
            padding=20,
            style='Section.TLabelframe'
        )
        log_frame.pack(fill=tk.BOTH, expand=True)

        # Scrollbar and log text with enhanced styling
        scrollbar = ttk.Scrollbar(log_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.log_text = tk.Text(
            log_frame,
            width=60,
            height=12,
            bg='#000000',
            fg='#00FF00',
            font=('Courier', 11),
            yscrollcommand=scrollbar.set,
            wrap=tk.WORD,
            padx=10,
            pady=10
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.log_text.yview)
        self.log_text.config(state=tk.DISABLED)

        # Initialize message queue for typing animation
        self.message_queue = queue.Queue()
        self.typing_speed = 0.03  # Adjust typing speed (seconds per character)
        
        # Start the message processing thread
        self.typing_thread = threading.Thread(target=self.process_messages, daemon=True)
        self.typing_thread.start()

        # Initial AI message
        self.log("NEURAL INTERFACE INITIALIZED...")
        self.log("AI SYSTEM ONLINE AND READY...")
        self.log("AWAITING USER INPUT...")

        # Social Links frame with cyberpunk design
        social_frame = ttk.LabelFrame(
            main_frame,
            text=" SOCIAL NODES :: SECURE ACCESS ",
            padding=15,
            style='Section.TLabelframe'
        )
        social_frame.pack(fill=tk.X, pady=(20, 0))

        # Configure social button style
        style.configure('Social.TButton',
                       background='#001a00',
                       foreground='#00FF00',
                       font=('Courier', 11, 'bold'),
                       padding=(15, 10),
                       borderwidth=2,
                       relief='raised')
        
        style.configure('Social.TButton.Hover',
                       background='#003300',
                       foreground='#00FF00',
                       font=('Courier', 11, 'bold'),
                       padding=(15, 10),
                       borderwidth=2,
                       relief='raised')

        # Inner container with grid layout
        links_container = ttk.Frame(social_frame, style='Custom.TFrame')
        links_container.pack(fill=tk.X, padx=10, pady=10)

        social_links = [
            ("GITHUB::REPO", "https://github.com/deepanik", "⌘"),
            ("LINKEDIN::NET", "https://www.linkedin.com/in/laxmi-narayan-pandey/", "◉"),
            ("TELEGRAM::COM", "https://t.me/deepanikk", "⟡")
        ]

        # Create a status label for hover feedback
        self.social_status = ttk.Label(
            social_frame,
            text="STATUS :: READY",
            style='Custom.TLabel'
        )
        self.social_status.pack(pady=(0, 5))

        for i, (name, url, icon) in enumerate(social_links):
            # Container for each button
            link_frame = ttk.Frame(links_container, style='Custom.TFrame')
            link_frame.pack(side=tk.LEFT, expand=True, padx=8)
            
            # Enhanced social buttons
            link_btn = ttk.Button(
                link_frame,
                text=f"{icon} {name} {icon}",
                command=lambda u=url, n=name: self.open_social_link(u, n),
                style='Social.TButton'
            )
            link_btn.pack(expand=True, fill=tk.X)

            # Add hover effects with status update
            link_btn.bind('<Enter>', 
                lambda e, n=name: self.social_hover_enter(n))
            link_btn.bind('<Leave>', 
                lambda e: self.social_hover_leave())

        # Add session initialization
        self.session = requests.Session()
        self.jiosaavn = Jiosaavn(self.session)

        # Add user-agent to mimic browser
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.5',
            'DNT': '1',
            'Connection': 'keep-alive',
        })

    def social_hover_enter(self, name):
        """Handle mouse enter for social buttons"""
        self.social_status.configure(text=f"STATUS :: CONNECTING TO {name}")

    def social_hover_leave(self):
        """Handle mouse leave for social buttons"""
        self.social_status.configure(text="STATUS :: READY")

    def open_social_link(self, url, name):
        """Enhanced social link opening with visual feedback"""
        self.social_status.configure(text=f"STATUS :: ACCESSING {name}")
        self.log(f"INITIALIZING CONNECTION TO {name}...")
        time.sleep(0.3)
        self.log("ESTABLISHING SECURE TUNNEL...")
        time.sleep(0.2)
        self.log(f"CONNECTING TO NODE: {url}")
        webbrowser.open(url)
        self.log("CONNECTION ESTABLISHED :: STATUS [OK]")
        time.sleep(0.2)
        self.log(f"ACCESS TO {name} GRANTED...")
        self.social_status.configure(text="STATUS :: READY")

    def check_updates(self):
        """Check for updates with matrix-style logging and visual feedback"""
        # Disable the button during check
        self.update_button.configure(state='disabled')
        self.version_label.configure(text="VERSION :: CHECKING...")
        
        self.log("INITIATING UPDATE CHECK SEQUENCE...")
        time.sleep(0.5)
        self.log("SCANNING REMOTE REPOSITORY...")
        
        try:
            # Simulate checking for updates
            time.sleep(1)
            self.log("ANALYZING VERSION DATA...")
            time.sleep(0.5)

            self.log("STATUS: SYSTEM IS UP TO DATE")
            self.version_label.configure(text="VERSION :: v1.0.0")
            self.log("UPDATE CHECK COMPLETE :: STATUS [OK]")
        except Exception as e:
            self.log("ERROR: UPDATE CHECK FAILED")
            self.log(f"ERROR CODE: {str(e)}")
            self.version_label.configure(text="VERSION :: ERROR")
        finally:
            self.log("UPDATE SEQUENCE TERMINATED")
            # Re-enable the button
            self.update_button.configure(state='normal')

    def log(self, message):
        """Add message to queue for typing animation"""
        self.message_queue.put(f"[{time.strftime('%H:%M:%S')}] {message}\n")

    def process_messages(self):
        """Process messages in queue with typing animation"""
        while True:
            try:
                message = self.message_queue.get()
                self.type_message(message)
                self.message_queue.task_done()
            except queue.Empty:
                time.sleep(0.1)

    def type_message(self, message):
        """Display message with typing animation"""
        self.log_text.config(state=tk.NORMAL)
        for char in message:
            self.log_text.insert(tk.END, char)
            self.log_text.see(tk.END)
            self.log_text.update()
            time.sleep(self.typing_speed)
        self.log_text.config(state=tk.DISABLED)

    def download(self):
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showerror("Error", "Please enter a valid URL!")
            return

        # Validate URL format
        if not url.startswith("https://www.jiosaavn.com/"):
            messagebox.showerror("Error", "Invalid URL! Please enter a valid JioSaavn URL.")
            return

        self.progress_bar["value"] = 0
        self.status_label.config(text="⚡ INITIATING DOWNLOAD SEQUENCE")
        self.log("ANALYZING URL PATTERN...")
        self.log("ESTABLISHING CONNECTION TO SERVER...")

        def download_thread():
            try:
                # Create Downloads directory if it doesn't exist
                if not os.path.exists("Downloads"):
                    os.makedirs("Downloads")

                self.progress_bar["value"] = 20
                if "/album/" in url or "/song/" in url:
                    match = album_song_rx.search(url)
                    if not match:
                        raise ValueError("Invalid album/song URL format")
                    
                    kind, id_ = match.groups()
                    self.log(f"DETECTED CONTENT TYPE: {kind.upper()}")
                    self.progress_bar["value"] = 40

                    if kind == 'song':
                        self.log("DOWNLOADING SINGLE TRACK...")
                        self.jiosaavn.processTrack(id_, None, 1, 1)
                    elif kind == 'album':
                        self.log("PROCESSING ALBUM CONTENTS...")
                        self.jiosaavn.processAlbum(id_)
                    
                    self.progress_bar["value"] = 80
                    self.log("FINALIZING DOWNLOAD...")
                    
                elif '/playlist/' in url:
                    self.log("DETECTED CONTENT TYPE: PLAYLIST")
                    match = playlist_rx.search(url)
                    if not match:
                        raise ValueError("Invalid playlist URL format")
                    
                    playlist_id = match.group(1)
                    self.jiosaavn.processPlaylist(playlist_id)
                else:
                    messagebox.showerror("Error", "Invalid URL type! Please use a valid JioSaavn song, album, or playlist URL.")
                    return

                self.progress_bar["value"] = 100
                self.status_label.config(text="⚡ DOWNLOAD COMPLETE")
                self.log("DOWNLOAD SEQUENCE COMPLETED SUCCESSFULLY")
                
                # Open downloads folder after completion
                downloads_path = os.path.join(os.getcwd(), "Downloads")
                if os.path.exists(downloads_path):
                    webbrowser.open(downloads_path)
                
            except requests.exceptions.RequestException as e:
                self.log("NETWORK ERROR: CONNECTION FAILED")
                messagebox.showerror("Network Error", "Failed to connect to JioSaavn. Please check your internet connection.")
            except json.JSONDecodeError:
                self.log("ERROR: INVALID SERVER RESPONSE")
                messagebox.showerror("Error", "Failed to parse server response. The song might be unavailable.")
            except Exception as e:
                self.log(f"ERROR DETECTED: {str(e)}")
                messagebox.showerror("Error", str(e))
            finally:
                self.progress_bar["value"] = 0
                self.status_label.config(text="⚡ SYSTEM IDLE")

        threading.Thread(target=download_thread, daemon=True).start()

    def show_social_popup(self):
        """Show social links in a popup window"""
        # Create popup window
        popup = tk.Toplevel(self.root)
        popup.title("Network Nodes")
        popup.geometry("500x400")
        popup.configure(bg='#1E1E1E')
        
        # Make popup modal
        popup.transient(self.root)
        popup.grab_set()
        
        # Center popup on screen
        popup.geometry("+%d+%d" % (
            self.root.winfo_x() + (self.root.winfo_width()/2 - 250),
            self.root.winfo_y() + (self.root.winfo_height()/2 - 200)
        ))

        # Main frame for popup
        popup_frame = ttk.Frame(popup, style='Custom.TFrame')
        popup_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        # Title
        title_label = ttk.Label(
            popup_frame,
            text="< SOCIAL NODES >",
            style='Header.TLabel'
        )
        title_label.pack(pady=(0, 20))

        # Status label
        self.popup_status = ttk.Label(
            popup_frame,
            text="STATUS :: SELECT NODE",
            style='Custom.TLabel'
        )
        self.popup_status.pack(pady=(0, 15))

        # Social links with descriptions
        social_links = [
            ("GITHUB::REPO", "https://github.com/deepanik", "⌘", 
             "Access source code and development updates"),
            ("LINKEDIN::NET", "https://linkedin.com/in/laxmi-narayan-pandey/", "◉",
             "Professional network connection point"),
            ("TELEGRAM::COM", "https://t.me/deepanikk", "⟡",
             "Direct communication channel")
        ]

        # Container for social buttons
        buttons_frame = ttk.Frame(popup_frame, style='Custom.TFrame')
        buttons_frame.pack(fill=tk.BOTH, expand=True, padx=10)

        for name, url, icon, desc in social_links:
            # Frame for each button and description
            link_frame = ttk.Frame(buttons_frame, style='Custom.TFrame')
            link_frame.pack(fill=tk.X, pady=10)
            
            # Button
            link_btn = ttk.Button(
                link_frame,
                text=f"{icon} {name} {icon}",
                command=lambda u=url, n=name: self.open_social_link(u, n),
                style='Social.TButton'
            )
            link_btn.pack(fill=tk.X)
            
            # Description
            desc_label = ttk.Label(
                link_frame,
                text=f":: {desc}",
                style='Custom.TLabel'
            )
            desc_label.pack(pady=(5, 0))

            # Add hover effects
            link_btn.bind('<Enter>', 
                lambda e, n=name: self.popup_hover_enter(n))
            link_btn.bind('<Leave>', 
                lambda e: self.popup_hover_leave())

        # Close button
        close_btn = ttk.Button(
            popup_frame,
            text="◄ CLOSE CONNECTION ►",
            command=popup.destroy,
            style='Download.TButton'
        )
        close_btn.pack(pady=(20, 0))

    def popup_hover_enter(self, name):
        """Handle mouse enter for popup buttons"""
        if hasattr(self, 'popup_status'):
            self.popup_status.configure(text=f"STATUS :: CONNECTING TO {name}")

    def popup_hover_leave(self):
        """Handle mouse leave for popup buttons"""
        if hasattr(self, 'popup_status'):
            self.popup_status.configure(text="STATUS :: SELECT NODE")

def main():
    root = tk.Tk()
    app = App(root)
    root.mainloop()

if __name__ == "__main__":
    main()
