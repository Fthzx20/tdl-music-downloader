<div align="center">
  
# 🌊 Tdl-music-downloader
**The Ultimate Audiophile Music Downloader**

[![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-blue.svg?style=for-the-badge&logo=python)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-success.svg?style=for-the-badge)](LICENSE)
[![UI: CustomTkinter](https://img.shields.io/badge/UI-CustomTkinter-purple.svg?style=for-the-badge)](https://github.com/TomSchimansky/CustomTkinter)
[![Audio: Hi-Res FLAC](https://img.shields.io/badge/Audio-24--bit%20FLAC-ffb300.svg?style=for-the-badge)](https://en.wikipedia.org/wiki/FLAC)
[![Audio: Dolby Atmos](https://img.shields.io/badge/Audio-Dolby%20Atmos-9c27b0.svg?style=for-the-badge)](https://www.dolby.com/technologies/dolby-atmos/)

A sleek, lightning-fast, and open-source HiFi music downloader built for audiophiles who demand true, bit-perfect studio quality. Say goodbye to low-bitrate MP3s and hello to pristine **24-bit/192kHz Studio Masters**.

[Features](#-superpowers--features) • [External Link Support](#-multi-platform-link-search) • [Installation](#-installation) • [How to Use](#-how-to-use) • [Configuration](#-configuration)

</div>

---

## ⚡ Superpowers & Features

* 🎧 **True Hi-Res Studio Masters**: Bit-perfect extraction up to **24-bit/192kHz FLAC** directly from the source—no upscaling, no transcoding, pure studio sound.
* 🔗 **Multi-Platform Link Search**: Paste links directly from **Spotify**, **Apple Music**, **YouTube / YouTube Music**, **Deezer**, and **SoundCloud** to instantly find and download the exact track or album on Tidal!
* 🎵 **Dynamic Real Specs Badge**: Real-time color-coded badges that reflect true bit-depth and sample rates (`MAX • 24-bit/192kHz`, `MAX • 24-bit/96kHz`, `HiFi • 16-bit/44.1kHz`, etc.), 100% verified against acoustic spectrum analyzers like **Spek**.
* 🔊 **Dolby Atmos Toggle & Smart Fallback**: Toggle spatial Dolby Atmos on or off in Settings. When off, the engine automatically selects the **highest available stereo tier** (MAX 24-bit FLAC or HiFi 16-bit FLAC).
* ▶️ **Instant In-App Audio Preview**: Click the preview button (▶) on any search result to listen to a 30-second audio preview before downloading, powered by low-latency Windows native audio with race-condition protection.
* 🎤 **Karaoke-Ready Synchronized Lyrics**: Automatically extracts synced lyrics, saves standard `.lrc` files alongside your music, and embeds lyrics tags into the audio metadata (`UNSYNCEDLYRICS` for FLAC, `©lyr` for M4A).
* 📁 **Custom File Naming Templates**: Organize your library your way with customizable path templates (e.g. `{artist}/{album}/{track_num} - {title}.{ext}`).
* 🎚️ **Adjustable Concurrent Downloads**: Configure 1 to 3 simultaneous download slots with real-time UI control and async semaphore gating.
* ⏭️ **Smart Sync Skip**: Automatically checks your library before downloading and skips tracks that already exist, saving time and bandwidth.
* 🧑‍🎤 **Artist Discography Browser**: Click "View Albums" on any artist search result to instantly view and download their complete discography.
* 🛡️ **HTTP 429 Armor & Auto-Retry**: Built-in exponential backoff and connection retry safeguards your downloads against network drops and rate limits.
* 🧠 **Session Preservation**: Pending download queues are automatically remembered and restored if the application is closed.
* 🔐 **Secure OAuth PKCE Login**: No API keys or developer tokens needed. Authorize safely through your web browser using standard OAuth Device Flow.

---

## 🔗 Multi-Platform Link Search

Paste any streaming link directly into the search bar and press **Enter**:

| Platform | Supported Formats | Example |
| :--- | :--- | :--- |
| **Spotify** | Tracks, Albums, Playlists, Artists, URIs | `https://open.spotify.com/track/...` |
| **Apple Music** | Tracks (`?i=...`), Albums, Playlists, Artists | `https://music.apple.com/.../album/...` |
| **YouTube Music** | Tracks, Music Videos, Playlists | `https://music.youtube.com/watch?v=...` |
| **Deezer** | Tracks, Albums, Playlists, Artists | `https://www.deezer.com/track/...` |
| **SoundCloud** | Tracks, Songs | `https://soundcloud.com/...` |
| **Tidal** | Direct Track, Album, Playlist, Artist links & UUIDs | `https://tidal.com/browse/track/...` |

---

## 🛠️ Prerequisites

1. **Python 3.8 or higher**
2. An active **Tidal Account** *(HiFi/Max subscription required for lossless 16-bit & 24-bit FLAC streams)*.

*(FFmpeg is automatically handled via `imageio-ffmpeg`—no manual binary installation required!)*

---

## 🚀 Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/Fthzx20/tdl-music-downloader.git
   cd tdl-music-downloader
   ```

2. **Create a virtual environment (Recommended):**
   ```bash
   python -m venv venv
   
   # Windows:
   venv\Scripts\activate
   # macOS/Linux:
   source venv/bin/activate
   ```

3. **Install the dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

---

## 🎮 How to Use

1. **Launch the application:**
   ```bash
   python main.py
   ```

2. **Login:**
   - Click the **Login** button in the sidebar.
   - Enter the displayed verification code in the browser window that opens to link your account.

3. **Search & Download:**
   - Search by **Keywords**, **Tidal link**, or paste links from **Spotify / Apple Music / YouTube / Deezer**.
   - Click **▶** to preview any song.
   - Click **Download** to queue tracks, full albums, or playlists.

4. **Monitor Queue:**
   - Switch to the **Queue Monitor** tab to see real-time progress, retry failed downloads, bump tracks to top, or review exact downloaded specifications (e.g. `Completed (24-bit/176.4kHz FLAC)`).

---

## ⚙️ Configuration

Open the **Settings** tab in the sidebar to configure:

* 📁 **Download Directory:** Set where your music files are saved.
* 🎚️ **Preferred Quality Tier:** `Max (Hi-Res Lossless FLAC)`, `HiFi (16-bit FLAC)`, `High (320kbps AAC)`, or `Low (96kbps AAC)`.
* 🔊 **Allow Dolby Atmos:** Toggle spatial audio downloads on/off (Default: **OFF**, automatically falls back to MAX/HiFi stereo FLAC).
* 📝 **File Naming Template:** Customize file paths using `{artist}`, `{album}`, `{track_num}`, `{title}`, `{ext}` tags.
* ⚡ **Concurrent Downloads:** Slider to control simultaneous download threads (1 to 3).
* 🌐 **Login Browser:** Select your preferred browser for OAuth authorization.

---

## ⚠️ Disclaimer

This tool is strictly for **personal use and educational purposes only**. Downloading copyrighted material without permission may violate Terms of Service and local copyright laws. The developers do not encourage or condone music piracy. Please support artists by subscribing to official streaming services or purchasing their music.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
