import asyncio
import re
import urllib.request
import urllib.parse
import json

def is_external_music_link(text):
    """Detects if input text is an external music streaming URL."""
    if not isinstance(text, str):
        return False
    t = text.strip().lower()
    return any(domain in t for domain in [
        "spotify.com", "open.spotify.com", "spotify:",
        "music.apple.com", "itunes.apple.com",
        "youtube.com", "youtu.be", "music.youtube.com",
        "deezer.com", "deezer.page.link",
        "soundcloud.com"
    ])

def clean_music_title(title):
    """Removes common noise from music titles like video tags, remaster brackets, etc."""
    if not title:
        return ""
    # Remove common video brackets
    t = re.sub(
        r"\s*[\(\[](?:Official Music Video|Official Video|Official Audio|Music Video|Official Visualizer|Visualizer|Lyrics|Lyric Video|Audio|4K Remaster|Remastered \d+|Remastered|HD|Video|Clip Officiel)[\)\]]",
        "",
        title,
        flags=re.I
    )
    # Remove leading/trailing quotes or dashes
    t = t.strip(" -\"'")
    return t

async def resolve_external_link(url):
    """
    Asynchronously resolves an external music link to Tidal search parameters.
    Returns: (search_query, search_type, display_info, service_name)
    Or (None, None, None, None) if not resolvable.
    """
    url = url.strip()
    
    # -------------------------------------------------------------
    # 1. SPOTIFY
    # -------------------------------------------------------------
    if "spotify.com" in url or url.startswith("spotify:"):
        # Normalize spotify URI: spotify:track:xxx -> https://open.spotify.com/track/xxx
        if url.startswith("spotify:"):
            parts = url.split(":")
            if len(parts) >= 3:
                url = f"https://open.spotify.com/{parts[1]}/{parts[2]}"

        # Remove query parameters for cleaner scraping
        clean_url = url.split("?")[0]
        
        req = urllib.request.Request(
            clean_url,
            headers={'User-Agent': 'facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)'}
        )
        def fetch_spotify():
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.read().decode('utf-8', errors='ignore')
                
        try:
            html = await asyncio.to_thread(fetch_spotify)
            title_m = re.search(r'<meta (?:property|name)="og:title" content="([^"]+)"', html)
            desc_m = re.search(r'<meta (?:property|name)="og:description" content="([^"]+)"', html)
            
            raw_title = title_m.group(1) if title_m else ""
            raw_desc = desc_m.group(1) if desc_m else ""
            
            # Split description by middle dot, bullet, hyphen, etc.
            parts = [p.strip() for p in re.split(r'[\xb7\u2022\u2027\u2219\u25cf\u25cb\-\|]', raw_desc) if p.strip()]
            
            if "/track/" in clean_url:
                artist = parts[0] if parts else ""
                clean_track = clean_music_title(raw_title)
                query = f"{artist} {clean_track}".strip()
                return query, "tracks", f"Spotify Track: {clean_track} by {artist}", "Spotify"
                
            elif "/album/" in clean_url:
                artist = ""
                by_m = re.search(r" - (?:Album|Single|EP) by (.*?) \| Spotify", raw_title, re.I)
                if by_m:
                    artist = by_m.group(1).strip()
                elif parts:
                    artist = parts[0]
                clean_album = re.sub(r" - (?:Album|Single|EP) by .*? \| Spotify", "", raw_title, flags=re.I).strip()
                clean_album = re.sub(r" \| Spotify", "", clean_album, flags=re.I).strip()
                query = f"{artist} {clean_album}".strip()
                return query, "albums", f"Spotify Album: {clean_album} by {artist}", "Spotify"
                
            elif "/playlist/" in clean_url:
                clean_pl = re.sub(r" \| Spotify", "", raw_title, flags=re.I).strip()
                return clean_pl, "playlists", f"Spotify Playlist: {clean_pl}", "Spotify"
                
            elif "/artist/" in clean_url:
                clean_artist = re.sub(r" \| Spotify", "", raw_title, flags=re.I).strip()
                return clean_artist, "artists", f"Spotify Artist: {clean_artist}", "Spotify"
        except Exception as e:
            print(f"Spotify link resolution error: {e}")

    # -------------------------------------------------------------
    # 2. APPLE MUSIC / ITUNES
    # -------------------------------------------------------------
    elif "music.apple.com" in url or "itunes.apple.com" in url:
        track_match = re.search(r"[?&]i=(\d+)", url)
        album_match = re.search(r"/album/(?:[^/]+/)?(\d+)", url)
        slug_match = re.search(r"/(?:album|song|artist)/([^/]+)/(\d+)", url)
        
        slug_title = slug_match.group(1).replace("-", " ") if slug_match else ""
        
        try:
            if track_match and album_match:
                tid = track_match.group(1)
                aid = album_match.group(1)
                api_url = f"https://itunes.apple.com/lookup?id={aid}&entity=song"
                def fetch_am_album_songs():
                    req = urllib.request.Request(api_url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        return json.loads(resp.read().decode('utf-8'))
                data = await asyncio.to_thread(fetch_am_album_songs)
                results = data.get("results", [])
                artist_name = results[0].get("artistName", "") if results else ""
                track_name = slug_title
                for r in results:
                    if str(r.get("trackId")) == str(tid):
                        track_name = r.get("trackName", track_name)
                        artist_name = r.get("artistName", artist_name)
                        break
                query = f"{artist_name} {track_name}".strip()
                return query, "tracks", f"Apple Music Track: {track_name} by {artist_name}", "Apple Music"
                
            elif album_match:
                aid = album_match.group(1)
                api_url = f"https://itunes.apple.com/lookup?id={aid}"
                def fetch_am_album():
                    req = urllib.request.Request(api_url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        return json.loads(resp.read().decode('utf-8'))
                data = await asyncio.to_thread(fetch_am_album)
                results = data.get("results", [])
                if results:
                    c_name = results[0].get("collectionName", slug_title)
                    a_name = results[0].get("artistName", "")
                    return f"{a_name} {c_name}".strip(), "albums", f"Apple Music Album: {c_name} by {a_name}", "Apple Music"
                return slug_title, "albums", f"Apple Music Album: {slug_title}", "Apple Music"
                
            elif "/playlist/" in url:
                slug_p = re.search(r"/playlist/([^/]+)/", url)
                p_name = slug_p.group(1).replace("-", " ") if slug_p else "Playlist"
                return p_name, "playlists", f"Apple Music Playlist: {p_name}", "Apple Music"
                
            elif "/artist/" in url:
                slug_a = re.search(r"/artist/([^/]+)/", url)
                a_name = slug_a.group(1).replace("-", " ") if slug_a else "Artist"
                return a_name, "artists", f"Apple Music Artist: {a_name}", "Apple Music"
        except Exception as e:
            print(f"Apple Music resolution error: {e}")

    # -------------------------------------------------------------
    # 3. YOUTUBE & YOUTUBE MUSIC
    # -------------------------------------------------------------
    elif "youtube.com" in url or "youtu.be" in url:
        try:
            api_url = f"https://www.youtube.com/oembed?url={urllib.parse.quote(url)}&format=json"
            def fetch_yt():
                req = urllib.request.Request(api_url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    return json.loads(resp.read().decode('utf-8'))
            data = await asyncio.to_thread(fetch_yt)
            raw_title = data.get("title", "")
            author = data.get("author_name", "")
            clean_title = clean_music_title(raw_title)
            
            # If playlist
            if "list=" in url and "/watch" not in url:
                return clean_title, "playlists", f"YouTube Playlist: {clean_title}", "YouTube"
                
            return clean_title, "tracks", f"YouTube Track: {clean_title}", "YouTube"
        except Exception as e:
            print(f"YouTube resolution error: {e}")

    # -------------------------------------------------------------
    # 4. DEEZER
    # -------------------------------------------------------------
    elif "deezer.com" in url:
        try:
            t_m = re.search(r"/track/(\d+)", url)
            a_m = re.search(r"/album/(\d+)", url)
            p_m = re.search(r"/playlist/(\d+)", url)
            ar_m = re.search(r"/artist/(\d+)", url)
            
            if t_m:
                api_url = f"https://api.deezer.com/track/{t_m.group(1)}"
                def fetch_dz_track():
                    req = urllib.request.Request(api_url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        return json.loads(resp.read().decode('utf-8'))
                data = await asyncio.to_thread(fetch_dz_track)
                title = data.get("title", "")
                artist = data.get("artist", {}).get("name", "")
                return f"{artist} {title}".strip(), "tracks", f"Deezer Track: {title} by {artist}", "Deezer"
                
            elif a_m:
                api_url = f"https://api.deezer.com/album/{a_m.group(1)}"
                def fetch_dz_album():
                    req = urllib.request.Request(api_url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        return json.loads(resp.read().decode('utf-8'))
                data = await asyncio.to_thread(fetch_dz_album)
                title = data.get("title", "")
                artist = data.get("artist", {}).get("name", "")
                return f"{artist} {title}".strip(), "albums", f"Deezer Album: {title} by {artist}", "Deezer"
                
            elif p_m:
                api_url = f"https://api.deezer.com/playlist/{p_m.group(1)}"
                def fetch_dz_pl():
                    req = urllib.request.Request(api_url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        return json.loads(resp.read().decode('utf-8'))
                data = await asyncio.to_thread(fetch_dz_pl)
                title = data.get("title", "")
                return title, "playlists", f"Deezer Playlist: {title}", "Deezer"
                
            elif ar_m:
                api_url = f"https://api.deezer.com/artist/{ar_m.group(1)}"
                def fetch_dz_ar():
                    req = urllib.request.Request(api_url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        return json.loads(resp.read().decode('utf-8'))
                data = await asyncio.to_thread(fetch_dz_ar)
                name = data.get("name", "")
                return name, "artists", f"Deezer Artist: {name}", "Deezer"
        except Exception as e:
            print(f"Deezer resolution error: {e}")

    # -------------------------------------------------------------
    # 5. SOUNDCLOUD
    # -------------------------------------------------------------
    elif "soundcloud.com" in url:
        try:
            api_url = f"https://soundcloud.com/oembed?url={urllib.parse.quote(url)}&format=json"
            def fetch_sc():
                req = urllib.request.Request(api_url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    return json.loads(resp.read().decode('utf-8'))
            data = await asyncio.to_thread(fetch_sc)
            raw_title = data.get("title", "")
            author = data.get("author_name", "")
            # Title is often "Song Name by Author"
            clean_title = re.sub(r" by .*$", "", raw_title, flags=re.I).strip()
            query = f"{author} {clean_title}".strip()
            return query, "tracks", f"SoundCloud Track: {clean_title} by {author}", "SoundCloud"
        except Exception as e:
            print(f"SoundCloud resolution error: {e}")

    return None, None, None, None
