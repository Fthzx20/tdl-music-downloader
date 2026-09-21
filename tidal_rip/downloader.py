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

        template = getattr(self.config, 'file_template', '{artist}/{album}/{track_num} - {title}.{ext}')
        base_dir = self.config.download_directory
        if parent_folder:
            safe_parent = sanitize_filename(parent_folder)
            base_dir = os.path.join(base_dir, safe_parent)

        rel_path_flac = template.format(artist=safe_artist, album=safe_album, track_num=f'{track_num:02d}', title=safe_title, ext='flac')
        rel_path_m4a = template.format(artist=safe_artist, album=safe_album, track_num=f'{track_num:02d}', title=safe_title, ext='m4a')
        rel_path_flac = rel_path_flac.replace('/', os.sep).replace('\\', os.sep)
        rel_path_m4a = rel_path_m4a.replace('/', os.sep).replace('\\', os.sep)

        flac_path = os.path.join(base_dir, rel_path_flac)
        m4a_path = os.path.join(base_dir, rel_path_m4a)

        album_dir = os.path.dirname(flac_path)
        os.makedirs(album_dir, exist_ok=True)

        if os.path.exists(flac_path) and os.path.getsize(flac_path) > 0:
            if progress_callback: await progress_callback(1, 1, 'Skipped (Already Downloaded)')
            return flac_path
        if os.path.exists(m4a_path) and os.path.getsize(m4a_path) > 0:
            if progress_callback: await progress_callback(1, 1, 'Skipped (Already Downloaded)')
            return m4a_path

        lyrics_text = ''
        if progress_callback: await progress_callback(0, 1, 'Fetching lyrics...')
        try:
            lyrics_data = await self.api.get_track_lyrics(track_id)
            if lyrics_data:
                lrc_path = os.path.join(album_dir, f'{track_num:02d} - {safe_title}.lrc')
                if lyrics_data.get('subtitles'):
                    lyrics_text = lyrics_data['subtitles']
                elif lyrics_data.get('lyrics'):
                    lyrics_text = lyrics_data['lyrics']
                if lyrics_text:
                    with open(lrc_path, 'w', encoding='utf-8') as f: f.write(lyrics_text)
        except Exception as e: print(f'Failed lyrics: {e}')

        quality = self.config.quality_tier
        if progress_callback: await progress_callback(0, 1, 'Fetching stream URL...')
        stream_info = await self.api.get_stream_info(track_id, quality)
        ext = stream_info['extension']

        rel_path_final = template.format(artist=safe_artist, album=safe_album, track_num=f'{track_num:02d}', title=safe_title, ext=ext)
        rel_path_final = rel_path_final.replace('/', os.sep).replace('\\', os.sep)
        final_path = os.path.join(base_dir, rel_path_final)
        temp_path = final_path + '.tmp'
        
        # 3. Perform Download
        session = await self.api.get_session()
        try:
            if stream_info["type"] == "direct":
                # Direct file download
                url = stream_info["url"]
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        downloaded = 0
                        if os.path.exists(temp_path):
                            downloaded = os.path.getsize(temp_path)
                            
                        headers = {}
                        if downloaded > 0:
                            headers["Range"] = f"bytes={downloaded}-"
                            
                        async with session.get(url, headers=headers) as resp:
                            resp.raise_for_status()
                            total_size = int(resp.headers.get("Content-Length", 0)) + downloaded
                            last_time = time.time()
                            last_downloaded = downloaded
                            smoothed_speed = None
                            
                            mode = "ab" if downloaded > 0 else "wb"
                            async with aiofiles.open(temp_path, mode) as f:
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
                        break # Exit retry loop on success
                    except Exception as e:
                        if (task_state and task_state.get("is_cancelled", False)) or self.is_cancelled or attempt == max_retries - 1:
                            raise e
                        if progress_callback:
                            await progress_callback(downloaded, 1, f"Network Error. Retrying ({attempt+1}/{max_retries})...")
                        await asyncio.sleep(2)
                                
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
                            
                        max_retries = 3
                        for attempt in range(max_retries):
                            try:
                                if progress_callback:
                                    if attempt > 0:
                                        await progress_callback(idx, total_segments, f"Retrying segment {idx + 1:02d}/{total_segments:02d}... ({attempt}/{max_retries})")
                                    else:
                                        await progress_callback(idx, total_segments, f"Downloading segment {idx + 1:02d}/{total_segments:02d}...")
                                        
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
                                                await progress_callback(idx, total_segments, f"Downloading segment {idx + 1:02d}/{total_segments:02d}       ({smoothed_speed / 1024 / 1024:>4.1f} MB/s)")
                                break # Success
                            except Exception as e:
                                if (task_state and task_state.get("is_cancelled", False)) or self.is_cancelled or attempt == max_retries - 1:
                                    raise e
                                await asyncio.sleep(2)
                                
            # Convert/Extract if needed
            if stream_info["type"] == "dash" and ext == "flac":
                # DASH FLAC streams are encapsulated in MP4 containers. Extract the raw FLAC.
                if progress_callback:
                    await progress_callback(100, 100, "Extracting FLAC stream from MP4 container...")
                
                ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
                raw_flac_path = final_path + ".raw.tmp"
                try:
                    proc = await asyncio.create_subprocess_exec(
                        ffmpeg_exe, "-y", "-i", temp_path, "-c:a", "copy", "-f", "flac", raw_flac_path,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    
                    async def wait_ffmpeg():
                        return await proc.communicate()
                        
                    ff_task = asyncio.create_task(wait_ffmpeg())
                    while not ff_task.done():
                        if (task_state and task_state.get("is_cancelled", False)) or self.is_cancelled:
                            proc.kill()
                            raise Exception("Cancelled by user during extraction")
                        await asyncio.sleep(0.5)
                        
                    stdout, stderr = ff_task.result()
                    if proc.returncode != 0:
                        err_msg = stderr.decode().strip().split('\n')[-1] if stderr else "Unknown error"
                        raise Exception(f"Failed to extract FLAC stream. FFmpeg error: {err_msg}")
                        
                    os.remove(temp_path)
                    temp_path = raw_flac_path
                except Exception as e:
                    print(f"FFmpeg extraction failed: {e}")
                    raise e

            if (task_state and task_state.get("is_cancelled", False)) or self.is_cancelled:
                raise Exception("Cancelled by user before tagging")
                
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
                    
            # Apply tags using Mutagen in a background thread to prevent blocking the async loop
            tags_dict = {
                "title": title,
                "artist": artist_name,
                "album": album_title,
                "track_num": track_num,
                "total_tracks": total_tracks,
                "disc_num": disc_num,
                "date": release_date,
                "genre": genre,
                "cover_bytes": cover_bytes,
                "lyrics": lyrics_text
            }
            await asyncio.to_thread(self.apply_metadata, final_path, ext, tags_dict)
            
            spec_str = ""
            bd = stream_info.get("bit_depth")
            sr = stream_info.get("sample_rate")
            if bd and sr:
                sr_khz = f"{sr/1000:g}kHz"
                spec_str = f" ({bd}-bit/{sr_khz} {ext.upper()})"
            elif ext:
                spec_str = f" ({ext.upper()})"

            if progress_callback:
                await progress_callback(1, 1, f"Completed{spec_str}")
            return {
                "final_path": final_path,
                "spec_str": spec_str,
                "bit_depth": bd,
                "sample_rate": sr,
                "extension": ext
            }
            
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
                
            if tags.get("lyrics"):
                audio["UNSYNCEDLYRICS"] = tags["lyrics"]
                
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
                
            if tags.get("lyrics"):
                audio["\xa9lyr"] = tags["lyrics"]
                
            audio.save()
