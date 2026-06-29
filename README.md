<div align="center">
  
# 🌊 Tdl-music-downloader
**The Ultimate Audiophile Music Downloader**

[![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-blue.svg?style=for-the-badge&logo=python)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-success.svg?style=for-the-badge)](LICENSE)
[![UI: CustomTkinter](https://img.shields.io/badge/UI-CustomTkinter-purple.svg?style=for-the-badge)](https://github.com/TomSchimansky/CustomTkinter)
[![Audio: Hi-Res FLAC](https://img.shields.io/badge/Audio-24--bit%20FLAC-ff69b4.svg?style=for-the-badge)](https://en.wikipedia.org/wiki/FLAC)

A sleek, lightning-fast, and open-source HiFi music downloader built for people who actually care about audio quality. Say goodbye to low-bitrate MP3s and hello to pristine, bit-perfect **24-bit/192kHz Studio Masters**. 

[Features](#-superpowers--features) • [Installation](#-installation) • [Usage](#-how-to-use) • [Configuration](#-configuration) 

</div>

---

## ⚡ Superpowers & Features

We didn't just build a downloader; we built a beast. Here is what this app can do:

* 🎧 **True Hi-Res Studio Masters**: We don't upscale. The app grabs the bit-perfect 16-bit/44.1kHz FLAC streams, and even fully supports extracting the massive **24-bit/192kHz** studio masters directly from the source!
* 🎤 **Karaoke-Ready Lyrics**: It automatically fetches the exact, millisecond-synchronized lyrics and saves them as a standard `.lrc` file right next to your music. Drop it into your favorite media player and sing along!
* 🚀 **Multi-Threaded Asynchronous Engine**: The core engine is built on a non-blocking architecture. Heavy FFmpeg extraction and ID3 tagging run in invisible background threads, guaranteeing that your concurrent downloads *never* freeze or stutter.
* 🧠 **Session Memory**: Never lose a massive queue again. Accidentally closed the app with 200 songs pending? Don't panic. The app safely dumps your queue to memory and instantly resurrects it the next time you open the app.
* ⏭️ **Smart Skip**: Already downloaded half of a playlist yesterday? The app scans your folder and instantly skips tracks you already own, saving you massive amounts of bandwidth.
* 🛡️ **Auto-Retry & Network Armor**: If your Wi-Fi drops halfway through a massive 100MB track, the app uses HTTP `Range` headers to aggressively reconnect and resume the download exactly where it cut out.
* ⬆️ **Queue Prioritization**: Need a specific song *right now*? Click the green **⬆ Move to Top** button to instantly bump any queued song to the absolute front of the line!
* 🔐 **Secure PKCE Login**: No messing around with developer tokens, API keys, or sketchy scraping. Log in securely through your actual web browser using the modern OAuth Device flow.

---

## 🛠️ Prerequisites

You only need two things to get the party started:
1. **Python 3.8 or higher**
2. An active **Premium/HiFi Account** *(High-tier subscription required to unlock those sweet, sweet 16-bit and 24-bit FLAC streams).*

*(Don't worry about FFmpeg! The app automatically downloads and manages it for you in the background).*

---

## 🚀 Installation

It takes less than 60 seconds to get up and running:

1. **Clone the repository:**
   ```bash
   git clone https://github.com/yourusername/Tdl-music-downloader.git
   cd Tdl-music-downloader
   ```

2. **Create a virtual environment (Highly Recommended!):**
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

1. **Boot it up:**
   ```bash
   python main.py
   ```
2. **Secure Login:**
   - Click the **Login** button in the sidebar. 
   - A secure 6-letter code will pop up, and your browser will open. Just paste the code into the official authorization page to link your account securely.
3. **Search & Destroy:**
   - Search for your favorite Track, Album, Artist, or Custom Playlist.
   - Click **Download** and watch the magic happen.
4. **Take Control:**
   - Jump over to the **Queue Monitor** tab. From here you can pause individual songs, cancel them, or bump them to the top of the queue!
5. **Sit Back & Listen:**
   - Your `.flac` files (and their `.lrc` lyric files) will be beautifully organized and fully embedded with ID3 tags and high-res album art in your download folder.

---

## ⚙️ Configuration

Make it yours. Click the **Settings** gear in the sidebar to tweak:
* 📁 **Download Directory:** Tell the app exactly where to stash your FLACs.
* 🎚️ **Quality Tiers:** Choose your weapon: `Low (96kbps)`, `High (320kbps)`, `Lossless (16-bit FLAC)`, or `Max (24-bit Hi-Res FLAC)`.

---

## ⚠️ Disclaimer

This tool is strictly for **personal use and educational purposes only**. Downloading copyrighted material without permission may violate Terms of Service and local copyright laws. The developers of this application do not encourage or condone music piracy. Please support the artists by subscribing to official streaming platforms or purchasing their music.

## 📄 License

This project is open-source and proudly available under the [MIT License](LICENSE).
*(Note: This project relies on third-party libraries which may have their own licenses. Please review them accordingly.)*
