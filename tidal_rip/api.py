import asyncio
import base64
import hashlib
import json
import os
import random
import time
import xml.etree.ElementTree as ET
import urllib.parse
import aiohttp
import re
import unicodedata

class TidalAPI:
    """Asynchronous client for interacting with the Tidal API."""
    
    BASE_URL = "https://api.tidal.com/v1"
    AUTH_URL = "https://auth.tidal.com/v1/oauth2"
    
    def __init__(self, config):
        self.config = config
        self.session = None
        self.country_code = "US"  # Default fallback

    async def get_session(self):
        """Lazy-loaded aiohttp client session with TCP connection pooling and keepalive."""
        if self.session is None or self.session.closed:
            connector = aiohttp.TCPConnector(limit=50, keepalive_timeout=60, enable_cleanup_closed=True)
            timeout = aiohttp.ClientTimeout(total=60, sock_connect=15)
            self.session = aiohttp.ClientSession(connector=connector, timeout=timeout)
        return self.session

    async def close(self):
        """Closes the client session."""
        if self.session and not self.session.closed:
            await self.session.close()

    async def _api_request(self, method, endpoint, params=None, json_data=None, retry_auth=True):
        """Helper to perform requests with Bearer token authentication and auto-refresh."""
        session = await self.get_session()
        
        # Check token expiration
        if self.config.refresh_token and (self.config.token_expiry - time.time() < 300): # 5 min buffer
            try:
                await self.refresh_token()
            except Exception as e:
                print(f"Auto-token refresh failed: {e}")

        url = f"{self.BASE_URL}/{endpoint.lstrip('/')}"
        
        # Inject standard parameters
        request_params = params.copy() if params else {}
        if "countryCode" not in request_params:
            request_params["countryCode"] = self.country_code

        headers = {}
        if self.config.access_token:
            headers["Authorization"] = f"Bearer {self.config.access_token}"

        try:
            async with session.request(method, url, headers=headers, params=request_params, json=json_data) as resp:
                if resp.status == 401 and retry_auth and self.config.refresh_token:
                    # Token might have expired early or been revoked; attempt refresh once
                    print("Received 401. Attempting manual token refresh and retry...")
                    await self.refresh_token()
                    headers["Authorization"] = f"Bearer {self.config.access_token}"
                    async with session.request(method, url, headers=headers, params=request_params, json=json_data) as retry_resp:
                        if retry_resp.status >= 400:
                            err_text = await retry_resp.text()
                            raise Exception(f"API request failed with status {retry_resp.status}: {err_text}")
                        return await retry_resp.json()
                
                if resp.status == 429:
                    print("Received 429 Too Many Requests from Tidal. Backing off 2s and retrying...")
                    await asyncio.sleep(2.0)
                    async with session.request(method, url, headers=headers, params=request_params, json=json_data) as retry_resp:
                        if retry_resp.status >= 400:
                            err_text = await retry_resp.text()
                            raise Exception(f"Rate limited by Tidal (429): {err_text}")
                        return await retry_resp.json()
                
                if resp.status >= 400:
                    err_text = await resp.text()
                    raise Exception(f"API request failed with status {resp.status}: {err_text}")
                
                return await resp.json()
        except Exception as e:
            raise Exception(f"Network error requesting {url}: {e}")

    # --- PKCE Authorization Code Flow (primary login method) ---
    # This is the only flow that grants proper r_usr/w_usr/w_sub scopes.

    def get_pkce_login_url(self):
        """Generates the PKCE authorization URL and stores verifier for later exchange."""
        code_verifier = base64.urlsafe_b64encode(os.urandom(32))[:-1].decode("utf-8")
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode("utf-8")).digest()
        )[:-1].decode("utf-8")
        client_unique_key = format(random.getrandbits(64), "02x")

        # Store verifier and key on instance for use during code exchange
        self._pkce_code_verifier = code_verifier
        self._pkce_client_unique_key = client_unique_key

        params = {
            "client_id": self.config.pkce_client_id,
            "redirect_uri": self.config.pkce_redirect_uri,
            "response_type": "code",
            "scope": "r_usr w_usr w_sub",
            "code_challenge_method": "S256",
            "code_challenge": code_challenge,
            "client_unique_key": client_unique_key,
            "appMode": "android",
            "restrict_signup": "true",
        }
        return "https://login.tidal.com/authorize?" + urllib.parse.urlencode(params)

    async def exchange_pkce_code(self, auth_code):
        """Exchanges the PKCE authorization code for tokens. Returns True on success."""
        session = await self.get_session()
        url = f"{self.AUTH_URL}/token"

        # No Basic Auth — PKCE is a public client flow.
        # Must include scope and client_unique_key to match the original auth request.
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        data = {
            "code": auth_code,
            "client_id": self.config.pkce_client_id,
            "grant_type": "authorization_code",
            "redirect_uri": self.config.pkce_redirect_uri,
            "scope": "r_usr+w_usr+w_sub",
            "code_verifier": self._pkce_code_verifier,
            "client_unique_key": self._pkce_client_unique_key,
        }

        async with session.post(url, data=data, headers=headers) as resp:
            try:
                resp_json = await resp.json(content_type=None)
            except Exception:
                err_text = await resp.text()
                raise Exception(f"Unexpected token response ({resp.status}): {err_text[:200]}")

            if resp.status == 200:
                self.config.access_token = resp_json["access_token"]
                self.config.refresh_token = resp_json.get("refresh_token", "")
                self.config.token_expiry = time.time() + float(resp_json.get("expires_in", 604800))
                await self.fetch_session_info()
                self.config.save()
                return True
            else:
                raise Exception(f"Token exchange failed: {resp_json.get('error_description', resp_json)}")


    async def refresh_token(self):
        """Refreshes the Access Token using the stored Refresh Token."""
        session = await self.get_session()
        url = f"{self.AUTH_URL}/token"

        auth_b64 = base64.b64encode(
            f"{self.config.pkce_client_id}:{self.config.pkce_client_secret}".encode()
        ).decode()
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {auth_b64}"
        }
        body = (
            f"client_id={self.config.pkce_client_id}"
            f"&grant_type=refresh_token"
            f"&refresh_token={self.config.refresh_token}"
        )

        async with session.post(url, data=body, headers=headers) as resp:
            try:
                resp_json = await resp.json(content_type=None)
            except Exception:
                err_text = await resp.text()
                self.config.clear_session()
                raise Exception(f"Unexpected response refreshing token ({resp.status}): {err_text[:200]}")
            if resp.status == 200:
                self.config.access_token = resp_json["access_token"]
                self.config.refresh_token = resp_json.get("refresh_token", self.config.refresh_token)
                self.config.token_expiry = time.time() + float(resp_json["expires_in"])
                self.config.save()
                await self.fetch_session_info()
                return True
            else:
                self.config.clear_session()
                raise Exception(f"Failed to refresh token: {resp_json.get('error_description', 'Unknown error')}")

    def _decode_token_payload(self):
        """Decodes the JWT access token payload without verification."""
        try:
            token = self.config.access_token
            if not token:
                return {}
            parts = token.split(".")
            if len(parts) != 3:
                return {}
            payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
            payload_bytes = base64.urlsafe_b64decode(payload_b64)
            return json.loads(payload_bytes.decode("utf-8"))
        except Exception as e:
            print(f"Failed to decode token payload: {e}")
            return {}

    async def fetch_session_info(self):
        """Extracts country code and user ID directly from the JWT token payload."""
        payload = self._decode_token_payload()
        cc = payload.get("cc")
        if cc:
            self.country_code = cc
        uid = payload.get("uid")
        if uid:
            self.config.user_id = str(uid)
        # user_name will be set from the token exchange response or stays blank

    # --- Search & Metadata Methods ---

    async def search(self, query, limit=30, offset=0, types=None):
        """Searches Tidal catalog for tracks, albums, playlists, and artists."""
        if not types:
            types = "TRACKS,ALBUMS,PLAYLISTS,ARTISTS"
        params = {
            "query": query,
            "limit": limit,
            "offset": offset,
            "types": types
        }
        return await self._api_request("GET", "search", params=params)

    async def smart_search(self, query, search_type="tracks", limit=30):
        """Intelligent search that optimizes category filtering, handles diacritics/accents, permutation fallbacks, and cross-category recovery."""
        type_map = {
            "tracks": "TRACKS",
            "albums": "ALBUMS",
            "playlists": "PLAYLISTS",
            "artists": "ARTISTS"
        }
        clean_st = search_type.lower()
        target_type = type_map.get(clean_st, "TRACKS,ALBUMS,PLAYLISTS,ARTISTS")
        clean_q = query.strip()
        
        # 1. Primary search with direct user query
        try:
            res = await self.search(clean_q, limit=limit, types=target_type)
            if clean_st in res and len(res[clean_st].get("items", [])) > 0:
                return res
        except Exception:
            res = {}

        # Helpers
        def strip_accents(text):
            return "".join(
                c for c in unicodedata.normalize("NFD", text)
                if unicodedata.category(c) != "Mn"
            )

        def clean_text(q):
            t = re.sub(r'[\(\[][^\)\]]*(?:feat|ft|remaster|radio|edit|version|mix|official|video|audio|deluxe|bonus|live)[^\)\]]*[\)\]]', '', q, flags=re.I)
            t = re.sub(r'\b(?:feat\.?|ft\.?)\s+[^\-]+', '', t, flags=re.I)
            t = re.sub(r'[^\w\s\-\'\,\.]', ' ', t)
            t = re.sub(r'\s+', ' ', t).strip()
            return t

        # Generate candidates in priority order
        candidates = []
        
        # A. Diacritics/Accents normalized version (e.g. "Björk" <-> "Bjork", "Rosalía" <-> "Rosalia")
        unaccented = strip_accents(clean_q)
        if unaccented.lower() != clean_q.lower():
            candidates.append(unaccented)

        # B. Cleaned text without noise/brackets
        cleaned = clean_text(clean_q)
        if cleaned and cleaned.lower() not in [clean_q.lower(), unaccented.lower()]:
            candidates.append(cleaned)
            cleaned_unaccented = strip_accents(cleaned)
            if cleaned_unaccented.lower() not in [c.lower() for c in candidates]:
                candidates.append(cleaned_unaccented)

        # C. Sub-phrase permutations: handle "Artist - Title" vs "Title Artist"
        for base in [clean_q, cleaned] if cleaned != clean_q else [clean_q]:
            if " - " in base:
                left, right = [p.strip() for p in base.split(" - ", 1)]
                candidates.append(f"{left} {right}")
                candidates.append(f"{right} {left}")
                candidates.append(right)
                candidates.append(left)
            elif " by " in base.lower():
                m = re.split(r"\s+by\s+", base, flags=re.I, maxsplit=1)
                if len(m) == 2:
                    t_part, a_part = m[0].strip(), m[1].strip()
                    candidates.append(f"{a_part} {t_part}")
                    candidates.append(f"{t_part} {a_part}")
                    candidates.append(t_part)

        # Try candidates in sequence
        seen_cand = {clean_q.lower()}
        for cand in candidates:
            if not cand or cand.lower() in seen_cand:
                continue
            seen_cand.add(cand.lower())
            try:
                cand_res = await self.search(cand, limit=limit, types=target_type)
                if clean_st in cand_res and len(cand_res[clean_st].get("items", [])) > 0:
                    return cand_res
            except Exception:
                pass

        # 3. Broad multi-category fallback
        try:
            broad_query = cleaned or unaccented or clean_q
            broad_res = await self.search(broad_query, limit=limit, types="TRACKS,ALBUMS,PLAYLISTS,ARTISTS")
            if clean_st in broad_res and len(broad_res[clean_st].get("items", [])) > 0:
                return broad_res

            # 4. Cross-category recovery:
            # If user wanted albums but 0 albums found, extract albums from matching tracks
            if clean_st == "albums" and "tracks" in broad_res and len(broad_res["tracks"].get("items", [])) > 0:
                seen_album_ids = set()
                recovered_albums = []
                for trk in broad_res["tracks"]["items"]:
                    alb = trk.get("album")
                    if alb and alb.get("id") and alb["id"] not in seen_album_ids:
                        seen_album_ids.add(alb["id"])
                        recovered_albums.append(alb)
                if recovered_albums:
                    return {"albums": {"items": recovered_albums, "totalNumberOfItems": len(recovered_albums)}}

            # If user wanted tracks and 0 found, but any other category matched, return broad
            if any(len(broad_res.get(k, {}).get("items", [])) > 0 for k in ["tracks", "albums", "playlists", "artists"]):
                return broad_res
        except Exception:
            pass

        return res

    async def get_track(self, track_id):
        """Gets metadata for a specific track."""
        return await self._api_request("GET", f"tracks/{track_id}")

    async def get_track_lyrics(self, track_id):
        """Gets lyrics for a specific track. Returns None if not found."""
        try:
            return await self._api_request("GET", f"tracks/{track_id}/lyrics")
        except Exception:
            return None

    async def get_album(self, album_id):
        """Gets metadata for a specific album."""
        return await self._api_request("GET", f"albums/{album_id}")

    async def get_album_tracks(self, album_id):
        """Gets all tracks on an album with automatic pagination support."""
        tracks = []
        limit = 100
        offset = 0
        while True:
            resp = await self._api_request("GET", f"albums/{album_id}/tracks", params={"limit": limit, "offset": offset})
            items = resp.get("items", [])
            tracks.extend(items)
            if len(items) < limit:
                break
            offset += limit
        return {"items": tracks}

    async def get_playlist(self, playlist_id):
        """Gets metadata for a specific playlist."""
        return await self._api_request("GET", f"playlists/{playlist_id}")

    async def get_playlist_tracks(self, playlist_id):
        """Gets all tracks in a playlist."""
        # Handles pagination automatically if items exceed 100
        tracks = []
        limit = 100
        offset = 0
        while True:
            resp = await self._api_request("GET", f"playlists/{playlist_id}/tracks", params={"limit": limit, "offset": offset})
            items = resp.get("items", [])
            tracks.extend(items)
            if len(items) < limit:
                break
            offset += limit
        return tracks

    async def get_artist(self, artist_id):
        """Gets metadata for a specific artist."""
        return await self._api_request("GET", f"artists/{artist_id}")

    async def get_artist_albums(self, artist_id):
        """Gets all albums and singles/EPs for a specific artist."""
        # Handles pagination for artist albums
        albums = []
        limit = 100
        offset = 0
        while True:
            resp = await self._api_request("GET", f"artists/{artist_id}/albums", params={"limit": limit, "offset": offset})
            items = resp.get("items", [])
            albums.extend(items)
            if len(items) < limit:
                break
            offset += limit
        return {"items": albums}

    # --- Stream manifest parser ---

    async def get_stream_info(self, track_id, quality):
        """Fetches and decodes the stream manifest for a track at target quality."""
        params = {
            "playbackmode": "STREAM",
            "assetpresentation": "FULL",
            "audioquality": quality
        }
        
        resp = await self._api_request("GET", f"tracks/{track_id}/playbackinfopostpaywall", params=params)
        
        mime_type = resp.get("manifestMimeType")
        encoded_manifest = resp.get("manifest")
        
        if not encoded_manifest:
            raise Exception("No manifest found in playback info response")
            
        decoded_bytes = base64.b64decode(encoded_manifest)
        
        if mime_type == "application/vnd.tidal.bts":
            # JSON manifest containing direct URL
            manifest_json = json.loads(decoded_bytes.decode("utf-8"))
            urls = manifest_json.get("urls", [])
            if not urls:
                raise Exception("No stream URLs found in BTS manifest")
            
            # True quality codec detection
            codec = manifest_json.get("codecs", "flac")
            ext = "flac" if "flac" in codec.lower() else "m4a"
            
            return {
                "type": "direct",
                "url": urls[0],
                "extension": ext,
                "bitrate": manifest_json.get("bitrate"),
                "bit_depth": resp.get("bitDepth"),
                "sample_rate": resp.get("sampleRate"),
                "audio_quality": resp.get("audioQuality"),
                "audio_mode": resp.get("audioMode", "STEREO")
            }
            
        elif mime_type == "application/dash+xml":
            # MPEG-DASH XML manifest containing fragmented URLs
            xml_str = decoded_bytes.decode("utf-8")
            dash_info = self._parse_dash_manifest(xml_str)
            
            # Codec detection from manifest XML
            ext = "flac"
            codec = dash_info.get("codec", "").lower()
            if "mp4a" in codec or "aac" in codec:
                ext = "m4a"
            elif "ec-3" in codec or "ac-4" in codec:
                if not getattr(self.config, "allow_dolby_atmos", False):
                    preferred = getattr(self.config, "quality_tier", "HI_RES_LOSSLESS")
                    # Fallback to the highest tier besides Atmos (HI_RES_LOSSLESS -> LOSSLESS)
                    fallback_tier = "HI_RES_LOSSLESS" if preferred == "HI_RES_LOSSLESS" else "LOSSLESS"
                    print(f"Dolby Atmos ({codec}) detected but disallowed by settings. Falling back to top stereo tier ({fallback_tier}).")
                    try:
                        return await self.get_stream_info(track_id, fallback_tier)
                    except Exception:
                        return await self.get_stream_info(track_id, "LOSSLESS")
                ext = "m4a"
                
            return {
                "type": "dash",
                "init_url": dash_info["init_url"],
                "segment_urls": dash_info["urls"],
                "extension": ext,
                "bit_depth": resp.get("bitDepth"),
                "sample_rate": resp.get("sampleRate"),
                "audio_quality": resp.get("audioQuality"),
                "audio_mode": resp.get("audioMode", "STEREO")
            }
        else:
            raise Exception(f"Unsupported manifest MIME type: {mime_type}")

    async def get_track_specs(self, track_id, quality=None):
        """Fetches accurate stream resolution specs (bitDepth, sampleRate, audioQuality, audioMode)."""
        if quality is None:
            quality = getattr(self.config, "quality_tier", "HI_RES_LOSSLESS")
        params = {
            "playbackmode": "STREAM",
            "assetpresentation": "FULL",
            "audioquality": quality
        }
        try:
            resp = await self._api_request("GET", f"tracks/{track_id}/playbackinfopostpaywall", params=params)
            bit_depth = resp.get("bitDepth")
            sample_rate = resp.get("sampleRate")
            audio_quality = resp.get("audioQuality", "")
            audio_mode = resp.get("audioMode", "STEREO")
            return {
                "bit_depth": bit_depth,
                "sample_rate": sample_rate,
                "audio_quality": audio_quality,
                "audio_mode": audio_mode
            }
        except Exception:
            return None

    def _parse_dash_manifest(self, xml_content):
        """Parses MPEG-DASH XML content to extract initialization and segment URLs."""
        root = ET.fromstring(xml_content)
        
        # Parse potential XML namespaces
        ns = ""
        if root.tag.startswith("{"):
            ns = root.tag.split("}")[0] + "}"
            
        # Parse BaseURLs (root and nested levels)
        base_urls = [bu.text for bu in root.findall(f".//{ns}BaseURL")]
        base_url = "".join(base_urls) if base_urls else ""
        
        rep = root.find(f".//{ns}Representation")
        codec = rep.attrib.get("codecs", "").lower() if rep is not None else ""
        
        template = root.find(f".//{ns}SegmentTemplate")
        if template is None:
            if base_url:
                # Return single file DASH stream
                return {"init_url": None, "urls": [base_url], "codec": codec}
            raise Exception("No SegmentTemplate or BaseURL found in DASH manifest")
            
        init_pattern = template.attrib.get("initialization", "")
        media_pattern = template.attrib.get("media", "")
        start_number = int(template.attrib.get("startNumber", "1"))
        
        init_url = urllib.parse.urljoin(base_url, init_pattern)
        
        # Read the segment timeline
        timeline = template.find(f"{ns}SegmentTimeline")
        segments = []
        if timeline is not None:
            curr_num = start_number
            for s in timeline.findall(f"{ns}S"):
                r = int(s.attrib.get("r", "0"))
                # S element might be repeated
                repeat = r + 1 if r >= 0 else 1
                for _ in range(repeat):
                    segments.append(curr_num)
                    curr_num += 1
        else:
            raise Exception("SegmentTimeline not found inside DASH manifest SegmentTemplate")
            
        segment_urls = []
        for num in segments:
            seg_file = media_pattern.replace("$Number$", str(num))
            segment_urls.append(urllib.parse.urljoin(base_url, seg_file))
            
        return {
            "init_url": init_url,
            "urls": segment_urls,
            "codec": codec
        }
