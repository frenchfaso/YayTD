# Imports
import os
import ssl
import sys
import threading
import webbrowser
from dataclasses import dataclass
from datetime import timedelta
from importlib.metadata import PackageNotFoundError, version as metadata_version
from pathlib import Path
from tkinter import Menu, filedialog
import tkinter as tk
from tkinter import ttk
from urllib.parse import parse_qs, urlparse
from urllib.request import urlopen

import certifi
import darkdetect
from PIL import Image, ImageTk
import sv_ttk
from yt_dlp import YoutubeDL, version as ytdlp_version
from yt_dlp.utils import DownloadCancelled, sanitize_filename


@dataclass(frozen=True)
class DownloadStream:
    video_url: str
    format_id: str
    default_filename: str
    mime_type: str
    resolution: str
    fps: str
    abr: str
    filesize_mb: float | None
    has_audio: bool
    has_video: bool


class YayTDApp:
    REPOSITORY_URL = "https://github.com/frenchfaso/YayTD"
    APP_WIDTH = 800
    APP_HEIGHT = 700
    VIDEO_PREVIEW_WIDTH = 160
    VIDEO_PREVIEW_HEIGHT = 120
    THUMBNAIL_TIMEOUT = 10
    DOWNLOAD_TIMEOUT = 30
    DOWNLOAD_RETRIES = 2
    THEME_POLL_MS = 3000
    ACTIVE_DOWNLOAD_STATES = {"downloading", "cancelling"}

    LIGHT_PALETTE = {
        "background": "#f5f5f7",
        "panel": "#ffffff",
        "foreground": "#1d1d1f",
        "muted": "#4a4a4f",
        "link": "#0057d9",
    }
    DARK_PALETTE = {
        "background": "#1c1c1e",
        "panel": "#2c2c2e",
        "foreground": "#f5f5f7",
        "muted": "#c7c7cc",
        "link": "#64a8ff",
    }

    SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("YayTD")
        self.root.geometry(f"{self.APP_WIDTH}x{self.APP_HEIGHT}")
        self.root.minsize(self.APP_WIDTH, self.APP_HEIGHT)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.style = ttk.Style(self.root)
        self.theme_mode = None
        self.closing = False
        self.loading = False
        self.active_downloads = 0
        self.current_load_id = 0
        self.focus_autopaste_done = False

        self.streams_by_id = {}
        self.stream_rows = {}
        self.downloads = {}
        self.download_cancel_events = {}
        self.icon_image = None
        self.thumbnail_image = None

        self.url_var = tk.StringVar()
        self.url_var.trace_add("write", lambda *_: self.update_load_button_state())

        self.font = self.platform_monospace_font()

        self.apply_theme(self.detect_theme())
        self.configure_window_icon()
        self.create_menu()
        self.create_widgets()
        self.create_context_menu()
        self.bind_events()
        self.schedule_theme_poll()

    def platform_monospace_font(self):
        match sys.platform:
            case "darwin":
                return "Monaco"
            case "win32":
                return "Consolas"
            case _:
                return "DejaVu Sans Mono"

    def configure_window_icon(self):
        icon_path = self.bundled_path("yaytd_logo_64.png")
        if icon_path.exists():
            try:
                self.icon_image = tk.PhotoImage(file=icon_path.as_posix())
                self.root.iconphoto(True, self.icon_image)
            except tk.TclError:
                pass

    @staticmethod
    def bundled_path(filename):
        base_path = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
        bundled = base_path / filename
        if bundled.exists():
            return bundled
        return Path(__file__).resolve().with_name(filename)

    @classmethod
    def app_version(cls):
        try:
            version = cls.bundled_path("yaytd_version.txt").read_text(encoding="utf-8").strip()
        except OSError:
            version = ""
        return version or os.environ.get("YAYTD_VERSION", "").strip().removeprefix("v") or "development"

    @staticmethod
    def package_version(package_name):
        try:
            return metadata_version(package_name)
        except PackageNotFoundError:
            return "unknown"

    def create_menu(self):
        self.menu_bar = Menu(self.root)

        file_menu = Menu(self.menu_bar, tearoff=False)
        file_menu.add_command(label="Paste", command=self.menu_file_paste)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_close)
        self.menu_bar.add_cascade(label="File", menu=file_menu)

        help_menu = Menu(self.menu_bar, tearoff=False)
        help_menu.add_command(label="About", command=self.open_about_window)
        self.menu_bar.add_cascade(label="Help", menu=help_menu)

        self.root.configure(menu=self.menu_bar)

    def create_widgets(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=1)

        url_group = ttk.LabelFrame(self.root, text="Youtube video link", padding=10)
        url_group.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
        url_group.columnconfigure(0, weight=1)

        self.url_entry = ttk.Entry(url_group, textvariable=self.url_var)
        self.url_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.url_entry.bind("<Return>", lambda _event: self.on_click_load_button())
        self.url_entry.bind("<Button-2>", self.show_context_menu)
        self.url_entry.bind("<Button-3>", self.show_context_menu)

        self.load_button = ttk.Button(url_group, text="Load", command=self.on_click_load_button, state=tk.DISABLED)
        self.load_button.grid(row=0, column=1)

        preview_group = ttk.LabelFrame(self.root, text="Video info", padding=10)
        preview_group.grid(row=1, column=0, sticky="ew", padx=12, pady=6)
        preview_group.columnconfigure(2, weight=1)

        self.thumbnail_label = ttk.Label(preview_group, style="Thumbnail.TLabel", anchor=tk.CENTER)
        self.thumbnail_label.grid(row=0, column=0, rowspan=6, sticky="n", padx=(0, 12))
        self.set_placeholder_thumbnail()

        ttk.Label(preview_group, text="Title:", style="Muted.TLabel").grid(row=0, column=1, sticky="w")
        self.video_title = ttk.Label(preview_group, text="", wraplength=560)
        self.video_title.grid(row=1, column=1, columnspan=2, sticky="ew", pady=(0, 6))

        ttk.Label(preview_group, text="Author:", style="Muted.TLabel").grid(row=2, column=1, sticky="w")
        self.video_author = ttk.Label(preview_group, text="")
        self.video_author.grid(row=3, column=1, columnspan=2, sticky="ew", pady=(0, 6))

        ttk.Label(preview_group, text="Duration:", style="Muted.TLabel").grid(row=4, column=1, sticky="w")
        self.video_duration = ttk.Label(preview_group, text="")
        self.video_duration.grid(row=5, column=1, columnspan=2, sticky="ew")

        stream_frame = ttk.Frame(self.root, padding=(12, 6))
        stream_frame.grid(row=2, column=0, sticky="nsew")
        stream_frame.columnconfigure(0, weight=1)
        stream_frame.rowconfigure(0, weight=1)

        columns = ("format", "type", "resolution", "fps", "abr", "size", "progress", "tracks", "action")
        self.stream_tree = ttk.Treeview(
            stream_frame,
            columns=columns,
            show="headings",
            selectmode="extended",
            style="Stream.Treeview",
        )
        headings = {
            "format": "Format",
            "type": "Type",
            "resolution": "Resolution",
            "fps": "FPS",
            "abr": "Audio",
            "size": "Size",
            "progress": "Progress",
            "tracks": "Tracks",
            "action": "Cancel",
        }
        widths = {
            "format": 72,
            "type": 96,
            "resolution": 110,
            "fps": 58,
            "abr": 72,
            "size": 110,
            "progress": 86,
            "tracks": 80,
            "action": 64,
        }
        anchors = {
            "format": tk.CENTER,
            "type": tk.W,
            "resolution": tk.E,
            "fps": tk.E,
            "abr": tk.E,
            "size": tk.E,
            "progress": tk.E,
            "tracks": tk.CENTER,
            "action": tk.CENTER,
        }
        for column in columns:
            self.stream_tree.heading(column, text=headings[column])
            self.stream_tree.column(column, width=widths[column], minwidth=50, anchor=anchors[column], stretch=column == "type")
        self.stream_tree.grid(row=0, column=0, sticky="nsew")
        self.stream_tree.bind("<<TreeviewSelect>>", lambda _event: self.on_stream_selected())
        self.stream_tree.bind("<Button-1>", self.on_stream_tree_click)
        self.stream_tree.bind("<Motion>", self.on_stream_tree_motion)

        stream_scrollbar = ttk.Scrollbar(stream_frame, orient=tk.VERTICAL, command=self.stream_tree.yview)
        stream_scrollbar.grid(row=0, column=1, sticky="ns")
        self.stream_tree.configure(yscrollcommand=stream_scrollbar.set)

        footer = ttk.Frame(self.root, padding=(12, 6, 12, 12))
        footer.grid(row=3, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)

        self.status_bar = ttk.Label(footer, text="Yet Another YouTube Downloader", style="Status.TLabel")
        self.status_bar.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self.download_button = ttk.Button(footer, text="Download", command=self.on_click_download_button, state=tk.DISABLED)
        self.download_button.grid(row=0, column=1, sticky="e")

    def create_context_menu(self):
        self.context_menu = Menu(self.root, tearoff=False)
        self.context_menu.add_command(label="Paste", command=self.menu_file_paste)

    def bind_events(self):
        self.root.bind("<FocusIn>", self.on_app_focus)
        self.configure_platform_commands()

    def configure_platform_commands(self):
        if sys.platform != "darwin":
            return
        try:
            self.root.createcommand("tkAboutDialog", self.open_about_window)
        except tk.TclError:
            pass

    def detect_theme(self):
        return "dark" if darkdetect.isDark() else "light"

    def schedule_theme_poll(self):
        if self.closing:
            return
        detected_theme = self.detect_theme()
        if detected_theme != self.theme_mode:
            self.apply_theme(detected_theme)
        self.root.after(self.THEME_POLL_MS, self.schedule_theme_poll)

    def apply_theme(self, mode):
        mode = "dark" if mode == "dark" else "light"
        sv_ttk.set_theme(mode)
        self.theme_mode = mode

        palette = self.DARK_PALETTE if mode == "dark" else self.LIGHT_PALETTE
        self.root.configure(background=palette["background"])
        self.style.configure("TFrame", background=palette["background"])
        self.style.configure("TLabelframe", background=palette["background"])
        self.style.configure("TLabelframe.Label", background=palette["background"], foreground=palette["foreground"])
        self.style.configure("TLabel", background=palette["background"], foreground=palette["foreground"])
        self.style.configure("Muted.TLabel", background=palette["background"], foreground=palette["muted"])
        self.style.configure("Status.TLabel", background=palette["background"], foreground=palette["muted"])
        self.style.configure("Title.TLabel", background=palette["background"], foreground=palette["foreground"], font=("TkDefaultFont", 12, "bold"))
        self.style.configure("AboutTitle.TLabel", background=palette["background"], foreground=palette["foreground"], font=("TkDefaultFont", 20, "bold"))
        self.style.configure("AboutVersion.TLabel", background=palette["background"], foreground=palette["muted"])
        self.style.configure("Link.TLabel", background=palette["background"], foreground=palette["link"])
        self.style.configure("Thumbnail.TLabel", background=palette["panel"], foreground=palette["foreground"])
        self.style.configure("Stream.Treeview", font=(self.font, 12), rowheight=26)
        self.style.configure("Stream.Treeview.Heading", font=(self.font, 12, "bold"))

    def set_placeholder_thumbnail(self):
        image = Image.new("RGB", (self.VIDEO_PREVIEW_WIDTH, self.VIDEO_PREVIEW_HEIGHT), "gray")
        self.set_thumbnail_image(image)

    def set_thumbnail_image(self, image):
        image = self.fit_thumbnail(image)
        self.thumbnail_image = ImageTk.PhotoImage(image)
        self.thumbnail_label.configure(image=self.thumbnail_image)

    def fit_thumbnail(self, image):
        image = image.convert("RGB")
        image.thumbnail((self.VIDEO_PREVIEW_WIDTH, self.VIDEO_PREVIEW_HEIGHT), Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", (self.VIDEO_PREVIEW_WIDTH, self.VIDEO_PREVIEW_HEIGHT), "gray")
        offset = (
            (self.VIDEO_PREVIEW_WIDTH - image.width) // 2,
            (self.VIDEO_PREVIEW_HEIGHT - image.height) // 2,
        )
        canvas.paste(image, offset)
        return canvas

    def schedule_on_ui(self, function, args=None):
        if self.closing:
            return
        try:
            self.root.after(0, function, *(args or []))
        except tk.TclError:
            pass

    def is_active_load(self, load_id):
        return not self.closing and load_id == self.current_load_id

    def menu_file_paste(self):
        if self.url_var.get():
            return
        try:
            clipboard_text = self.root.clipboard_get()
        except tk.TclError:
            return

        if "youtu" in clipboard_text:
            self.url_var.set(clipboard_text)
            self.update_status_bar("")
        else:
            self.update_status_bar("Not a valid YouTube URL")

    def show_context_menu(self, event):
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()

    def on_app_focus(self, event):
        if self.focus_autopaste_done or event.widget is not self.root:
            return
        self.focus_autopaste_done = True
        self.menu_file_paste()

    def update_load_button_state(self):
        if self.url_var.get() and not self.loading and self.active_downloads == 0:
            self.load_button.configure(state=tk.NORMAL)
        else:
            self.load_button.configure(state=tk.DISABLED)

    def on_click_load_button(self):
        if self.loading or self.active_downloads > 0:
            return

        url = self.url_var.get().strip()
        if not url:
            self.update_status_bar("Paste a valid Youtube video url")
            return
        url = self.normalize_video_url(url)

        self.current_load_id += 1
        load_id = self.current_load_id
        self.loading = True
        self.clear_video()
        self.update_load_button_state()
        self.update_status_bar("Loading video...")

        thread = threading.Thread(target=self.load_video_url, args=(load_id, url), daemon=True)
        thread.start()

    def clear_video(self):
        self.stream_tree.delete(*self.stream_tree.get_children())
        self.streams_by_id.clear()
        self.stream_rows.clear()
        self.downloads.clear()
        self.download_cancel_events.clear()
        self.download_button.configure(state=tk.DISABLED)
        self.set_placeholder_thumbnail()
        self.video_title.configure(text="")
        self.video_duration.configure(text="")
        self.video_author.configure(text="")

    def load_video_url(self, load_id, url):
        try:
            info = self.extract_video_info(url)
            title = info.get("title") or "Untitled video"
            duration = int(info.get("duration") or 0)
            author = info.get("uploader") or info.get("channel") or ""
            thumbnail_url = info.get("thumbnail")
            self.schedule_on_ui(self.update_status_for_load, [load_id, "Searching streams..."])

            stream_entries = []
            for format_info in info.get("formats") or []:
                stream = self.build_download_stream(url, title, format_info)
                if stream is not None:
                    stream_entries.append((stream, self.build_stream_row(stream)))

            if not stream_entries:
                raise ValueError("No downloadable streams found")

            self.schedule_on_ui(self.apply_loaded_streams, [load_id, title, duration, author, stream_entries])

            if thumbnail_url:
                try:
                    thumbnail = self.load_thumbnail(thumbnail_url)
                    self.schedule_on_ui(self.update_thumbnail, [load_id, thumbnail])
                except Exception:
                    self.schedule_on_ui(self.update_thumbnail_error, [load_id])
        except Exception as error:
            self.schedule_on_ui(self.load_video_failed, [load_id, str(error)])

    def extract_video_info(self, url):
        with YoutubeDL(self.ydl_base_options()) as ydl:
            return ydl.extract_info(url, download=False)

    @staticmethod
    def normalize_video_url(url):
        parsed = urlparse(url.strip())
        host = parsed.netloc.lower().removeprefix("www.")
        path_parts = [part for part in parsed.path.split("/") if part]
        video_id = None

        if host == "youtu.be" and path_parts:
            video_id = path_parts[0]
        elif host in {"youtube.com", "m.youtube.com", "music.youtube.com"}:
            if parsed.path == "/watch":
                video_id = (parse_qs(parsed.query).get("v") or [None])[0]
            elif len(path_parts) >= 2 and path_parts[0] in {"shorts", "live", "embed"}:
                video_id = path_parts[1]
        elif host == "youtube-nocookie.com" and len(path_parts) >= 2 and path_parts[0] == "embed":
            video_id = path_parts[1]

        if video_id:
            return f"https://youtu.be/{video_id}"
        return url

    def ydl_base_options(self):
        return {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "allowed_extractors": ["youtube"],
            "socket_timeout": self.DOWNLOAD_TIMEOUT,
            "retries": self.DOWNLOAD_RETRIES,
            "fragment_retries": self.DOWNLOAD_RETRIES,
        }

    def build_download_stream(self, video_url, title, format_info):
        format_id = str(format_info.get("format_id") or "")
        if not format_id:
            return None

        vcodec = format_info.get("vcodec")
        acodec = format_info.get("acodec")
        has_video = bool(vcodec and vcodec != "none")
        has_audio = bool(acodec and acodec != "none")
        if not has_video and not has_audio:
            return None

        extension = format_info.get("ext") or "media"
        safe_title = sanitize_filename(title, restricted=True) or "video"
        media_kind = "video" if has_video else "audio"
        resolution = ""
        if has_video:
            resolution = format_info.get("resolution") or ""
            if not resolution and format_info.get("height"):
                resolution = f"{format_info['height']}p"

        fps = format_info.get("fps") or ""
        abr = format_info.get("abr")
        abr_label = f"{abr:.0f}k" if isinstance(abr, (int, float)) else ""

        filesize = format_info.get("filesize") or format_info.get("filesize_approx")
        filesize_mb = filesize / (1024 * 1024) if filesize else None

        return DownloadStream(
            video_url=video_url,
            format_id=format_id,
            default_filename=f"{safe_title}.{extension}",
            mime_type=f"{media_kind}/{extension}",
            resolution=resolution,
            fps=str(fps) if fps else "",
            abr=abr_label,
            filesize_mb=filesize_mb,
            has_audio=has_audio,
            has_video=has_video,
        )

    def build_stream_row(self, stream):
        return {
            "format_id": stream.format_id,
            "mime_type": stream.mime_type or "",
            "resolution": stream.resolution or "",
            "fps": stream.fps or "",
            "abr": stream.abr or "",
            "filesize_mb": stream.filesize_mb,
            "has_audio": stream.has_audio,
            "has_video": stream.has_video,
        }

    def format_tree_values(self, row, percent=None, progress_label=None, action_label=""):
        filesize = f"{row['filesize_mb']:.2f} Mb" if row["filesize_mb"] is not None else "unknown"
        progress = progress_label if progress_label is not None else f"{percent:.0f}%" if percent is not None else ""
        tracks = []
        if row["has_audio"]:
            tracks.append("🎧")
        if row["has_video"]:
            tracks.append("🎬")
        return (
            row["format_id"],
            row["mime_type"],
            row["resolution"],
            row["fps"],
            row["abr"],
            filesize,
            progress,
            " ".join(tracks),
            action_label,
        )

    def apply_loaded_streams(self, load_id, title, duration, author, stream_entries):
        if not self.is_active_load(load_id):
            return

        self.stream_tree.delete(*self.stream_tree.get_children())
        self.streams_by_id.clear()
        self.stream_rows.clear()
        for stream, row in stream_entries:
            self.streams_by_id[stream.format_id] = stream
            self.stream_rows[stream.format_id] = row
            self.stream_tree.insert("", tk.END, iid=stream.format_id, values=self.format_tree_values(row))

        self.loading = False
        self.update_url_info(title, duration, author)
        self.update_status_bar(f"Found {len(stream_entries)} streams")
        self.update_load_button_state()

    def on_stream_selected(self):
        selected_ids = list(self.stream_tree.selection())

        if self.active_downloads == 0 and selected_ids:
            self.download_button.configure(state=tk.NORMAL)
        else:
            self.download_button.configure(state=tk.DISABLED)

    def on_stream_tree_click(self, event):
        row_id = self.stream_tree.identify_row(event.y)
        column_name = self.identify_stream_tree_column(event.x)
        if row_id and column_name == "action" and self.downloads.get(row_id) == "downloading":
            self.request_cancel_download(row_id)
            self.update_status_bar("Cancelling download...")
            return "break"
        return None

    def on_stream_tree_motion(self, event):
        row_id = self.stream_tree.identify_row(event.y)
        column_name = self.identify_stream_tree_column(event.x)
        if row_id and column_name == "action" and self.downloads.get(row_id) == "downloading":
            self.stream_tree.configure(cursor="hand2")
        else:
            self.stream_tree.configure(cursor="")

    def identify_stream_tree_column(self, x_position):
        column_id = self.stream_tree.identify_column(x_position)
        if not column_id.startswith("#"):
            return None
        try:
            column_index = int(column_id[1:]) - 1
        except ValueError:
            return None

        columns = self.stream_tree["columns"]
        if 0 <= column_index < len(columns):
            return columns[column_index]
        return None

    def on_click_download_button(self):
        selected_ids = list(self.stream_tree.selection())
        if not selected_ids:
            return

        if len(selected_ids) == 1:
            stream = self.streams_by_id[selected_ids[0]]
            file_name = filedialog.asksaveasfilename(
                parent=self.root,
                initialdir=Path.home(),
                initialfile=f"{stream.format_id}-{stream.default_filename}",
            )
            if file_name:
                self.start_download(stream, file_name)
            return

        folder = filedialog.askdirectory(parent=self.root, title="Select folder", initialdir=Path.home())
        if not folder:
            return

        for format_id in selected_ids:
            stream = self.streams_by_id[format_id]
            file_name = Path(folder).joinpath(f"{stream.format_id}-{stream.default_filename}")
            self.start_download(stream, file_name)

    def request_cancel_download(self, format_id):
        if self.downloads.get(format_id) != "downloading":
            return

        cancel_event = self.download_cancel_events.get(format_id)
        if cancel_event is not None:
            cancel_event.set()

        self.downloads[format_id] = "cancelling"
        self.update_stream_progress(format_id, progress_label="Cancelling", action_label="", force=True)
        self.stream_tree.configure(cursor="")

    def start_download(self, stream, file_name):
        cancel_event = threading.Event()
        self.downloads[stream.format_id] = "downloading"
        self.download_cancel_events[stream.format_id] = cancel_event
        self.active_downloads += 1
        self.download_button.configure(state=tk.DISABLED)
        self.update_load_button_state()
        self.update_status_bar("Download in progress...")
        self.update_stream_progress(stream.format_id, 0, action_label="❌")
        self.on_stream_selected()

        thread = threading.Thread(target=self.download_stream, args=(stream, file_name, cancel_event), daemon=True)
        thread.start()

    def download_stream(self, stream, file_name, cancel_event):
        temp_files = set()
        try:
            target = Path(file_name)
            ydl_options = self.ydl_base_options()
            ydl_options.update(
                {
                    "format": stream.format_id,
                    "outtmpl": target.as_posix(),
                    "progress_hooks": [self.make_download_progress_hook(stream.format_id, cancel_event, temp_files)],
                    "overwrites": True,
                }
            )
            with YoutubeDL(ydl_options) as ydl:
                ydl.download([stream.video_url])
            self.schedule_on_ui(self.mark_download_finished, [stream.format_id, "completed"])
        except DownloadCancelled:
            self.cleanup_temp_files(temp_files)
            self.schedule_on_ui(self.mark_download_finished, [stream.format_id, "cancelled"])
        except Exception:
            self.schedule_on_ui(self.mark_download_finished, [stream.format_id, "failed"])

    def make_download_progress_hook(self, format_id, cancel_event, temp_files):
        def download_progress(progress):
            tmpfilename = progress.get("tmpfilename")
            if tmpfilename:
                temp_files.add(tmpfilename)

            if cancel_event.is_set():
                raise DownloadCancelled("Download cancelled by user")

            status = progress.get("status")
            if status == "finished":
                self.schedule_on_ui(self.update_stream_progress, [format_id, 100])
                return
            if status != "downloading":
                return

            downloaded = progress.get("downloaded_bytes") or 0
            total = progress.get("total_bytes") or progress.get("total_bytes_estimate")
            if total:
                self.schedule_on_ui(self.update_stream_progress, [format_id, (100 * downloaded) / total])

        return download_progress

    def cleanup_temp_files(self, temp_files):
        for temp_file in temp_files:
            try:
                Path(temp_file).unlink(missing_ok=True)
            except OSError:
                pass

    def mark_download_finished(self, format_id, result):
        if self.downloads.get(format_id) not in self.ACTIVE_DOWNLOAD_STATES:
            return

        self.downloads[format_id] = result
        self.download_cancel_events.pop(format_id, None)
        self.active_downloads = max(0, self.active_downloads - 1)

        if result == "completed":
            self.update_stream_progress(format_id, 100, action_label="", force=True)
        elif result == "cancelled":
            self.update_stream_progress(format_id, progress_label="Cancelled", action_label="", force=True)
        else:
            self.update_stream_progress(format_id, progress_label="Failed", action_label="", force=True)

        completed = sum(1 for state in self.downloads.values() if state == "completed")
        cancelled = sum(1 for state in self.downloads.values() if state == "cancelled")
        failed = sum(1 for state in self.downloads.values() if state == "failed")
        total = len(self.downloads)
        details = [f"{completed}/{total} completed"]
        if cancelled:
            details.append(f"{cancelled} cancelled")
        if failed:
            details.append(f"{failed} failed")
        self.update_status_bar(f"Downloads: {', '.join(details)}")

        if self.active_downloads == 0:
            self.update_load_button_state()
        self.on_stream_selected()

    def update_url_info(self, title, duration, author):
        self.video_title.configure(text=title)
        self.video_duration.configure(text=str(timedelta(seconds=duration)))
        self.video_author.configure(text=author)

    def update_stream_progress(self, format_id, percent=None, progress_label=None, action_label=None, force=False):
        if not force and self.downloads.get(format_id) != "downloading":
            return
        if not self.stream_tree.exists(format_id):
            return
        row = self.stream_rows.get(format_id)
        if row is None:
            return
        if action_label is None:
            action_label = "❌" if self.downloads.get(format_id) == "downloading" else ""
        self.stream_tree.item(format_id, values=self.format_tree_values(row, percent, progress_label, action_label))

    def load_thumbnail(self, thumbnail_url):
        with urlopen(thumbnail_url, timeout=self.THUMBNAIL_TIMEOUT, context=self.SSL_CONTEXT) as response:
            image = Image.open(response)
            image.load()
            return image.copy()

    def update_thumbnail(self, load_id, thumbnail):
        if self.is_active_load(load_id):
            self.set_thumbnail_image(thumbnail)

    def update_thumbnail_error(self, load_id):
        if self.is_active_load(load_id):
            self.update_status_bar("Can't load video thumbnail")

    def update_status_for_load(self, load_id, message):
        if self.is_active_load(load_id):
            self.update_status_bar(message)

    def load_video_failed(self, load_id, error_message):
        if not self.is_active_load(load_id):
            return
        self.loading = False
        self.update_status_bar(f"Can't load video: {error_message}")
        self.update_load_button_state()

    def update_status_bar(self, message):
        self.status_bar.configure(text=message)

    def open_about_window(self):
        about = tk.Toplevel(self.root)
        about.title("About YayTD")
        about.resizable(False, False)
        about.transient(self.root)
        about.grab_set()

        frame = ttk.Frame(about, padding=(24, 22, 24, 18))
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(1, weight=1)

        icon_path = self.bundled_path("yaytd_logo_64.png")
        about.icon_image = None
        if icon_path.exists():
            try:
                about.icon_image = tk.PhotoImage(file=icon_path.as_posix())
                ttk.Label(frame, image=about.icon_image).grid(row=0, column=0, rowspan=3, sticky="n", padx=(0, 18))
            except tk.TclError:
                pass

        ttk.Label(frame, text="YayTD", style="AboutTitle.TLabel").grid(row=0, column=1, sticky="w")
        ttk.Label(frame, text=f"Version {self.app_version()}", style="AboutVersion.TLabel").grid(row=1, column=1, sticky="w", pady=(2, 8))
        ttk.Label(frame, text="Yet Another YouTube Downloader", style="Muted.TLabel").grid(row=2, column=1, sticky="w")

        ttk.Separator(frame).grid(row=3, column=0, columnspan=2, sticky="ew", pady=(18, 14))

        details = ttk.Frame(frame)
        details.grid(row=4, column=0, columnspan=2, sticky="ew")
        details.columnconfigure(1, weight=1)

        self.create_about_detail(details, 0, "Engine", f"yt-dlp {ytdlp_version.__version__}")
        self.create_about_detail(details, 1, "Interface", f"tkinter.ttk + sv-ttk {self.package_version('sv-ttk')}")
        self.create_about_detail(details, 2, "Theme detection", f"darkdetect {self.package_version('darkdetect')}")
        self.create_about_detail(details, 3, "Images", f"Pillow {self.package_version('pillow')}")
        self.create_about_detail(details, 4, "Certificates", f"certifi {self.package_version('certifi')}")
        self.create_about_detail(details, 5, "Python", f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")

        links = ttk.Frame(frame)
        links.grid(row=5, column=0, columnspan=2, sticky="w", pady=(16, 0))
        about_links = [
            ("GitHub", self.REPOSITORY_URL),
            ("yt-dlp", "https://github.com/yt-dlp/yt-dlp"),
            ("sv-ttk", "https://github.com/rdbende/Sun-Valley-ttk-theme"),
            ("Pillow", "https://python-pillow.org/"),
            ("darkdetect", "https://github.com/albertosottile/darkdetect"),
            ("certifi", "https://github.com/certifi/python-certifi"),
        ]
        for index, (text, url) in enumerate(about_links):
            self.create_about_link(links, text, url, index // 3, index % 3)

        ttk.Button(frame, text="Close", command=about.destroy).grid(row=6, column=0, columnspan=2, sticky="e", pady=(18, 0))

        self.center_window(about, 500, 380)
        about.wait_window()

    def create_about_detail(self, frame, row, label, value):
        ttk.Label(frame, text=label, style="Muted.TLabel").grid(row=row, column=0, sticky="w", padx=(0, 18), pady=3)
        ttk.Label(frame, text=value).grid(row=row, column=1, sticky="w", pady=3)

    def create_about_link(self, frame, text, url, row, column):
        label = ttk.Label(frame, text=text, style="Link.TLabel", cursor="hand2")
        label.grid(row=row, column=column, sticky="w", padx=(0, 18), pady=2)
        label.bind("<Button-1>", lambda _event: webbrowser.open(url))

    def center_window(self, window, width, height):
        self.root.update_idletasks()
        root_x = self.root.winfo_rootx()
        root_y = self.root.winfo_rooty()
        root_width = self.root.winfo_width()
        root_height = self.root.winfo_height()
        x = root_x + (root_width - width) // 2
        y = root_y + (root_height - height) // 2
        window.geometry(f"{width}x{height}+{x}+{y}")

    def on_close(self):
        self.closing = True
        for cancel_event in self.download_cancel_events.values():
            cancel_event.set()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    app = YayTDApp()
    app.run()


if __name__ == "__main__":
    os.environ["SSL_CERT_FILE"] = certifi.where()
    main()
