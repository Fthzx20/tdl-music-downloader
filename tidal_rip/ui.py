import os
import time
import asyncio
import threading
import webbrowser
import re
import customtkinter as CTk
from tkinter import filedialog, messagebox
from .downloader import DownloadManager

CTk.set_appearance_mode("dark")
CTk.set_default_color_theme("blue")

# Custom colors for Tidal theme
COLOR_ACCENT = "#00e5ff"       # Tidal Cyan
COLOR_ACCENT_HOVER = "#00b8d4" # Darker Cyan
COLOR_DARK_BG = "#121212"      # Black
COLOR_FRAME_BG = "#1e1e1e"     # Dark Grey
COLOR_TEXT_MUTED = "#aaaaaa"   # Light Grey

def register_browsers():
    import platform
    if platform.system() != "Windows":
        return
        
    import winreg
    
    browser_keys = {
        "chrome": ["chrome", "google-chrome", "google chrome"],
        "firefox": ["firefox", "mozilla firefox"],
        "edge": ["edge", "microsoft edge", "msedge"],
        "opera": ["opera", "opera beta", "opera stable"]
    }
    
    registered = set()
    
    # 1. Search in Windows Registry for installed browsers
    for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            key_path = r"SOFTWARE\Clients\StartMenuInternet"
            with winreg.OpenKey(root, key_path) as key:
                num_subkeys = winreg.QueryInfoKey(key)[0]
                for i in range(num_subkeys):
                    subkey_name = winreg.EnumKey(key, i)
                    try:
                        shell_path = f"{key_path}\\{subkey_name}\\shell\\open\\command"
                        with winreg.OpenKey(root, shell_path) as path_key:
                            val = winreg.QueryValue(path_key, None)
                            if val:
                                path = val.strip('"')
                                if path.lower().endswith(' %1'):
                                    path = path[:-3].strip('"')
                                if os.path.exists(path):
                                    sub_lower = subkey_name.lower()
                                    matched_key = None
                                    for k, aliases in browser_keys.items():
                                        if any(alias in sub_lower for alias in aliases):
                                            matched_key = k
                                            break
                                    
                                    if matched_key and matched_key not in registered:
                                        webbrowser.register(matched_key, None, webbrowser.BackgroundBrowser(path))
                                        registered.add(matched_key)
                    except Exception:
                        pass
        except Exception:
            pass

    # 2. Fallback to common hardcoded paths
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    program_files = os.environ.get("ProgramFiles", "C:\\Program Files")
    program_files_x86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
    
    common = {
        "chrome": [
            os.path.join(program_files, "Google\\Chrome\\Application\\chrome.exe"),
            os.path.join(program_files_x86, "Google\\Chrome\\Application\\chrome.exe"),
            os.path.join(local_app_data, "Google\\Chrome\\Application\\chrome.exe")
        ],
        "firefox": [
            os.path.join(program_files, "Mozilla Firefox\\firefox.exe"),
            os.path.join(program_files_x86, "Mozilla Firefox\\firefox.exe")
        ],
        "edge": [
            os.path.join(program_files_x86, "Microsoft\\Edge\\Application\\msedge.exe"),
            os.path.join(program_files, "Microsoft\\Edge\\Application\\msedge.exe")
        ],
        "opera": [
            os.path.join(local_app_data, "Programs\\Opera\\launcher.exe"),
            os.path.join(program_files, "Opera\\launcher.exe"),
            os.path.join(program_files_x86, "Opera\\launcher.exe")
        ]
    }
    
    for name, paths in common.items():
        if name in registered:
            continue
        for path in paths:
            if os.path.exists(path):
                try:
                    webbrowser.register(name, None, webbrowser.BackgroundBrowser(path))
                    registered.add(name)
                    break
                except Exception:
                    pass

# Run browser registration on load
register_browsers()

def open_browser(url, browser_name):
    if not browser_name or browser_name == "Default Browser":
        webbrowser.open(url)
        return
        
    mapping = {
        "Google Chrome": "chrome",
        "Mozilla Firefox": "firefox",
        "Microsoft Edge": "edge",
        "Safari": "safari",
        "Opera": "opera"
    }
    
    key = mapping.get(browser_name)
    if key:
        try:
            b = webbrowser.get(key)
            b.open(url)
        except Exception as e:
            print(f"Failed to open specific browser {browser_name}: {e}. Falling back to default.")
            webbrowser.open(url)
    else:
        webbrowser.open(url)

def parse_tidal_url(query):
    """Parses track, album, playlist, or artist/singer links from Tidal, including raw playlist UUIDs."""
    query = query.strip()
    
    # Check for raw UUID (custom user playlist ID)
    uuid_pattern = r"^([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})$"
    uuid_match = re.search(uuid_pattern, query)
    if uuid_match:
        return "playlist", uuid_match.group(1)
        
    patterns = {
        "track": r"tidal\.com/(?:[a-z]+/)?(?:browse/)?track/(\d+)",
        "album": r"tidal\.com/(?:[a-z]+/)?(?:browse/)?album/(\d+)",
        "playlist": r"tidal\.com/(?:[a-z]+/)?(?:browse/)?playlist/([a-zA-Z0-9-]+)",
        "artist": r"tidal\.com/(?:[a-z]+/)?(?:browse/)?artist/(\d+)"
    }
    for item_type, pattern in patterns.items():
        match = re.search(pattern, query)
        if match:
            return item_type, match.group(1)
    return None, None

class LoginModal(CTk.CTkToplevel):
    """Modal dialog displaying the OAuth device verification link and code."""
    
    def __init__(self, parent, verification_uri, user_code):
        super().__init__(parent)
        self.title("Tidal Login Verification")
        self.geometry("450x300")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        
        # Center window
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")
        
        self.configure(fg_color=COLOR_DARK_BG)
        
        title_label = CTk.CTkLabel(self, text="TIDAL DEVICE LOGIN", font=CTk.CTkFont(size=18, weight="bold"), text_color=COLOR_ACCENT)
        title_label.pack(pady=(20, 10))
        
        instr_label = CTk.CTkLabel(
            self, 
            text="Please open the link below and enter the verification code on Tidal:",
            font=CTk.CTkFont(size=12),
            wraplength=400
        )
        instr_label.pack(pady=10)
        
        # Code Display Box
        code_frame = CTk.CTkFrame(self, fg_color=COLOR_FRAME_BG, border_color=COLOR_ACCENT, border_width=1)
        code_frame.pack(pady=10, padx=20, fill="x")
        
        self.code_label = CTk.CTkLabel(code_frame, text=user_code, font=CTk.CTkFont(size=28, weight="bold", family="Courier"))
        self.code_label.pack(pady=10)
        
        # Buttons
        btn_frame = CTk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=20)
        
        copy_btn = CTk.CTkButton(
            btn_frame, 
            text="Copy Code", 
            fg_color=COLOR_FRAME_BG, 
            hover_color="#333333", 
            text_color="white",
            border_color=COLOR_ACCENT,
            border_width=1,
            width=120,
            command=lambda: self.copy_code(user_code)
        )
        copy_btn.pack(side="left", padx=10)
        
        open_btn = CTk.CTkButton(
            btn_frame, 
            text="Open Link", 
            fg_color=COLOR_ACCENT, 
            hover_color=COLOR_ACCENT_HOVER, 
            text_color="black",
            width=120,
            command=lambda: self.open_link(verification_uri)
        )
        open_btn.pack(side="left", padx=10)
        
        self.status_label = CTk.CTkLabel(self, text="Waiting for authorization...", text_color=COLOR_TEXT_MUTED, font=CTk.CTkFont(size=11, slant="italic"))
        self.status_label.pack(pady=(0, 10))

    def copy_code(self, code):
        self.clipboard_clear()
        self.clipboard_append(code)
        self.status_label.configure(text="Code copied to clipboard!", text_color=COLOR_ACCENT)

    def open_link(self, url):
        browser_name = self.master.config.login_browser
        open_browser(url, browser_name)
        self.status_label.configure(text="Link opened in browser!", text_color=COLOR_ACCENT)


class AppUI(CTk.CTk):
    """Main Application UI class running CustomTkinter."""
    
    def __init__(self, api, config, async_loop):
        super().__init__()
        self.api = api
        self.config = config
        self.async_loop = async_loop
        self.downloader = DownloadManager(self.api, self.config)
        
        self.title("Tidal Rip - HiFi Downloader")
        self.geometry("950x600")
        self.minsize(800, 500)
        self.configure(fg_color=COLOR_DARK_BG)
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # State variables
        self.search_results = []
        self.queue_items = {} # track_id -> UI elements and stats
        self.queue_order = []
        self.pending_downloads = []
        
        # Create Layout
        self.setup_layout()
        
        # Start 3 background worker tasks
        for _ in range(3):
            self.run_async(self.download_worker())
        
        # Check login status
        self.check_login_status()

    def on_closing(self):
        """Handle application close event to cancel downloads."""
        self.downloader.is_cancelled = True
        self.destroy()

    def run_async(self, coro):
        """Helper to run a coroutine safely in the background event loop."""
        return asyncio.run_coroutine_threadsafe(coro, self.async_loop)

    def check_login_status(self):
        """Verifies session token on load."""
        if self.config.access_token:
            # Check if token needs refresh
            if self.config.token_expiry - time.time() < 3600:
                self.run_async(self.refresh_token_on_load())
            else:
                self.run_async(self.verify_session_on_load())
        else:
            self.update_login_display(False)

    async def verify_session_on_load(self):
        try:
            await self.api.fetch_session_info()
            self.after(0, self.update_login_display, True)
        except Exception as e:
            print(f"Session verification failed on startup: {e}")
            self.config.clear_session()
            self.after(0, self.update_login_display, False)

    async def refresh_token_on_load(self):
        try:
            await self.api.refresh_token()
            self.after(0, self.update_login_display, True)
        except Exception as e:
            print(f"Token refresh failed on startup: {e}")
            self.config.clear_session()
            self.after(0, self.update_login_display, False)

    def update_login_display(self, logged_in):
        """Updates login indicator in sidebar."""
        if logged_in:
            user = self.config.user_name or f"User {self.config.user_id}"
            self.login_status_lbl.configure(text=f"Logged In:\n{user}", text_color=COLOR_ACCENT)
            self.login_btn.configure(text="Logout", fg_color=COLOR_FRAME_BG, hover_color="#333333", text_color="white", border_color="#e53935", border_width=1)
        else:
            self.login_status_lbl.configure(text="Logged Out", text_color=COLOR_TEXT_MUTED)
            self.login_btn.configure(text="Login", fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER, text_color="black", border_width=0)

    def setup_layout(self):
        # Grid layout (1 row, 2 columns)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        
        # 1. Sidebar Navigation Panel
        sidebar = CTk.CTkFrame(self, width=200, corner_radius=0, fg_color=COLOR_FRAME_BG)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_rowconfigure(4, weight=1)
        
        logo = CTk.CTkLabel(sidebar, text="TIDAL RIP", font=CTk.CTkFont(size=22, weight="bold"), text_color=COLOR_ACCENT)
        logo.grid(row=0, column=0, padx=20, pady=(30, 20))
        
        # Nav buttons
        self.btn_search = CTk.CTkButton(sidebar, text="Search Catalog", fg_color=COLOR_DARK_BG, text_color="white", hover_color="#2a2a2a", height=40, anchor="w", command=lambda: self.switch_view("search"))
        self.btn_search.grid(row=1, column=0, padx=10, pady=5, sticky="ew")
        
        self.btn_queue = CTk.CTkButton(sidebar, text="Downloads Queue", fg_color="transparent", text_color=COLOR_TEXT_MUTED, hover_color="#2a2a2a", height=40, anchor="w", command=lambda: self.switch_view("queue"))
        self.btn_queue.grid(row=2, column=0, padx=10, pady=5, sticky="ew")
        
        self.btn_settings = CTk.CTkButton(sidebar, text="Settings", fg_color="transparent", text_color=COLOR_TEXT_MUTED, hover_color="#2a2a2a", height=40, anchor="w", command=lambda: self.switch_view("settings"))
        self.btn_settings.grid(row=3, column=0, padx=10, pady=5, sticky="ew")
        
        # Account Status Panel (Bottom Sidebar)
        acc_panel = CTk.CTkFrame(sidebar, fg_color="transparent")
        acc_panel.grid(row=5, column=0, padx=10, pady=20, sticky="ew")
        
        self.login_status_lbl = CTk.CTkLabel(acc_panel, text="Checking...", font=CTk.CTkFont(size=12), text_color=COLOR_TEXT_MUTED)
        self.login_status_lbl.pack(pady=5)
        
        self.login_btn = CTk.CTkButton(acc_panel, text="Login", fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER, text_color="black", command=self.handle_login_click)
        self.login_btn.pack(fill="x", padx=10, pady=5)
        
        # 2. Main Content Frame (Contains multiple views)
        self.main_container = CTk.CTkFrame(self, fg_color="transparent")
        self.main_container.grid(row=0, column=1, sticky="nsew", padx=15, pady=15)
        self.main_container.grid_rowconfigure(0, weight=1)
        self.main_container.grid_columnconfigure(0, weight=1)
        
        # Initialize views
        self.create_search_view()
        self.create_queue_view()
        self.create_settings_view()
        
        # Set default view
        self.switch_view("search")

    def switch_view(self, view_name):
        """Switches active subview in the container."""
        # Hide all
        self.search_view.grid_forget()
        self.queue_view.grid_forget()
        self.settings_view.grid_forget()
        
        # Reset button styles
        self.btn_search.configure(fg_color="transparent", text_color=COLOR_TEXT_MUTED)
        self.btn_queue.configure(fg_color="transparent", text_color=COLOR_TEXT_MUTED)
        self.btn_settings.configure(fg_color="transparent", text_color=COLOR_TEXT_MUTED)
        
        if view_name == "search":
            self.search_view.grid(row=0, column=0, sticky="nsew")
            self.btn_search.configure(fg_color=COLOR_FRAME_BG, text_color="white")
        elif view_name == "queue":
            self.queue_view.grid(row=0, column=0, sticky="nsew")
            self.btn_queue.configure(fg_color=COLOR_FRAME_BG, text_color="white")
        elif view_name == "settings":
            self.settings_view.grid(row=0, column=0, sticky="nsew")
            self.btn_settings.configure(fg_color=COLOR_FRAME_BG, text_color="white")

    # --- Login Flows (PKCE Authorization Code) ---

    def handle_login_click(self):
        if self.config.access_token:
            self.config.clear_session()
            self.update_login_display(False)
            messagebox.showinfo("Logged Out", "You have been logged out.")
        else:
            if hasattr(self, "login_in_progress") and self.login_in_progress:
                return
            self.start_pkce_login()

    def start_pkce_login(self):
        """Generates PKCE URL, opens browser, and shows redirect URL input dialog."""
        self.login_in_progress = True
        self.login_btn.configure(state="disabled", text="Logging in...")
        login_url = self.api.get_pkce_login_url()
        open_browser(login_url, self.config.login_browser)
        self.show_pkce_redirect_dialog()

    def show_pkce_redirect_dialog(self):
        """Shows a dialog where the user pastes the redirect URL after login."""
        dialog = CTk.CTkToplevel(self)
        dialog.title("Complete Login")
        dialog.geometry("580x290")
        dialog.resizable(False, False)
        dialog.configure(fg_color=COLOR_DARK_BG)
        dialog.grab_set()
        dialog.focus_force()

        CTk.CTkLabel(
            dialog,
            text="Log in with Tidal in your browser",
            font=CTk.CTkFont(size=16, weight="bold"),
        ).pack(pady=(22, 4))

        CTk.CTkLabel(
            dialog,
            text="After logging in, your browser will redirect to an error page.\nCopy the FULL URL from the browser address bar and paste it below.",
            font=CTk.CTkFont(size=12),
            text_color=COLOR_TEXT_MUTED,
            justify="center",
        ).pack(pady=(0, 14))

        url_entry = CTk.CTkEntry(
            dialog,
            placeholder_text="https://tidal.com/android/login/auth?code=...",
            height=42,
            font=CTk.CTkFont(size=12),
            width=530,
        )
        url_entry.pack(padx=20, pady=(0, 10))

        status_lbl = CTk.CTkLabel(dialog, text="", font=CTk.CTkFont(size=11), text_color=COLOR_ACCENT)
        status_lbl.pack()

        def on_submit():
            import urllib.parse as _up
            pasted = url_entry.get().strip()
            if "code=" not in pasted:
                status_lbl.configure(text="Invalid URL — must contain 'code='", text_color="#e53935")
                return
            parsed = _up.urlparse(pasted)
            qs = _up.parse_qs(parsed.query)
            auth_code = qs.get("code", [None])[0]
            if not auth_code:
                status_lbl.configure(text="Could not extract code from URL.", text_color="#e53935")
                return
            status_lbl.configure(text="Exchanging token...", text_color=COLOR_ACCENT)
            dialog.update()
            self.run_async(self.exchange_pkce_code(auth_code, dialog))

        CTk.CTkButton(
            dialog,
            text="Complete Login",
            fg_color=COLOR_ACCENT,
            hover_color=COLOR_ACCENT_HOVER,
            text_color="black",
            height=38,
            width=180,
            font=CTk.CTkFont(size=13, weight="bold"),
            command=on_submit,
        ).pack(pady=(10, 0))

    async def exchange_pkce_code(self, auth_code, dialog):
        try:
            await self.api.exchange_pkce_code(auth_code)
            self.after(0, self.login_success, dialog)
        except Exception as e:
            err_msg = str(e)
            self.after(0, lambda: self.login_fail(err_msg, dialog))

    def login_success(self, dialog=None):
        self.login_in_progress = False
        self.login_btn.configure(state="normal")
        if dialog and dialog.winfo_exists():
            dialog.destroy()
        self.update_login_display(True)
        messagebox.showinfo(
            "Login Success",
            f"Logged in successfully!\nUser ID: {self.config.user_id}\nCountry: {self.api.country_code}"
        )

    def login_fail(self, error, dialog=None):
        self.login_in_progress = False
        self.login_btn.configure(state="normal", text="Login")
        if dialog and dialog.winfo_exists():
            dialog.destroy()
        self.update_login_display(False)
        messagebox.showerror("Login Failed", f"Authorization failed:\n{error}")

    # --- Search View ---

    def create_search_view(self):
        self.search_view = CTk.CTkFrame(self.main_container, fg_color="transparent")
        self.search_view.grid_rowconfigure(1, weight=1)
        self.search_view.grid_columnconfigure(0, weight=1)
        
        # Search controls
        search_ctrl = CTk.CTkFrame(self.search_view, fg_color="transparent")
        search_ctrl.grid(row=0, column=0, sticky="ew", pady=(0, 15))
        search_ctrl.grid_columnconfigure(0, weight=1)
        
        self.search_entry = CTk.CTkEntry(search_ctrl, placeholder_text="Search terms, Tidal URL, or Playlist UUID...", height=40, font=CTk.CTkFont(size=14))
        self.search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.search_entry.bind("<Return>", lambda e: self.trigger_search())
        
        self.search_type_menu = CTk.CTkOptionMenu(
            search_ctrl,
            values=["Tracks", "Albums", "Playlists", "Artists"],
            width=110,
            height=40,
            fg_color=COLOR_FRAME_BG,
            button_color=COLOR_FRAME_BG,
            button_hover_color="#333333",
            dropdown_fg_color=COLOR_FRAME_BG
        )
        self.search_type_menu.grid(row=0, column=1, sticky="w", padx=(0, 10))
        
        search_btn = CTk.CTkButton(search_ctrl, text="Search", fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER, text_color="black", width=100, height=40, font=CTk.CTkFont(size=13, weight="bold"), command=self.trigger_search)
        search_btn.grid(row=0, column=2, sticky="e")
        
        # Results frame
        self.results_scroll = CTk.CTkScrollableFrame(self.search_view, fg_color=COLOR_FRAME_BG)
        self.results_scroll.grid(row=1, column=0, sticky="nsew")

    def trigger_search(self):
        query = self.search_entry.get().strip()
        if not query:
            return
            
        if not self.config.access_token:
            messagebox.showwarning("Login Required", "You must be logged in to search Tidal catalog.")
            return
            
        self.results_scroll.winfo_children()
        for child in self.results_scroll.winfo_children():
            child.destroy()
            
        # Loading indicator
        lbl = CTk.CTkLabel(self.results_scroll, text="Searching Tidal...", font=CTk.CTkFont(size=14, slant="italic"))
        lbl.pack(pady=40)
        
        search_type = self.search_type_menu.get().lower()
        self.run_async(self.perform_search(query, search_type))

    def trigger_artist_albums_search(self, artist_id):
        """Helper that populates search bar with the artist's URL to retrieve all their albums."""
        url = f"https://tidal.com/artist/{artist_id}"
        self.search_entry.delete(0, "end")
        self.search_entry.insert(0, url)
        self.search_type_menu.set("Albums")
        self.trigger_search()

    async def perform_search(self, query, search_type):
        # 1. Support direct URL link routing for quick fetching
        url_type, url_id = parse_tidal_url(query)
        if url_type:
            try:
                if url_type == "track":
                    track = await self.api.get_track(url_id)
                    results = {"tracks": {"items": [track]}}
                    self.after(0, self.populate_results, results, "tracks")
                elif url_type == "album":
                    album = await self.api.get_album(url_id)
                    results = {"albums": {"items": [album]}}
                    self.after(0, self.populate_results, results, "albums")
                elif url_type == "playlist":
                    playlist = await self.api.get_playlist(url_id)
                    results = {"playlists": {"items": [playlist]}}
                    self.after(0, self.populate_results, results, "playlists")
                elif url_type == "artist":
                    # Directly display the singer's catalog albums
                    albums_resp = await self.api.get_artist_albums(url_id)
                    self.after(0, self.populate_results, albums_resp, "albums")
            except Exception as e:
                err_msg = str(e)
                self.after(0, lambda: messagebox.showerror("Link Search Error", f"Failed to retrieve link metadata: {err_msg}"))
            return

        # 2. Standard string search query
        try:
            results = await self.api.search(query)
            self.after(0, self.populate_results, results, search_type)
        except Exception as e:
            err_msg = str(e)
            self.after(0, lambda: messagebox.showerror("Search Error", f"Search request failed: {err_msg}"))

    def populate_results(self, data, search_type):
        # Clear loading label
        for child in self.results_scroll.winfo_children():
            child.destroy()
            
        items = []
        if search_type == "tracks" and "tracks" in data:
            items = data["tracks"].get("items", [])
        elif search_type == "albums" and "albums" in data:
            items = data["albums"].get("items", [])
        elif search_type == "playlists" and "playlists" in data:
            items = data["playlists"].get("items", [])
        elif search_type == "artists" and "artists" in data:
            items = data["artists"].get("items", [])
            
        if not items:
            lbl = CTk.CTkLabel(self.results_scroll, text="No results found.", font=CTk.CTkFont(size=14))
            lbl.pack(pady=40)
            return
            
        for idx, item in enumerate(items):
            row = CTk.CTkFrame(self.results_scroll, fg_color="transparent", height=60)
            row.pack(fill="x", pady=5, padx=5)
            row.pack_propagate(False)
            
            # Text layout depending on category
            btn_text = "Download"
            if search_type == "tracks":
                title = item.get("title", "Unknown Title")
                artists = item.get("artists", [])
                artist = artists[0]["name"] if artists else "Unknown Artist"
                album_info = item.get("album", {})
                album = album_info.get("title", "Unknown Album")
                display_text = f"{title}\nBy {artist} — {album}"
                item_id = item["id"]
                action_func = lambda i=item_id, t=title: self.queue_track_download(i, t)
            elif search_type == "albums":
                title = item.get("title", "Unknown Title")
                artists = item.get("artists", [])
                artist = artists[0]["name"] if artists else "Unknown Artist"
                display_text = f"Album: {title}\nBy {artist}"
                item_id = item["id"]
                action_func = lambda i=item_id, t=title: self.queue_album_downloads(i, t)
            elif search_type == "playlists":
                title = item.get("title", "Unknown Title")
                display_text = f"Playlist: {title}\nTracks: {item.get('numberOfTracks', 'Unknown')}"
                item_id = item["uuid"]
                action_func = lambda i=item_id, t=title: self.queue_playlist_downloads(i, t)
            elif search_type == "artists":
                name = item["name"]
                display_text = f"Artist: {name}"
                item_id = item["id"]
                action_func = lambda i=item_id: self.trigger_artist_albums_search(i)
                btn_text = "View Albums"
                
            info_lbl = CTk.CTkLabel(row, text=display_text, font=CTk.CTkFont(size=12), anchor="w", justify="left")
            info_lbl.pack(side="left", fill="both", expand=True, padx=10)
            
            dl_btn = CTk.CTkButton(
                row, 
                text=btn_text, 
                fg_color=COLOR_ACCENT, 
                hover_color=COLOR_ACCENT_HOVER, 
                text_color="black",
                width=100, 
                font=CTk.CTkFont(size=11, weight="bold"),
                command=action_func
            )
            dl_btn.pack(side="right", padx=10, pady=15)
            
            # Divider
            divider = CTk.CTkFrame(self.results_scroll, fg_color="#333333", height=1)
            divider.pack(fill="x", padx=5)

    # --- Queue View ---

    def create_queue_view(self):
        self.queue_view = CTk.CTkFrame(self.main_container, fg_color="transparent")
        self.queue_view.grid_rowconfigure(1, weight=1)
        self.queue_view.grid_columnconfigure(0, weight=1)
        
        # Header
        header = CTk.CTkFrame(self.queue_view, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        
        title_lbl = CTk.CTkLabel(header, text="Download Progress Monitor", font=CTk.CTkFont(size=16, weight="bold"))
        title_lbl.pack(side="left")
        
        self.pause_btn = CTk.CTkButton(header, text="Pause", width=80, fg_color="#ff9800", hover_color="#f57c00", text_color="black", command=self.toggle_pause)
        self.pause_btn.pack(side="right", padx=5)
        
        cancel_btn = CTk.CTkButton(header, text="Cancel All", width=80, fg_color="#f44336", hover_color="#d32f2f", text_color="white", command=self.cancel_all_downloads)
        cancel_btn.pack(side="right", padx=5)
        
        clear_btn = CTk.CTkButton(header, text="Clear Finished", width=100, fg_color=COLOR_FRAME_BG, hover_color="#333333", text_color="white", border_color=COLOR_ACCENT, border_width=1, command=self.clear_finished_downloads)
        clear_btn.pack(side="right", padx=5)
        
        # Scroll area
        self.queue_scroll = CTk.CTkScrollableFrame(self.queue_view, fg_color=COLOR_FRAME_BG)
        self.queue_scroll.grid(row=1, column=0, sticky="nsew")

    def toggle_pause(self):
        if self.downloader.is_paused:
            self.downloader.is_paused = False
            self.pause_btn.configure(text="Pause")
        else:
            self.downloader.is_paused = True
            self.pause_btn.configure(text="Resume")
            
    def cancel_all_downloads(self):
        if messagebox.askyesno("Cancel Downloads", "Are you sure you want to cancel all downloads?"):
            self.downloader.is_cancelled = True
            
            # Clear queued items
            for tid in list(self.queue_order):
                if self.queue_items[tid]["status"] == "queued":
                    self.queue_items[tid]["status"] = "cancelled"
                    self.queue_items[tid]["status_lbl"].configure(text="Cancelled", text_color="#f44336")
                    self.queue_order.remove(tid)
                    
            # Reset flag after a short delay to allow current downloads to exit gracefully
            self.after(1500, self._reset_cancel_flag)
            
    def _reset_cancel_flag(self):
        self.downloader.is_cancelled = False
        
    def clear_finished_downloads(self):
        """Removes completed, failed, and cancelled items from the UI queue."""
        for tid in list(self.queue_items.keys()):
            status = self.queue_items[tid]["status"]
            if status in ["completed", "failed", "cancelled"]:
                # Destroy the UI row
                self.queue_items[tid]["row"].destroy()
                # Remove from tracking dictionaries
                del self.queue_items[tid]
                if tid in self.queue_order:
                    self.queue_order.remove(tid)

    def queue_track_download(self, track_id, title, parent_folder=None):
        if track_id in self.queue_items:
            messagebox.showinfo("Already Queued", f"'{title}' is already in the download queue.")
            return
            
        # UI representation
        row = CTk.CTkFrame(self.queue_scroll, fg_color="#252525", height=70)
        row.pack(fill="x", pady=5, padx=5)
        row.pack_propagate(False)
        
        lbl = CTk.CTkLabel(row, text=title, font=CTk.CTkFont(size=12, weight="bold"), anchor="w")
        lbl.pack(side="top", fill="x", padx=15, pady=(5, 0))
        
        progress_frame = CTk.CTkFrame(row, fg_color="transparent")
        progress_frame.pack(side="bottom", fill="x", padx=15, pady=(0, 10))
        
        progress_bar = CTk.CTkProgressBar(progress_frame, fg_color="#444444", progress_color=COLOR_ACCENT)
        progress_bar.pack(side="left", fill="x", expand=True, padx=(0, 15))
        progress_bar.set(0.0)
        
        ctrl_frame = CTk.CTkFrame(progress_frame, fg_color="transparent")
        ctrl_frame.pack(side="right")
        
        lbl_frame = CTk.CTkFrame(ctrl_frame, width=280, height=20, fg_color="transparent")
        lbl_frame.pack(side="left", padx=(0, 10))
        lbl_frame.pack_propagate(False)
        
        status_lbl = CTk.CTkLabel(lbl_frame, text="Queued", font=CTk.CTkFont(family="Consolas", size=11), text_color=COLOR_TEXT_MUTED, anchor="w")
        status_lbl.pack(side="left", fill="both", expand=True)
        
        pause_btn = CTk.CTkButton(ctrl_frame, text="⏸", width=25, height=20, fg_color="#ff9800", hover_color="#f57c00", text_color="black")
        pause_btn.pack(side="left", padx=2)
        
        cancel_btn = CTk.CTkButton(ctrl_frame, text="✖", width=25, height=20, fg_color="#f44336", hover_color="#d32f2f", text_color="white")
        cancel_btn.pack(side="left", padx=2)
        
        top_btn = CTk.CTkButton(ctrl_frame, text="⬆", width=25, height=20, fg_color="#4caf50", hover_color="#388e3c", text_color="white")
        top_btn.pack(side="left", padx=2)
        
        task_state = {"is_paused": False, "is_cancelled": False}
        
        def toggle_item_pause():
            if task_state["is_paused"]:
                task_state["is_paused"] = False
                pause_btn.configure(text="⏸")
            else:
                task_state["is_paused"] = True
                pause_btn.configure(text="▶")
                
        def cancel_item():
            task_state["is_cancelled"] = True
            if self.queue_items[track_id]["status"] == "queued":
                self.queue_items[track_id]["status"] = "cancelled"
                status_lbl.configure(text="Cancelled", text_color="#f44336")
                
        def move_item_to_top():
            if track_id in self.pending_downloads:
                self.pending_downloads.remove(track_id)
                self.pending_downloads.insert(0, track_id)
                
        pause_btn.configure(command=toggle_item_pause)
        cancel_btn.configure(command=cancel_item)
        top_btn.configure(command=move_item_to_top)
        
        self.queue_items[track_id] = {
            "row": row,
            "progress_bar": progress_bar,
            "status_lbl": status_lbl,
            "pause_btn": pause_btn,
            "title": title,
            "status": "queued",
            "parent_folder": parent_folder,
            "task_state": task_state
        }
        self.queue_order.append(track_id)
        self.pending_downloads.append(track_id)
            
        # Switch to Queue tab to see progress
        self.switch_view("queue")

    def queue_album_downloads(self, album_id, album_title):
        self.run_async(self.fetch_and_queue_album(album_id, album_title))

    async def fetch_and_queue_album(self, album_id, album_title):
        try:
            tracks_resp = await self.api.get_album_tracks(album_id)
            items = tracks_resp.get("items", [])
            if not items:
                raise Exception("No tracks found on this album.")
                
            self.after(0, lambda: messagebox.showinfo("Album Queued", f"Adding {len(items)} tracks from '{album_title}' to the download queue."))
            
            for item in items:
                track_id = item["id"]
                title = f"{item['title']} - {item['artist']['name']}"
                self.after(0, self.queue_track_download, track_id, title)
        except Exception as e:
            err_msg = str(e)
            self.after(0, lambda: messagebox.showerror("Album Error", f"Failed to download album tracks: {err_msg}"))

    def queue_playlist_downloads(self, playlist_id, playlist_title):
        self.run_async(self.fetch_and_queue_playlist(playlist_id, playlist_title))

    async def fetch_and_queue_playlist(self, playlist_id, playlist_title):
        try:
            items = await self.api.get_playlist_tracks(playlist_id)
            if not items:
                raise Exception("No tracks found in this playlist.")
                
            self.after(0, lambda: messagebox.showinfo("Playlist Queued", f"Adding {len(items)} tracks from playlist '{playlist_title}' to the download queue."))
            
            for item in items:
                # Playlist response might wrap tracks in a sub-field 'item' or return them flat
                track_info = item.get("item") if "item" in item else item
                
                if track_info and ("id" in track_info):
                    track_id = track_info["id"]
                    artists = track_info.get("artists", [])
                    artist_name = artists[0]["name"] if artists else track_info.get("artist", {}).get("name", "Unknown Artist")
                    title = f"{track_info.get('title', 'Unknown Title')} - {artist_name}"
                    self.after(0, self.queue_track_download, track_id, title, playlist_title)
        except Exception as e:
            err_msg = str(e)
            self.after(0, lambda: messagebox.showerror("Playlist Error", f"Failed to download playlist tracks: {err_msg}"))

    async def download_worker(self):
        """Continuously pulls from pending_downloads and processes them."""
        while not self.downloader.is_cancelled:
            if not self.pending_downloads:
                await asyncio.sleep(0.5)
                continue
                
            track_id = self.pending_downloads.pop(0)
            
            if self.queue_items[track_id]["status"] == "cancelled" or self.queue_items[track_id]["task_state"]["is_cancelled"]:
                continue
                
            await self.process_single_download(track_id)

    async def process_single_download(self, tid):
        """Processes a single download task."""
        self.queue_items[tid]["status"] = "downloading"
        
        def make_callback(tid):
            async def progress_update(downloaded, total, status_text):
                progress = float(downloaded) / max(1.0, float(total))
                # Safely schedule label and progress updates on UI thread
                self.after(0, lambda: self.queue_items[tid]["progress_bar"].set(progress))
                self.after(0, lambda: self.queue_items[tid]["status_lbl"].configure(text=status_text))
            return progress_update
            
        try:
            parent_folder = self.queue_items[tid].get("parent_folder")
            task_state = self.queue_items[tid].get("task_state")
            await self.downloader.download_track(tid, make_callback(tid), parent_folder, task_state)
            self.queue_items[tid]["status"] = "completed"
            self.after(0, lambda nid=tid: self.queue_items[nid]["progress_bar"].configure(progress_color="#4caf50")) # Green on success
            self.after(0, lambda nid=tid: self.queue_items[nid]["status_lbl"].configure(text="Completed"))
        except Exception as e:
            print(f"Download failed for track {tid}: {e}")
            self.queue_items[tid]["status"] = "failed"
            self.after(0, lambda nid=tid: self.queue_items[nid]["progress_bar"].configure(progress_color="#f44336")) # Red on error
            self.after(0, lambda nid=tid: self.queue_items[nid]["status_lbl"].configure(text="Failed", text_color="#f44336"))

    # --- Settings View ---

    def create_settings_view(self):
        self.settings_view = CTk.CTkFrame(self.main_container, fg_color="transparent")
        self.settings_view.grid_columnconfigure(0, weight=1)
        
        # Title
        title_lbl = CTk.CTkLabel(self.settings_view, text="System Configurations", font=CTk.CTkFont(size=18, weight="bold"), text_color=COLOR_ACCENT)
        title_lbl.pack(anchor="w", pady=(0, 20))
        
        # 1. Output Folder Location
        folder_lbl = CTk.CTkLabel(self.settings_view, text="Download Directory Location", font=CTk.CTkFont(size=13, weight="bold"))
        folder_lbl.pack(anchor="w", pady=(5, 5))
        
        folder_frame = CTk.CTkFrame(self.settings_view, fg_color="transparent")
        folder_frame.pack(fill="x", pady=(0, 15))
        folder_frame.grid_columnconfigure(0, weight=1)
        
        self.folder_entry = CTk.CTkEntry(folder_frame, height=35)
        self.folder_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.folder_entry.insert(0, self.config.download_directory)
        
        browse_btn = CTk.CTkButton(folder_frame, text="Browse", fg_color=COLOR_FRAME_BG, hover_color="#333333", border_color=COLOR_ACCENT, border_width=1, width=100, height=35, command=self.browse_directory)
        browse_btn.grid(row=0, column=1)
        
        # 2. Quality Tier Selection
        quality_lbl = CTk.CTkLabel(self.settings_view, text="Preferred Stream Quality Tier", font=CTk.CTkFont(size=13, weight="bold"))
        quality_lbl.pack(anchor="w", pady=(5, 5))
        
        # Mapping UI names to internal values
        self.quality_map = {
            "Max (Hi-Res Lossless FLAC)": "HI_RES_LOSSLESS",
            "HiFi (CD-Quality Lossless FLAC)": "LOSSLESS",
            "High (320kbps AAC)": "HIGH",
            "Low (96kbps AAC)": "LOW"
        }
        self.quality_reverse_map = {v: k for k, v in self.quality_map.items()}
        
        self.quality_menu = CTk.CTkOptionMenu(
            self.settings_view,
            values=list(self.quality_map.keys()),
            width=300,
            height=35,
            fg_color=COLOR_FRAME_BG,
            button_color=COLOR_FRAME_BG,
            button_hover_color="#333333",
            dropdown_fg_color=COLOR_FRAME_BG
        )
        self.quality_menu.pack(anchor="w", pady=(0, 20))
        
        current_quality_str = self.quality_reverse_map.get(self.config.quality_tier, "HiFi (CD-Quality Lossless FLAC)")
        self.quality_menu.set(current_quality_str)
        
        # Browser Selection
        browser_lbl = CTk.CTkLabel(self.settings_view, text="Login Browser Selection", font=CTk.CTkFont(size=13, weight="bold"))
        browser_lbl.pack(anchor="w", pady=(5, 5))
        
        self.browser_options = ["Default Browser", "Google Chrome", "Mozilla Firefox", "Microsoft Edge", "Safari", "Opera"]
        self.browser_menu = CTk.CTkOptionMenu(
            self.settings_view,
            values=self.browser_options,
            width=300,
            height=35,
            fg_color=COLOR_FRAME_BG,
            button_color=COLOR_FRAME_BG,
            button_hover_color="#333333",
            dropdown_fg_color=COLOR_FRAME_BG
        )
        self.browser_menu.pack(anchor="w", pady=(0, 20))
        self.browser_menu.set(self.config.login_browser)
        
        # 3. Custom API Keys
        key_lbl = CTk.CTkLabel(self.settings_view, text="Custom API Credentials Override (Advanced)", font=CTk.CTkFont(size=13, weight="bold"))
        key_lbl.pack(anchor="w", pady=(5, 5))
        
        self.client_id_entry = CTk.CTkEntry(self.settings_view, placeholder_text="Client ID", height=35)
        self.client_id_entry.pack(fill="x", pady=(0, 10))
        self.client_id_entry.insert(0, self.config.client_id)
        
        self.client_secret_entry = CTk.CTkEntry(self.settings_view, placeholder_text="Client Secret (Optional)", height=35)
        self.client_secret_entry.pack(fill="x", pady=(0, 25))
        self.client_secret_entry.insert(0, self.config.client_secret)
        
        # Action Buttons
        actions_frame = CTk.CTkFrame(self.settings_view, fg_color="transparent")
        actions_frame.pack(fill="x")
        
        save_btn = CTk.CTkButton(actions_frame, text="Save Settings", fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER, text_color="black", height=40, font=CTk.CTkFont(size=13, weight="bold"), command=self.save_settings)
        save_btn.pack(side="left", padx=(0, 15))
        
        reset_btn = CTk.CTkButton(actions_frame, text="Reset Keys to Default", fg_color=COLOR_FRAME_BG, hover_color="#333333", text_color="white", height=40, command=self.reset_keys)
        reset_btn.pack(side="left")

    def browse_directory(self):
        selected = filedialog.askdirectory(initialdir=self.folder_entry.get())
        if selected:
            self.folder_entry.delete(0, "end")
            self.folder_entry.insert(0, selected)

    def save_settings(self):
        new_dir = self.folder_entry.get().strip()
        new_quality = self.quality_map.get(self.quality_menu.get(), "LOSSLESS")
        new_browser = self.browser_menu.get()
        new_id = self.client_id_entry.get().strip()
        new_secret = self.client_secret_entry.get().strip()
        
        if not new_dir:
            messagebox.showerror("Error", "Download directory cannot be empty.")
            return
        if not new_id:
            messagebox.showerror("Error", "Client ID cannot be empty.")
            return
            
        # Update config properties
        self.config.download_directory = new_dir
        self.config.quality_tier = new_quality
        self.config.login_browser = new_browser
        
        # Check if keys changed
        keys_changed = (self.config.client_id != new_id or self.config.client_secret != new_secret)
        self.config.client_id = new_id
        self.config.client_secret = new_secret
        
        self.config.save()
        
        if keys_changed:
            self.config.clear_session()
            self.update_login_display(False)
            messagebox.showinfo("Settings Saved", "Settings successfully saved!\nSince API keys were updated, your active login session was cleared. Please log in again.")
        else:
            messagebox.showinfo("Settings Saved", "Settings successfully saved!")

    def reset_keys(self):
        self.client_id_entry.delete(0, "end")
        self.client_id_entry.insert(0, self.config.DEFAULT_CLIENT_ID)
        self.client_secret_entry.delete(0, "end")
        self.client_secret_entry.insert(0, self.config.DEFAULT_CLIENT_SECRET)
