# Tdl-music-downloader 🌊

A sleek, modern, and open-source HiFi music downloader. Built with Python and CustomTkinter, this application allows you to easily search for your favorite tracks, albums, and playlists, and download them in true lossless CD quality (FLAC) or AAC directly from the streaming service's servers.


## ✨ Features

- **True Lossless Downloads**: Downloads bit-perfect 16-bit/44.1kHz FLAC streams directly from the source (no upscaling or re-encoding).
- **Modern UI**: A beautiful, dark-themed graphical user interface built with CustomTkinter.
- **Queue Management**: Download multiple tracks, full albums, or entire playlists with background queueing. Includes Pause, Resume, Cancel All, and Clear Finished controls.
- **Smart Remuxing**: Automatically extracts raw `.flac` streams from DASH `.mp4` containers using FFmpeg without losing quality.
- **Auto-Tagging**: Automatically applies rich metadata tags (Title, Artist, Album, Track Number) and embedded high-resolution album cover art.
- **Secure Authentication**: Uses modern PKCE OAuth flow for secure login without requiring developer API keys.

## 🛠️ Prerequisites

Before installing, ensure you have the following on your system:
- **Python 3.8 or higher**
- An active **Premium/HiFi Account** (High-tier subscription recommended for lossless FLAC downloads).

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
   - Your web browser will open the official login page.
   - Log in with your account credentials.
   - You will be redirected to an error or blank page. **Copy the entire URL** from your browser's address bar.
   - Paste the URL into the prompt in the app to complete the login.

3. **Search & Download:**
   - Use the search bar to find tracks, albums, playlists, or artists.
   - Click **Download** to add items to your queue.
   - Switch to the **Queue Monitor** tab to watch download progress, pause, or cancel downloads.

4. **Enjoy:**
   - Your downloaded, fully-tagged `.flac` or `.m4a` files will be saved in your configured download directory.

## ⚙️ Configuration

You can configure the app's behavior by clicking the **Settings** tab (gear icon) in the sidebar:
- **Download Directory:** Choose where your music is saved.
- **Quality:** Select between LOW (96kbps), HIGH (320kbps), or LOSSLESS (FLAC).

## ⚠️ Disclaimer

This tool is strictly for **personal use and educational purposes only**. 
Downloading copyrighted material without permission may violate Terms of Service and local copyright laws. The developers of this application do not encourage or condone music piracy. Please support the artists by subscribing to official streaming platforms or purchasing their music.

## 📄 License

This project is open-source and available under the [MIT License](LICENSE).
*(Note: This project relies on third-party libraries which may have their own licenses. Please review them accordingly.)*
