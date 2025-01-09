import os
import json
import requests
from html import unescape
from sanitize_filename import sanitize
import re
import logging
from flask import Flask, request, jsonify, render_template
from mutagen.mp4 import MP4, MP4Cover
from werkzeug.exceptions import HTTPException

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# APIs
song_api = "https://www.jiosaavn.com/api.php?__call=webapi.get&token={}&type=song"
album_api = "https://www.jiosaavn.com/api.php?__call=webapi.get&token={}&type=album"
playlist_api = "https://www.jiosaavn.com/api.php?__call=webapi.get&token={}&type=playlist&_format=json"
lyrics_api = "https://www.jiosaavn.com/api.php?__call=lyrics.getLyrics&ctx=web6dot0&api_version=4&_format=json&_marker=0%3F_marker%3D0&lyrics_id="
album_song_rx = re.compile("https://www\.jiosaavn\.com/(album|song)/.+?/(.+)")
playlist_rx = re.compile("https://www\.jiosaavn\.com/s/playlist/.+/(.+)")
json_rx = re.compile("({.+})")

app = Flask(__name__)

class Jiosaavn:
    def __init__(self):
        self.session = requests.Session()

    def tagger(self, json, song_path, album_artist, album_path, pos=1, total=1):
        try:
            audio = MP4(song_path)
            audio["\xa9nam"] = sanitize(unescape(json["song"]))
            audio["\xa9alb"] = sanitize(unescape(json["album"]))
            audio["\xa9ART"] = sanitize(unescape(json["primary_artists"]))
            audio["\xa9wrt"] = sanitize(unescape(json["music"]))
            audio["aART"] = album_artist if album_artist else sanitize(unescape(json["primary_artists"]))
            audio["\xa9day"] = json["release_date"]
            audio["----:TXXX:Record label"] = bytes(json["label"], 'UTF-8')
            audio["cprt"] = json["copyright_text"]
            audio["----:TXXX:Language"] = bytes(json["language"].title(), 'UTF-8')
            audio["rtng"] = [2 if json["explicit_content"] == 0 else 4]
            audio["trkn"] = [(pos, total)]

            if json["has_lyrics"] == "true":
                lyric_json = self.session.get(lyrics_api + json["id"]).json()
                audio["\xa9lyr"] = lyric_json["lyrics"].replace("<br>", "\n")

            with open(os.path.join(album_path, "cover.jpg"), "rb") as f:
                audio["covr"] = [MP4Cover(f.read(), imageformat=MP4Cover.FORMAT_JPEG)]

            if len(json['featured_artists']) > 1:
                audio["----:TXXX:Featured artists"] = bytes(json["featured_artists"], 'UTF-8')

            if len(json['singers']) > 1:
                audio["----:TXXX:Singers"] = bytes(json["singers"], 'UTF-8')

            if len(json['starring']) > 1:
                audio["----:TXXX:Starring"] = bytes(json["starring"], 'UTF-8')

            audio.pop("©too")
            audio.save()
        except Exception as e:
            logger.error(f"Error tagging metadata: {e}")
            raise HTTPException(f"Error tagging metadata: {e}")

    def processAlbum(self, album_id):
        try:
            album_json = self.session.get(album_api.format(album_id)).text
            album_json = json.loads(json_rx.search(album_json).group(1))

            album_name = sanitize(unescape(album_json['title']))
            album_artist = album_json['primary_artists']
            total_tracks = len(album_json['songs'])
            year = str(album_json['year'])

            album_info = f"\nAlbum info:\nAlbum name       : {album_name}\nAlbum artists    : {album_artist}\nYear             : {year}\nNumber of tracks : {total_tracks}\n"
            logger.info(album_info)

            song_pos = 1
            for song in album_json['songs']:
                song_id = album_song_rx.search(song['perma_url']).group(2)
                self.processTrack(song_id, album_artist, song_pos, total_tracks)
                song_pos += 1
        except Exception as e:
            logger.error(f"Error processing album: {e}")
            raise HTTPException(f"Error processing album: {e}")

    def processTrack(self, song_id, album_artist=None, song_pos=1, total_tracks=1, isPlaylist=False):
        try:
            metadata = self.session.get(song_api.format(song_id)).text
            metadata = json.loads(json_rx.search(metadata).group(1))
            song_json = metadata[f'{list(metadata.keys())[0]}']

            primary_artists = album_artist if album_artist else sanitize(unescape(song_json["primary_artists"]))
            track_name = sanitize(unescape(song_json['song']))
            album = sanitize(unescape(song_json['album']))
            year = str(unescape(song_json['year']))

            folder_name = f"{primary_artists if primary_artists.count(',') < 2 else 'Various Artists'} - {album} [{year}]"
            song_name = f"{str(song_pos).zfill(2)}. {track_name}.m4a"

            album_path = os.path.join("Downloads", folder_name)
            song_path = os.path.join("Downloads", folder_name, song_name)

            try:
                os.makedirs(album_path)
            except Exception as e:
                logger.warning(f"Error creating directory: {e}")

            song_info = f"\nTrack info:\nSong name      : {song_json['song']}\nArtist(s) name : {song_json['primary_artists']}\nAlbum name     : {song_json['album']}\nYear           : {song_json['year']}\n"
            logger.info(song_info)

            if not os.path.exists(os.path.join(album_path, "cover.jpg")) or isPlaylist:
                logger.info("Downloading the cover...")
                with open(os.path.join(album_path, "cover.jpg"), "wb") as f:
                    f.write(self.session.get(song_json["image"].replace("150", "500")).content)

            if os.path.exists(song_path):
                logger.info(f"{song_name} already downloaded.")
            else:
                logger.info(f"Downloading: {song_name}...")

                if 'media_preview_url' in song_json:
                    cdnURL = self.getCdnURL(song_json["encrypted_media_url"])

                    with open(song_path, "wb") as f:
                        f.write(self.session.get(cdnURL).content)

                    logger.info("Tagging metadata...")
                    self.tagger(song_json, song_path, album_artist, album_path, song_pos, total_tracks)
                    logger.info("Done.")
                else:
                    logger.warning("\nTrack unavailable in your region!")
        except Exception as e:
            logger.error(f"Error processing track: {e}")
            raise HTTPException(f"Error processing track: {e}")

    def getCdnURL(self, encurl: str):
        try:
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
        except Exception as e:
            logger.error(f"Error getting CDN URL: {e}")
            raise HTTPException(f"Error getting CDN URL: {e}")

@app.route('/')
def home():
    # return render_template('index.html')
    return "Program Started!"

@app.route('/download', methods=['POST'])
def download():
    try:
        url = request.form['url']
        jiosaavn = Jiosaavn()

        if "/album/" in url or "/song/" in url:
            kind, id_ = album_song_rx.search(url).groups()

            if kind == 'song':
                jiosaavn.processTrack(id_, None, 1, 1)
            elif kind == 'album':
                jiosaavn.processAlbum(id_)
        elif '/playlist/' in url:
            playlist_id = playlist_rx.search(url).group(1)
            jiosaavn.processPlaylist(playlist_id)
        else:
            return jsonify({"error": "Invalid URL! Please provide a valid song, album, or playlist URL."}), 400

        return jsonify({"message": "Download started!"}), 200
    except HTTPException as e:
        logger.error(f"HTTP error: {e}")
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        logger.error(f"Unknown error: {e}")
        return jsonify({"error": "An unexpected error occurred."}), 500

if __name__ == "__main__":
    app.run(debug=True)
