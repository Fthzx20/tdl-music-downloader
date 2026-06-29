# Tdl-music-downloader 🌊

A sleek, modern, and open-source HiFi music downloader. Built with Python and CustomTkinter, this application allows you to easily search for your favorite tracks, albums, and playlists, and download them in true lossless CD quality (FLAC) or AAC directly from the streaming service's servers.

## ✨ Features

- **True Lossless & Hi-Res Audio**: Downloads bit-perfect 16-bit/44.1kHz FLAC streams, and fully supports downloading **24-bit/192kHz Studio Masters** directly from the source.
- **Synchronized Lyrics (.lrc)**: Automatically downloads exact millisecond-synced lyrics and saves them as standard `.lrc` files next to your music for karaoke-style playback in modern media players.
- **Concurrent & Prioritized Queue**: Downloads up to 3 tracks simultaneously to maximize bandwidth. Control individual tracks with Pause/Cancel buttons, or bump important songs to the absolute front of the line with the "Move to Top" (⬆) button.
- **Session Memory**: Never lose a massive queue again. The app automatically saves your pending downloads to memory when closed, and instantly restores them the next time you open the app!
- **Asynchronous Engine**: Built with a true non-blocking asynchronous architecture. Heavy FFmpeg extraction and metadata tagging run in isolated background threads, guaranteeing that your concurrent downloads never stutter or freeze.
- **Smart Skip**: Instantly detects if a song already exists in your folder and skips it, saving you massive amounts of time and bandwidth when updating playlists.
- **Auto-Retry & Network Recovery**: If your internet drops mid-download, the app intelligently reconnects and uses HTTP `Range` headers to resume downloading exactly where it cut out.
- **Smart Remuxing**: Automatically extracts raw `.flac` streams from DASH `.mp4` containers using FFmpeg without losing quality.
- **Auto-Tagging**: Automatically applies rich metadata tags (Title, Artist, Album, Track Number) and embedded high-resolution album cover art.
- **Secure Authentication**: Uses modern PKCE Device OAuth flow for secure, effortless login via your web browser without requiring developer API keys or token scraping.
- **Modern UI**: A beautiful, dark-themed graphical user interface built with CustomTkinter featuring real-time, smoothed download speed metrics.

## 🛠️ Prerequisites

Before installing, ensure you have the following on your system:
- **Python 3.8 or higher**
- An active **Premium/HiFi Account** (High-tier subscription required for 16-bit and 24-bit Hi-Res FLAC downloads).

*(Note: FFmpeg is automatically downloaded and managed by the app via `imageio-ffmpeg`, so you do not need to install it manually!)*

## 🚀 Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/yourusername/Tdl-music-downloader.git
   cd Tdl-music-downloader
   ```

2. **Create a virtual environment (optional but recommended):**
   ```bash
   python -m venv venv
   # On Windows:
   venv\Scripts\activate
   # On macOS/Linux:
   source venv/bin/activate
   ```

3. **Install the dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

## 🎮 Usage

1. **Run the application:**
   ```bash
   python main.py
   ```
2. **Login:**
   - Click the **Login** button in the sidebar.
   - The app will display a 6-letter verification code and automatically open your web browser.
   - Enter the code on the official authorization page to securely link your account.

3. **Search & Download:**
   - Use the search bar to find tracks, albums, custom playlists, or artists.
   - Click **Download** to add items to your queue.
   - Switch to the **Queue Monitor** tab to watch download progress, pause individual songs, or bump songs to the top of the line.

4. **Enjoy:**
   - Your downloaded, fully-tagged `.flac` or `.m4a` files (along with their `.lrc` lyrics files) will be beautifully organized in your configured download directory!

## ⚙️ Configuration

You can configure the app's behavior by clicking the **Settings** tab (gear icon) in the sidebar:
- **Download Directory:** Choose where your music is saved.
- **Quality:** Select between LOW (96kbps), HIGH (320kbps), LOSSLESS (16-bit FLAC), or MAX (24-bit Hi-Res FLAC).

## ⚠️ Disclaimer

This tool is strictly for **personal use and educational purposes only**. 
Downloading copyrighted material without permission may violate Terms of Service and local copyright laws. The developers of this application do not encourage or condone music piracy. Please support the artists by subscribing to official streaming platforms or purchasing their music.

## 📄 License

This project is open-source and available under the [MIT License](LICENSE).
*(Note: This project relies on third-party libraries which may have their own licenses. Please review them accordingly.)*
