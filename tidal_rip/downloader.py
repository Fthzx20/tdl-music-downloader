import os
import re
import aiohttp
import aiofiles
import asyncio
import subprocess
import time
import imageio_ffmpeg
from mutagen.flac import FLAC, Picture
from mutagen.mp4 import MP4, MP4Cover

def sanitize_filename(name):
    """Sanitizes strings to be safe for file paths across Windows/macOS/Linux."""
    return re.sub(r'[\/:*?"<>|]', '_', name).strip()

class DownloadManager:
    """Manages queueing, downloading, and tagging of Tidal tracks."""
    
    def __init__(self, api, config):
        self.api = api
        self.config = config
        self.is_paused = False
        self.is_cancelled = False

    async def download_track(self, track_id, progress_callback=None, parent_folder=None, task_state=None):
        """Downloads a track, parses manifest, concatenates segments, and writes tags.
        
        progress_callback: func(bytes_downloaded, total_bytes, status_text)
        parent_folder: str (optional) A custom folder name to save the track in (e.g., Playlist Name)
        task_state: dict (optional) Dictionary containing {"is_paused": bool, "is_cancelled": bool}
        """
        if progress_callback:
            await progress_callback(0, 1, "Fetching metadata...")

        # 1. Fetch Track & Album Metadata
        track = await self.api.get_track(track_id)
        album_id = track["album"]["id"]
        album = await self.api.get_album(album_id)
        
        # Track details
        title = track["title"]
        artist_name = track["artist"]["name"]
        album_title = album["title"]
        track_num = track.get("trackNumber", 1)
        total_tracks = album.get("numberOfTracks", 1)
        disc_num = track.get("volumeNumber", 1)
        release_date = album.get("releaseDate", "")
        genre = album.get("genre", "")
        
        # Format the output paths
        safe_artist = sanitize_filename(artist_name)
        safe_album = sanitize_filename(album_title)
        safe_title = sanitize_filename(title)
        
        if parent_folder:
            safe_parent = sanitize_filename(parent_folder)
            album_dir = os.path.join(self.config.download_directory, safe_parent)
        else:
            album_dir = os.path.join(self.config.download_directory, safe_artist, safe_album)
            
        os.makedirs(album_dir, exist_ok=True)
        
        # 2. Fetch Stream Info
        quality = self.config.quality_tier
        if progress_callback:
            await progress_callback(0, 1, "Fetching stream URL...")
            
        stream_info = await self.api.get_stream_info(track_id, quality)
        ext = stream_info["extension"]
        
        filename = f"{track_num:02d} - {safe_title}.{ext}"
        final_path = os.path.join(album_dir, filename)
        temp_path = final_path + ".tmp"
        
        # 3. Perform Download
        session = await self.api.get_session()
        try:
            if stream_info["type"] == "direct":
                # Direct file download
                url = stream_info["url"]
                async with session.get(url) as resp:
                    resp.raise_for_status()
                    total_size = int(resp.headers.get("Content-Length", 0))
                    downloaded = 0
                    last_time = time.time()
                    last_downloaded = 0
                    smoothed_speed = None
                    
                    async with aiofiles.open(temp_path, "wb") as f:
                        async for chunk in resp.content.iter_chunked(1024 * 64):
                            is_paused = self.is_paused or (task_state and task_state.get("is_paused", False))
                            is_cancelled = self.is_cancelled or (task_state and task_state.get("is_cancelled", False))
                            
                            while is_paused and not is_cancelled:
                                await asyncio.sleep(0.5)
                                is_paused = self.is_paused or (task_state and task_state.get("is_paused", False))
                                is_cancelled = self.is_cancelled or (task_state and task_state.get("is_cancelled", False))
                                
                            if is_cancelled:
                                raise Exception("Cancelled by user")
                                
                            await f.write(chunk)
                            downloaded += len(chunk)
                            
                            now = time.time()
                            if now - last_time >= 0.5:
                                current_speed = (downloaded - last_downloaded) / (now - last_time) # bytes/sec
                                if smoothed_speed is None:
                                    smoothed_speed = current_speed
                                else:
                                    smoothed_speed = 0.5 * smoothed_speed + 0.5 * current_speed
                                    
                                last_time = now
                                last_downloaded = downloaded
                                if progress_callback:
                                    await progress_callback(downloaded, total_size, f"Downloading: {downloaded / 1024 / 1024:>5.1f}MB / {total_size / 1024 / 1024:>5.1f}MB       ({smoothed_speed / 1024 / 1024:>4.1f} MB/s)")
                                
            elif stream_info["type"] == "dash":
                # Fragmented DASH download with binary concatenation
                init_url = stream_info["init_url"]
                segment_urls = stream_info["segment_urls"]
                
                # Estimate total size if possible
                total_segments = len(segment_urls)
                downloaded = 0
                last_time = time.time()
                last_downloaded = 0
                smoothed_speed = None
                
                async with aiofiles.open(temp_path, "wb") as f:
                    # Download initialization segment
                    if init_url:
                        if progress_callback:
                            await progress_callback(0, total_segments, "Downloading initialization segment...")
                        async with session.get(init_url) as resp:
                            resp.raise_for_status()
                            await f.write(await resp.read())
                    
                    # Download each media segment in order
                    for idx, seg_url in enumerate(segment_urls):
                        is_paused = self.is_paused or (task_state and task_state.get("is_paused", False))
                        is_cancelled = self.is_cancelled or (task_state and task_state.get("is_cancelled", False))
                        
                        while is_paused and not is_cancelled:
                            await asyncio.sleep(0.5)
                            is_paused = self.is_paused or (task_state and task_state.get("is_paused", False))
                            is_cancelled = self.is_cancelled or (task_state and task_state.get("is_cancelled", False))
                            
                        if is_cancelled:
                            raise Exception("Cancelled by user")
                            
                        if progress_callback:
                            await progress_callback(idx, total_segments, f"Downloading segment {idx + 1}/{total_segments}...")
                        async with session.get(seg_url) as resp:
                            resp.raise_for_status()
                            async for chunk in resp.content.iter_chunked(1024 * 64):
                                await f.write(chunk)
                                downloaded += len(chunk)
                                
                                now = time.time()
                                if now - last_time >= 0.5:
                                    current_speed = (downloaded - last_downloaded) / (now - last_time) # bytes/sec
                                    if smoothed_speed is None:
                                        smoothed_speed = current_speed
                                    else:
                                        smoothed_speed = 0.5 * smoothed_speed + 0.5 * current_speed
                                        
                                    last_time = now
                                    last_downloaded = downloaded
                                    if progress_callback:
                                        # Use idx as proxy for progress, but append speed
                                        await progress_callback(idx, total_segments, f"Downloading segment {idx + 1:02d}/{total_segments:02d}       ({smoothed_speed / 1024 / 1024:>4.1f} MB/s)")
                                
            # Convert/Extract if needed
            if stream_info["type"] == "dash" and ext == "flac":
                # DASH FLAC streams are encapsulated in MP4 containers. Extract the raw FLAC.
                if progress_callback:
                    await progress_callback(100, 100, "Extracting FLAC stream from MP4 container...")
                
                ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
                raw_flac_path = final_path + ".raw.tmp"
                try:
                    result = subprocess.run(
                        [ffmpeg_exe, "-y", "-i", temp_path, "-c:a", "copy", "-f", "flac", raw_flac_path],
                        check=True, capture_output=True, text=True
                    )
                    os.remove(temp_path)
                    temp_path = raw_flac_path
                except subprocess.CalledProcessError as e:
                    print(f"FFmpeg extraction failed with {e.returncode}: {e.stderr}")
                    raise Exception(f"Failed to extract FLAC stream. FFmpeg error: {e.stderr.strip().split(chr(10))[-1]}")

            # Rename temp file to final destination
            if os.path.exists(final_path):
                os.remove(final_path)
            os.rename(temp_path, final_path)
            
            # 4. Embedded Metadata Tagging
            if progress_callback:
                await progress_callback(100, 100, "Applying metadata tags...")
                
            cover_bytes = None
            cover_id = album.get("cover")
            if cover_id:
                # Retrieve album artwork
                cover_url = f"https://resources.tidal.com/images/{cover_id.replace('-', '/')}/1280x1280.jpg"
                try:
                    async with session.get(cover_url) as resp:
                        if resp.status == 200:
                            cover_bytes = await resp.read()
                except Exception as e:
                    print(f"Failed to fetch album cover: {e}")
                    
            # Apply tags using Mutagen
            self.apply_metadata(final_path, ext, {
                "title": title,
                "artist": artist_name,
                "album": album_title,
                "track_num": track_num,
                "total_tracks": total_tracks,
                "disc_num": disc_num,
                "date": release_date,
                "genre": genre,
                "cover_bytes": cover_bytes
            })
            
            if progress_callback:
                await progress_callback(1, 1, "Completed")
            return True
            
        except Exception as e:
            # Clean up temp file on failure
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass
            raise e

    def apply_metadata(self, filepath, ext, tags):
        """Applies metadata tags and cover art to the file."""
        cover_bytes = tags.get("cover_bytes")
        
        if ext == "flac":
            audio = FLAC(filepath)
            audio["title"] = tags["title"]
            audio["artist"] = tags["artist"]
            audio["album"] = tags["album"]
            audio["tracknumber"] = str(tags["track_num"])
            audio["totaltracks"] = str(tags["total_tracks"])
            audio["discnumber"] = str(tags["disc_num"])
            audio["date"] = tags["date"]
            audio["genre"] = tags["genre"]
            
            if cover_bytes:
                picture = Picture()
                picture.data = cover_bytes
                picture.type = 3  # Front cover
                picture.mime = "image/jpeg"
                picture.desc = "Front Cover"
                audio.clear_pictures()
                audio.add_picture(picture)
                
            audio.save()
            
        elif ext == "m4a":
            audio = MP4(filepath)
            audio["\xa9nam"] = tags["title"]
            audio["\xa9ART"] = tags["artist"]
            audio["\xa9alb"] = tags["album"]
            audio["trkn"] = [(tags["track_num"], tags["total_tracks"])]
            audio["disk"] = [(tags["disc_num"], 1)]
            audio["\xa9day"] = tags["date"]
            audio["\xa9gen"] = tags["genre"]
            
            if cover_bytes:
                audio["covr"] = [MP4Cover(cover_bytes, imageformat=MP4Cover.FORMAT_JPEG)]
                
            audio.save()
