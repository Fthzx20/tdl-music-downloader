import os
import re
import aiohttp
import aiofiles
import asyncio
import subprocess
import time
import imageio_ffmpeg
from mutagen.flac import FLAC, Picture
import string
from mutagen.mp4 import MP4, MP4Cover

def sanitize_filename(name):
    """Sanitizes strings to be safe for file paths across Windows/macOS/Linux."""
    if not name:
        return "Unknown"
    # Replace forbidden path characters
    clean = re.sub(r'[\/:*?"<>|]', '_', str(name))
    # Strip whitespace and trailing dots (Windows invalid directory/file names)
    clean = clean.strip().rstrip('.').strip()
    # Guard against Windows reserved device names
    reserved = {"CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4", "COM5", 
                "COM6", "COM7", "COM8", "COM9", "LPT1", "LPT2", "LPT3", "LPT4", 
                "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"}
    if clean.upper() in reserved:
        clean = f"_{clean}_"
    return clean or "Unknown"

def clamp_target_path(folder: str, filename: str, max_total_len: int = 245) -> str:
    """
    Clamps filename length so that os.path.join(folder, filename) + '.tmp'
    never exceeds Windows MAX_PATH limit (260 characters).
    """
    folder_abs = os.path.abspath(folder)
    max_fn_len = max(20, max_total_len - len(folder_abs) - 6)
    if len(filename) > max_fn_len:
        base, ext = os.path.splitext(filename)
        allowed_base_len = max(5, max_fn_len - len(ext))
        filename = f"{base[:allowed_base_len].rstrip('. ')}{ext}"
    return os.path.join(folder_abs, filename)

def format_safe_template(template_str, **kwargs):
    """Safely formats a path template without raising KeyError on missing/extra placeholders."""
    class SafeDict(dict):
        def __missing__(self, key):
            return "Unknown"
    try:
        return string.Formatter().vformat(template_str, (), SafeDict(kwargs))
    except Exception:
        return f"{kwargs.get('artist', 'Unknown')}/{kwargs.get('album', 'Unknown')}/{kwargs.get('track_num', '01')} - {kwargs.get('title', 'Unknown')}.{kwargs.get('ext', 'flac')}"

class DownloadManager:
    """Manages queueing, downloading, and tagging of Tidal tracks."""
    
    def __init__(self, api, config):
        self.api = api
        self.config = config
        self.is_paused = False
        self.is_cancelled = False
        self._folder_locks = {}
        c_limit = max(1, min(int(getattr(self.config, 'concurrent_downloads', 3)), 5))
        self.semaphore = asyncio.Semaphore(c_limit)

    def _get_folder_lock(self, folder):
        """Returns or creates an asyncio.Lock specific to an album folder for thread-safe operations."""
        if not folder:
            return asyncio.Lock()
        norm_key = os.path.normcase(os.path.abspath(folder))
        if norm_key not in self._folder_locks:
            self._folder_locks[norm_key] = asyncio.Lock()
        return self._folder_locks[norm_key]

    def update_concurrency(self, new_val):
        """Dynamically adjusts download concurrency."""
        val = max(1, min(int(new_val), 5))
        self.semaphore = asyncio.Semaphore(val)

    async def download_album_goodies(self, album_meta, target_folder, cover_bytes=None):
        """Concurrency-safe helper to download album cover.jpg into target_folder."""
        if not target_folder:
            return
        try:
            os.makedirs(target_folder, exist_ok=True)
        except Exception:
            pass

        folder_lock = self._get_folder_lock(target_folder)
        async with folder_lock:
            cover_path = os.path.join(target_folder, "cover.jpg")
            if not os.path.exists(cover_path):
                if not cover_bytes and album_meta:
                    cover_id = album_meta.get("cover")
                    if cover_id:
                        cover_url = f"https://resources.tidal.com/images/{cover_id.replace('-', '/')}/1280x1280.jpg"
                        try:
                            session = await self.api.get_session()
                            async with session.get(cover_url, timeout=aiohttp.ClientTimeout(total=15)) as c_resp:
                                if c_resp.status == 200:
                                    cover_bytes = await c_resp.read()
                        except Exception as ce:
                            print(f"[Tidal Downloader] Warning: Could not fetch cover image: {ce}")

                if cover_bytes:
                    try:
                        with open(cover_path, "wb") as cf:
                            cf.write(cover_bytes)
                    except Exception as e:
                        print(f"[Tidal Downloader] Failed to write cover.jpg: {e}")

    async def download_track(self, track_id, progress_callback=None, parent_folder=None, task_state=None):
        """Downloads a track, parses manifest, concatenates segments, verifies integrity, and writes tags.
        
        progress_callback: func(bytes_downloaded, total_bytes, status_text)
        parent_folder: str (optional) A custom folder name to save the track in (e.g., Playlist Name)
        task_state: dict (optional) Dictionary containing {"is_paused": bool, "is_cancelled": bool}
        """
        async with self.semaphore:
            if progress_callback:
                await progress_callback(0, 1, "Fetching metadata...")

            # 1. Fetch Track & Album Metadata with 404 delisted protection
            try:
                track = await self.api.get_track(track_id)
            except Exception as e:
                err_msg = str(e)
                if "404" in err_msg or "delisted" in err_msg.lower() or "not found" in err_msg.lower():
                    return {
                        "status": "failed",
                        "error": "Track delisted / unavailable on Tidal (404)",
                        "final_path": None
                    }
                raise e

            if not track or not isinstance(track, dict):
                return {
                    "status": "failed",
                    "error": f"Could not retrieve track metadata for ID {track_id}",
                    "final_path": None
                }

            album_id = track.get("album", {}).get("id") if track.get("album") else None
            album = {}
            if album_id:
                try:
                    album = await self.api.get_album(album_id)
                except Exception:
                    album = track.get("album") or {}
            
            # Track details with defensive fallbacks
            title = track.get("title", "Unknown Title")
            if track.get("artist") and isinstance(track["artist"], dict):
                artist_name = track["artist"].get("name", "Unknown Artist")
            elif track.get("artists") and isinstance(track["artists"], list) and len(track["artists"]) > 0:
                artist_name = track["artists"][0].get("name", "Unknown Artist")
            else:
                artist_name = "Unknown Artist"

            album_title = album.get("title", "Unknown Album") if album else "Unknown Album"
            
            # Album artist
            album_artist = ""
            if album.get("artist") and isinstance(album["artist"], dict):
                album_artist = album["artist"].get("name", "")
            elif album.get("artists") and isinstance(album["artists"], list) and len(album["artists"]) > 0:
                album_artist = album["artists"][0].get("name", "")
            if not album_artist:
                album_artist = artist_name

            track_num = track.get("trackNumber", 1)
            total_tracks = album.get("numberOfTracks", 1) if album else 1
            disc_num = track.get("volumeNumber", 1)
            total_discs = album.get("numberOfVolumes", 1) if album else 1
            release_date = album.get("releaseDate", "") if album else ""
            genre = album.get("genre", "") if album else ""
            year = release_date.split("-")[0] if release_date else ""
            isrc = track.get("isrc", "")
            copyright_str = album.get("copyright") or track.get("copyright") or ""
            label_name = album.get("recordLabel") or album.get("label") or copyright_str or ""
            
            composer = ""
            if track.get("composer") and isinstance(track["composer"], dict):
                composer = track["composer"].get("name", "")
            elif track.get("composer") and isinstance(track["composer"], str):
                composer = track["composer"]

            try:
                track_num = int(track_num)
            except Exception:
                track_num = 1
            try:
                total_tracks = int(total_tracks)
            except Exception:
                total_tracks = 1
            try:
                disc_num = int(disc_num)
            except Exception:
                disc_num = 1
            try:
                total_discs = int(total_discs)
            except Exception:
                total_discs = 1

            quality = self.config.quality_tier
            if progress_callback:
                await progress_callback(0, 1, "Fetching stream URL...")

            try:
                stream_info = await self.api.get_stream_info(track_id, quality)
            except Exception as e:
                err_msg = str(e)
                if "404" in err_msg or "delisted" in err_msg.lower() or "not found" in err_msg.lower():
                    return {
                        "status": "failed",
                        "error": "Stream delisted / geo-restricted on Tidal (404)",
                        "final_path": None
                    }
                raise e

            ext = stream_info.get("extension", "flac")
            bd = stream_info.get("bit_depth") or (24 if quality == "HI_RES_LOSSLESS" else 16)
            sr = stream_info.get("sample_rate") or (192000 if quality == "HI_RES_LOSSLESS" else 44100)

            # Format spec labels
            sr_val = float(sr) / 1000.0 if float(sr) > 1000 else float(sr)
            sr_str = f"{int(sr_val)}kHz" if sr_val.is_integer() else f"{sr_val:g}kHz"
            bd_str = f"{bd}bit"
            qual_str = f"{bd_str}-{sr_str}"

            # Format the output paths
            safe_artist = sanitize_filename(artist_name)
            safe_album = sanitize_filename(album_title)
            safe_title = sanitize_filename(title)

            template = getattr(self.config, 'file_template', '{artist}/{album}/{track_num} - {title}.{ext}')
            base_dir = self.config.download_directory
            if parent_folder:
                safe_parent = sanitize_filename(parent_folder)
                base_dir = os.path.join(base_dir, safe_parent)

            self._current_format_args = {
                "artist": safe_artist,
                "album": safe_album,
                "track_num": f"{track_num:02d}",
                "title": safe_title,
                "disc_num": f"{disc_num:02d}",
                "year": year or "Unknown",
                "genre": sanitize_filename(genre) if genre else "Unknown",
                "total_tracks": f"{total_tracks:02d}",
                "total_discs": f"{total_discs:02d}",
                "bit_depth": bd_str,
                "sample_rate": sr_str,
                "quality": qual_str,
                "label": sanitize_filename(label_name) if label_name else "Unknown",
                "composer": sanitize_filename(composer) if composer else "Unknown",
                "isrc": sanitize_filename(isrc) if isrc else "Unknown",
                "ext": ext
            }

            if parent_folder:
                prefix = f"{disc_num}-{track_num:02d}" if disc_num > 1 else f"{track_num:02d}"
                folder_base = os.path.basename(os.path.normpath(parent_folder)).lower()
                if safe_artist.lower() in folder_base or not safe_artist:
                    raw_filename = f"{prefix} - {safe_title}.{ext}"
                else:
                    raw_filename = f"{prefix} - {safe_artist} - {safe_title}.{ext}"
                final_path = clamp_target_path(base_dir, raw_filename)
                album_dir = base_dir
            else:
                rel_path = format_safe_template(template, **self._current_format_args)
                rel_dir = os.path.dirname(rel_path)
                rel_file = os.path.basename(rel_path)
                target_dir = os.path.join(base_dir, rel_dir)
                final_path = clamp_target_path(target_dir, rel_file)
                album_dir = os.path.dirname(final_path)

            os.makedirs(album_dir, exist_ok=True)
            temp_path = final_path + ".tmp"

            # 2. Fast Sync Skip check
            if os.path.exists(final_path) and os.path.getsize(final_path) > 1024:
                await self.download_album_goodies(album, album_dir)
                spec_str = f" ({bd}-bit/{sr_str} {ext.upper()})"
                if progress_callback:
                    await progress_callback(1, 1, f"Skipped (Already Downloaded){spec_str}")
                return {
                    "final_path": final_path,
                    "spec_str": spec_str,
                    "bit_depth": bd,
                    "sample_rate": sr,
                    "extension": ext
                }

            # 3. Lyrics retrieval (Tidal primary with LRCLIB fallback)
            lyrics_text = ''
            if progress_callback:
                await progress_callback(0, 1, 'Fetching lyrics...')
            try:
                lyrics_data = await self.api.get_track_lyrics(track_id)
                if lyrics_data:
                    if lyrics_data.get('subtitles'):
                        lyrics_text = lyrics_data['subtitles']
                    elif lyrics_data.get('lyrics'):
                        lyrics_text = lyrics_data['lyrics']
            except Exception:
                pass

            if not lyrics_text:
                try:
                    from .lyrics import fetch_lyrics
                    lrc_info = await fetch_lyrics(title, artist_name, album_title, int(track.get("duration", 0)))
                    if lrc_info:
                        lyrics_text = lrc_info.get("synced") or lrc_info.get("plain") or ""
                except Exception as le:
                    print(f"LRCLIB fallback lookup: {le}")

            if lyrics_text:
                lrc_prefix = f"{disc_num}-{track_num:02d}" if disc_num > 1 else f"{track_num:02d}"
                lrc_filename = f"{lrc_prefix} - {safe_title}.lrc"
                lrc_path = clamp_target_path(album_dir, lrc_filename)
                try:
                    with open(lrc_path, 'w', encoding='utf-8') as lf:
                        lf.write(lyrics_text.strip() + "\n")
                except Exception as e:
                    print(f'Failed lyrics write: {e}')

            # 4. Perform Download
            session = await self.api.get_session()
            try:
                if stream_info["type"] == "direct":
                    url = stream_info["url"]
                    max_retries = 4
                    total_size = 0
                    downloaded = 0
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
                                        if now - last_time >= 0.3:
                                            current_speed = (downloaded - last_downloaded) / (now - last_time)
                                            if smoothed_speed is None:
                                                smoothed_speed = current_speed
                                            else:
                                                smoothed_speed = 0.5 * smoothed_speed + 0.5 * current_speed
                                                
                                            last_time = now
                                            last_downloaded = downloaded
                                            if progress_callback:
                                                await progress_callback(
                                                    downloaded, total_size,
                                                    f"Downloading: {downloaded / 1024 / 1024:>5.1f}MB / {total_size / 1024 / 1024:>5.1f}MB       ({smoothed_speed / 1024 / 1024:>4.1f} MB/s)"
                                                )
                            break
                        except Exception as e:
                            if (task_state and task_state.get("is_cancelled", False)) or self.is_cancelled or attempt == max_retries - 1:
                                raise e
                            if progress_callback:
                                await progress_callback(downloaded, 1, f"Network Error. Retrying ({attempt+1}/{max_retries})...")
                            await asyncio.sleep(2)

                    # Integrity verification: stream completion check
                    if total_size > 0 and downloaded < total_size:
                        raise Exception(f"Incomplete download: received {downloaded}/{total_size} bytes. Stream was truncated.")
                                    
                elif stream_info["type"] == "dash":
                    init_url = stream_info["init_url"]
                    segment_urls = stream_info["segment_urls"]
                    total_segments = len(segment_urls)
                    downloaded = 0
                    last_time = time.time()
                    last_downloaded = 0
                    smoothed_speed = None
                    
                    async with aiofiles.open(temp_path, "wb") as f:
                        if init_url:
                            if progress_callback:
                                await progress_callback(0, total_segments, "Downloading initialization segment...")
                            async with session.get(init_url) as resp:
                                resp.raise_for_status()
                                await f.write(await resp.read())
                        
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
                                            if now - last_time >= 0.3:
                                                current_speed = (downloaded - last_downloaded) / (now - last_time)
                                                if smoothed_speed is None:
                                                    smoothed_speed = current_speed
                                                else:
                                                    smoothed_speed = 0.5 * smoothed_speed + 0.5 * current_speed
                                                    
                                                last_time = now
                                                last_downloaded = downloaded
                                                if progress_callback:
                                                    await progress_callback(
                                                        idx, total_segments,
                                                        f"Downloading segment {idx + 1:02d}/{total_segments:02d}       ({smoothed_speed / 1024 / 1024:>4.1f} MB/s)"
                                                    )
                                    break
                                except Exception as e:
                                    if (task_state and task_state.get("is_cancelled", False)) or self.is_cancelled or attempt == max_retries - 1:
                                        raise e
                                    await asyncio.sleep(2)
                                    
                # Convert/Extract if needed
                if stream_info["type"] == "dash" and ext == "flac":
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

                # Payload size verification
                actual_size = os.path.getsize(temp_path) if os.path.exists(temp_path) else 0
                if actual_size < 1024:
                    raise Exception(f"Downloaded audio stream is corrupt or empty ({actual_size} bytes)")
                    
                # Safe atomic replace
                if os.path.exists(final_path):
                    try:
                        os.remove(final_path)
                    except Exception:
                        pass
                os.replace(temp_path, final_path)
                
                # 5. Mutagen STREAMINFO header verification
                if ext == "flac":
                    try:
                        audio_check = FLAC(final_path)
                        true_bd = getattr(audio_check.info, "bits_per_sample", bd)
                        true_sr = getattr(audio_check.info, "sample_rate", sr)
                        bd = true_bd
                        sr = true_sr
                        sr_val = float(sr) / 1000.0 if float(sr) > 1000 else float(sr)
                        sr_str = f"{int(sr_val)}kHz" if sr_val.is_integer() else f"{sr_val:g}kHz"
                    except Exception as e:
                        print(f"[Mutagen Integrity Check Warning] {e}")

                # 6. Embedded Metadata Tagging & cover.jpg save
                if progress_callback:
                    await progress_callback(100, 100, "Applying metadata tags...")
                    
                cover_bytes = None
                cover_id = album.get("cover")
                if cover_id:
                    cover_url = f"https://resources.tidal.com/images/{cover_id.replace('-', '/')}/1280x1280.jpg"
                    try:
                        async with session.get(cover_url) as resp:
                            if resp.status == 200:
                                cover_bytes = await resp.read()
                    except Exception as e:
                        print(f"Failed to fetch album cover: {e}")

                # Concurrency-safe folder cover.jpg save
                await self.download_album_goodies(album, album_dir, cover_bytes=cover_bytes)
                        
                spec_tag = f"Tidal Studio Master • {bd}-bit/{sr_str}" if ext == "flac" else f"Tidal AAC • {ext.upper()}"

                tags_dict = {
                    "title": title,
                    "artist": artist_name,
                    "album_artist": album_artist,
                    "album": album_title,
                    "track_num": track_num,
                    "total_tracks": total_tracks,
                    "disc_num": disc_num,
                    "total_discs": total_discs,
                    "date": release_date,
                    "year": year,
                    "genre": genre,
                    "isrc": isrc,
                    "copyright": copyright_str,
                    "composer": composer,
                    "comment": spec_tag,
                    "cover_bytes": cover_bytes,
                    "lyrics": lyrics_text
                }
                await asyncio.to_thread(self.apply_metadata, final_path, ext, tags_dict)

                # 7. Checksums.md5 generation with folder lock
                folder_lock = self._get_folder_lock(album_dir)
                async with folder_lock:
                    try:
                        import hashlib
                        hasher = hashlib.md5()
                        with open(final_path, "rb") as af:
                            while chunk := af.read(128 * 1024):
                                hasher.update(chunk)
                        md5_val = hasher.hexdigest()
                        base_name = os.path.basename(final_path)
                        chk_file = os.path.join(album_dir, "checksums.md5")
                        existing = ""
                        if os.path.exists(chk_file):
                            with open(chk_file, "r", encoding="utf-8", errors="ignore") as rf:
                                existing = rf.read()
                        if base_name not in existing:
                            with open(chk_file, "a", encoding="utf-8") as wf:
                                wf.write(f"{md5_val} *{base_name}\n")
                    except Exception as me:
                        print(f"Warning: Failed to write MD5 checksum: {me}")
                
                spec_str = f" ({bd}-bit/{sr_str} {ext.upper()})" if bd and sr else f" ({ext.upper()})"

                if progress_callback:
                    await progress_callback(1, 1, f"Completed{spec_str}")
                return {
                    "status": "completed",
                    "final_path": final_path,
                    "spec_str": spec_str,
                    "bit_depth": bd,
                    "sample_rate": sr,
                    "extension": ext
                }
                
            except Exception as e:
                for tp in [temp_path, final_path + ".tmp", final_path + ".raw.tmp"]:
                    if os.path.exists(tp):
                        try:
                            os.remove(tp)
                        except Exception:
                            pass
                raise e

    def apply_metadata(self, filepath, ext, tags):
        """Applies comprehensive audiophile metadata tags and cover art to the file."""
        cover_bytes = tags.get("cover_bytes")
        total_discs = str(tags.get("total_discs", 1))
        
        if ext == "flac":
            audio = FLAC(filepath)
            audio["TITLE"] = str(tags.get("title", ""))
            audio["ARTIST"] = str(tags.get("artist", ""))
            audio["ALBUM"] = str(tags.get("album", ""))
            if tags.get("album_artist"):
                audio["ALBUMARTIST"] = str(tags["album_artist"])
            audio["TRACKNUMBER"] = str(tags.get("track_num", 1))
            audio["TRACKTOTAL"] = str(tags.get("total_tracks", 1))
            audio["totaltracks"] = str(tags.get("total_tracks", 1))
            audio["DISCNUMBER"] = str(tags.get("disc_num", 1))
            audio["DISCTOTAL"] = total_discs
            audio["totaldiscs"] = total_discs
            if tags.get("date"):
                audio["DATE"] = str(tags["date"])
            if tags.get("year"):
                audio["YEAR"] = str(tags["year"])
            if tags.get("genre"):
                audio["GENRE"] = str(tags["genre"])
            if tags.get("isrc"):
                audio["ISRC"] = str(tags["isrc"])
            if tags.get("copyright"):
                audio["COPYRIGHT"] = str(tags["copyright"])
            if tags.get("composer"):
                audio["COMPOSER"] = str(tags["composer"])
            if tags.get("comment"):
                audio["COMMENT"] = str(tags["comment"])
            
            if cover_bytes:
                picture = Picture()
                picture.data = cover_bytes
                picture.type = 3  # Front cover
                picture.mime = "image/jpeg"
                picture.desc = "Front Cover"
                audio.clear_pictures()
                audio.add_picture(picture)
                
            if tags.get("lyrics"):
                audio["UNSYNCEDLYRICS"] = str(tags["lyrics"])
                audio["LYRICS"] = str(tags["lyrics"])
                
            audio.save()
            
        elif ext == "m4a":
            audio = MP4(filepath)
            audio["\xa9nam"] = str(tags.get("title", ""))
            audio["\xa9ART"] = str(tags.get("artist", ""))
            if tags.get("album_artist"):
                audio["aART"] = str(tags["album_artist"])
            audio["\xa9alb"] = str(tags.get("album", ""))
            audio["trkn"] = [(int(tags.get("track_num", 1)), int(tags.get("total_tracks", 1)))]
            audio["disk"] = [(int(tags.get("disc_num", 1)), int(tags.get("total_discs", 1)))]
            if tags.get("date"):
                audio["\xa9day"] = str(tags["date"])
            if tags.get("genre"):
                audio["\xa9gen"] = str(tags["genre"])
            if tags.get("copyright"):
                audio["cprt"] = str(tags["copyright"])
            if tags.get("composer"):
                audio["\xa9wrt"] = str(tags["composer"])
            if tags.get("comment"):
                audio["\xa9cmt"] = str(tags["comment"])
            
            if cover_bytes:
                audio["covr"] = [MP4Cover(cover_bytes, imageformat=MP4Cover.FORMAT_JPEG)]
                
            if tags.get("lyrics"):
                audio["\xa9lyr"] = str(tags["lyrics"])
                
            audio.save()
