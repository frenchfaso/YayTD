# Imports
import os
import sys
import certifi
from dataclasses import dataclass
from PIL import Image
from tkinter import Menu
from tkinter.constants import *
from guizero import *
from yt_dlp import YoutubeDL
from yt_dlp.utils import sanitize_filename
from urllib.request import urlopen
import threading
from pathlib import Path
from datetime import timedelta
import webbrowser


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


def main():
    # Functions and Callbacks
    def schedule_on_ui(function, args=None):
        if closing:
            return
        try:
            app.after(0, function, args or [])
        except Exception:
            pass

    def is_active_load(load_id):
        return not closing and load_id == current_load_id

    def update_load_button_state():
        if yt_url.value != "" and not loading and active_downloads == 0:
            load_url_button.enable()
        else:
            load_url_button.disable()

    def apply_light_palette():
        app.tk.call(
            "tk_setPalette",
            "background", LIGHT_BG,
            "foreground", LIGHT_FG,
            "activeBackground", LIGHT_ACTIVE_BG,
            "activeForeground", LIGHT_FG,
            "highlightBackground", LIGHT_BG,
            "highlightColor", LIGHT_ACCENT,
            "selectBackground", LIGHT_SELECT_BG,
            "selectForeground", LIGHT_SELECT_FG,
            "disabledForeground", LIGHT_DISABLED_FG,
            "insertBackground", LIGHT_FG,
            "troughColor", LIGHT_BORDER,
        )

    def configure_tk_options(tk_widget, **options):
        supported_options = set(tk_widget.keys())
        safe_options = {
            option: value
            for option, value in options.items()
            if option in supported_options
        }
        if safe_options:
            tk_widget.configure(**safe_options)

    def configure_light_widget(widget, *, bg=None, fg=None, input_widget=False):
        bg = LIGHT_BG if bg is None else bg
        fg = LIGHT_FG if fg is None else fg
        widget.bg = bg
        widget.text_color = fg
        configure_tk_options(
            widget.tk,
            background=bg,
            foreground=fg,
            activebackground=LIGHT_ACTIVE_BG,
            activeforeground=LIGHT_FG,
            highlightbackground=LIGHT_BORDER,
            highlightcolor=LIGHT_ACCENT,
        )
        if input_widget:
            input_options = {
                "background": LIGHT_INPUT_BG,
                "foreground": LIGHT_FG,
                "insertbackground": LIGHT_FG,
                "selectbackground": LIGHT_SELECT_BG,
                "selectforeground": LIGHT_SELECT_FG,
                "highlightbackground": LIGHT_BORDER,
                "highlightcolor": LIGHT_ACCENT,
            }
            configure_tk_options(widget.tk, **input_options)

            listbox = getattr(widget, "_listbox", None)
            if listbox is not None:
                configure_tk_options(listbox.tk, **input_options)

            for child in widget.tk.winfo_children():
                configure_tk_options(
                    child,
                    background=LIGHT_INPUT_BG,
                    activebackground=LIGHT_ACTIVE_BG,
                    troughcolor=LIGHT_BORDER,
                    highlightbackground=LIGHT_BORDER,
                )

    def configure_link(widget):
        configure_light_widget(widget, fg=LIGHT_LINK)
        configure_tk_options(widget.tk, cursor="hand2")

    def menu_file_paste():
        if yt_url.value == "":
            try:
                clipboard_text = app.tk.clipboard_get()
                if "youtu" in clipboard_text:
                    yt_url.value = clipboard_text
                    update_load_button_state()
                    update_status_bar("")
                else:
                    update_status_bar("Not a valid YouTube URL")
            except Exception:
                pass

    def menu_file_exit():
        on_app_close()

    def on_app_close():
        nonlocal closing
        closing = True
        try:
            about_window.cancel(stay_modal)
        except Exception:
            pass
        app.destroy()

    def menu_help_about():
        pos_str = app.tk.geometry().split('+')
        pos = (int(pos_str[1]), int(pos_str[2]))
        about_window.tk.geometry(f"{about_window.width}x{about_window.height}+{pos[0] + APP_WIDTH // 2 - about_window.width // 2}+{pos[1] + APP_HEIGHT // 2 - about_window.height // 2}")
        about_window.repeat(function=stay_modal, args=[about_window], time=100)
        about_window.show(wait=True)

    def on_about_close():
        about_window.cancel(stay_modal)
        about_window.hide()

    def stay_modal(widget):
        widget.tk.lift()

    def show_context_menu(event):
        try:
            context_menu.tk_popup(event.display_x, event.display_y)
        finally:
            context_menu.grab_release()

    def url_update():
        update_load_button_state()

    def on_key_pressed(event):
        if event.key != "" and len(event.key) == 1 and ord(event.key) == 13:
            on_click_load_button()

    def on_app_focus(event):
        if(event.widget == app.tk):
            app.tk.unbind("<FocusIn>")
            menu_file_paste()

    def on_click_load_button():
        nonlocal current_load_id, loading
        if loading or active_downloads > 0:
            return

        current_load_id += 1
        load_id = current_load_id
        loading = True
        stream_list.clear()
        streams.clear()
        stream_rows.clear()
        stream_row_by_id.clear()
        downloads.clear()
        download_button.disable()
        update_load_button_state()
        video_thumbnail.image = Image.new(mode="RGB", size=(VIDEO_PREVIEW_WIDTH,VIDEO_PREVIEW_HEIGHT), color="gray")
        video_title.value = ""
        video_duration.value = ""
        video_author.value = ""
        if (yt_url.value):
            url = yt_url.value
            t = threading.Thread(target=load_video_url, args=[load_id, url], daemon=True)
            t.start()
        else:
            loading = False
            update_load_button_state()
            update_status_bar("Paste a valid Youtube video url")

    def load_video_url(load_id, url):
        try:
            info = extract_video_info(url)
            title = info.get("title") or "Untitled video"
            length = int(info.get("duration") or 0)
            author = info.get("uploader") or info.get("channel") or ""
            thumbnail_url = info.get("thumbnail")
            schedule_on_ui(update_status_for_load, [load_id, "Searching streams..."])

            stream_entries = []
            for format_info in info.get("formats") or []:
                stream = build_download_stream(url, title, format_info)
                if stream is not None:
                    stream_entries.append((stream, build_stream_row(stream)))

            if not stream_entries:
                raise ValueError("No downloadable streams found")

            schedule_on_ui(apply_loaded_streams, [load_id, title, length, author, stream_entries])

            if thumbnail_url:
                try:
                    thumbnail = load_thumbnail(thumbnail_url)
                    schedule_on_ui(update_thumbnail, [load_id, thumbnail])
                except Exception:
                    schedule_on_ui(update_thumbnail_error, [load_id])
        except Exception as error:
            schedule_on_ui(load_video_failed, [load_id, str(error)])

    def extract_video_info(url):
        with YoutubeDL(ydl_base_options()) as ydl:
            return ydl.extract_info(url, download=False)

    def ydl_base_options():
        return {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "allowed_extractors": ["youtube"],
            "socket_timeout": DOWNLOAD_TIMEOUT,
            "retries": DOWNLOAD_RETRIES,
            "fragment_retries": DOWNLOAD_RETRIES,
        }

    def build_download_stream(video_url, title, format_info):
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

    def stream_selected():
        if active_downloads == 0:
            download_button.enable()

    def make_download_progress_hook(format_id):
        def download_progress(progress):
            status = progress.get("status")
            if status == "finished":
                schedule_on_ui(update_stream_list, [format_id, 100])
                return
            if status != "downloading":
                return

            downloaded = progress.get("downloaded_bytes") or 0
            total = progress.get("total_bytes") or progress.get("total_bytes_estimate")
            if total:
                schedule_on_ui(update_stream_list, [format_id, (100 * downloaded) / total])

        return download_progress

    def build_stream_row(stream):
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

    def format_stream_row(row, percent=None):
        progress = f"{percent:>4.0f}%" if percent is not None else "     "
        filesize = f"{row['filesize_mb']:>10.2f} Mb" if row["filesize_mb"] is not None else f"{'unknown':>13}"
        audio = "🎧" if row["has_audio"] else ""
        video = "🎬" if row["has_video"] else ""
        return (
            f"{row['format_id'][:6]:>6}  "
            f"{row['mime_type']:<10}"
            f"{row['resolution']:>8}"
            f"{row['fps']:>5}"
            f"{row['abr']:>10}"
            f"{filesize}"
            f"{progress:>7}"
            f"{audio:>4}"
            f"{video:>2}"
        )

    def apply_loaded_streams(load_id, title, duration, author, stream_entries):
        nonlocal loading
        if not is_active_load(load_id):
            return

        streams.clear()
        stream_rows.clear()
        stream_row_by_id.clear()
        stream_list.clear()
        for index, (stream, row) in enumerate(stream_entries):
            streams.append(stream)
            stream_rows.append(row)
            stream_row_by_id[stream.format_id] = index
            stream_list.append(format_stream_row(row))

        loading = False
        update_url_info(title, duration, author)
        update_status_bar(f"Found {len(stream_entries)} streams")
        update_load_button_state()

    def on_click_download_button():
        if stream_list.value != None:
            selected_rows = selected_stream_indexes()
            if not selected_rows:
                return
            if len(selected_rows) == 1:
                stream = streams[selected_rows[0]]
                file_name = app.select_file(save=True, filename=f"{stream.format_id}-{stream.default_filename}", folder=Path.home())
                if file_name:
                    start_download(stream, file_name)
            else:
                folder = app.select_folder(title="Select folder", folder=Path.home())
                if folder:
                    for id in selected_rows:
                        stream = streams[id]
                        file_name = Path(folder).joinpath(f"{stream.format_id}-{stream.default_filename}")
                        start_download(stream, file_name)

    def selected_stream_indexes():
        return [
            stream_list.items.index(item)
            for item in stream_list.value
            if item in stream_list.items
        ]

    def start_download(stream, file_name):
        nonlocal active_downloads
        downloads[stream.format_id] = "downloading"
        active_downloads += 1
        download_button.disable()
        update_load_button_state()
        update_status_bar("Download in progress...")

        t = threading.Thread(target=download_stream, args=[stream, file_name], daemon=True)
        t.start()

    def download_stream(stream, file_name):
        try:
            target = Path(file_name)
            ydl_options = ydl_base_options()
            ydl_options.update(
                {
                    "format": stream.format_id,
                    "outtmpl": target.as_posix(),
                    "progress_hooks": [make_download_progress_hook(stream.format_id)],
                    "overwrites": True,
                }
            )
            with YoutubeDL(ydl_options) as ydl:
                ydl.download([stream.video_url])
            schedule_on_ui(mark_download_finished, [stream.format_id, True])
        except Exception:
            schedule_on_ui(mark_download_finished, [stream.format_id, False])

    def mark_download_finished(format_id, success):
        nonlocal active_downloads
        if downloads.get(format_id) != "downloading":
            return

        downloads[format_id] = "completed" if success else "failed"
        active_downloads = max(0, active_downloads - 1)
        completed = sum(1 for state in downloads.values() if state == "completed")
        total = len(downloads)
        if success:
            update_status_bar(f"Download {completed}/{total} completed")
        else:
            update_status_bar(f"Download failed ({completed}/{total} completed)")

        if active_downloads == 0:
            update_load_button_state()
            if stream_list.value:
                download_button.enable()
    
    def update_url_info(title, duration, author):
        video_title.value = title
        video_duration.value = f"{timedelta(seconds=duration)}"
        video_author.value = author

    def update_stream_list(format_id, percent):
        if downloads.get(format_id) != "downloading":
            return
        id = stream_row_by_id.get(format_id)
        if id is None or id >= len(stream_list.items):
            return
        stream_list.remove(stream_list.items[id])
        stream_list.insert(id, format_stream_row(stream_rows[id], percent))

    def load_thumbnail(thumbnail_url):
        with urlopen(thumbnail_url, timeout=THUMBNAIL_TIMEOUT) as response:
            image = Image.open(response)
            image.load()
            return image.copy()

    def update_thumbnail(load_id, thumbnail):
        if is_active_load(load_id):
            video_thumbnail.image = thumbnail

    def update_thumbnail_error(load_id):
        if is_active_load(load_id):
            update_status_bar("Can't load video thumbnail")

    def update_status_for_load(load_id, message):
        if is_active_load(load_id):
            update_status_bar(message)

    def load_video_failed(load_id, error_message):
        nonlocal loading
        if not is_active_load(load_id):
            return
        loading = False
        update_status_bar(f"Can't load video: {error_message}")
        update_load_button_state()

    def update_status_bar(message):
        status_bar.value = message

    # Variables
    streams = []
    stream_rows = []
    stream_row_by_id = {}
    downloads = {}
    current_load_id = 0
    loading = False
    active_downloads = 0
    closing = False
    LIGHT_BG = "#f5f5f7"
    LIGHT_PANEL_BG = "#ffffff"
    LIGHT_INPUT_BG = "#ffffff"
    LIGHT_FG = "#1d1d1f"
    LIGHT_MUTED_FG = "#4a4a4f"
    LIGHT_DISABLED_FG = "#8e8e93"
    LIGHT_ACTIVE_BG = "#e5e5ea"
    LIGHT_BORDER = "#d1d1d6"
    LIGHT_SELECT_BG = "#0a84ff"
    LIGHT_SELECT_FG = "#ffffff"
    LIGHT_ACCENT = "#007aff"
    LIGHT_LINK = "#0057d9"
    APP_WIDTH = 800
    APP_HEIGHT = 700
    VIDEO_PREVIEW_WIDTH = 160
    VIDEO_PREVIEW_HEIGHT = 120
    THUMBNAIL_TIMEOUT = 10
    DOWNLOAD_TIMEOUT = 30
    DOWNLOAD_RETRIES = 2
    FONT = None

    match sys.platform:
        case "darwin":
            FONT = "Monaco"
        case "win32":
            FONT = "Consolas"
        case "linux":
            FONT = "DejaVu Sans Mono"

    # App
    app = App(title="YayTD", width=APP_WIDTH, height=APP_HEIGHT, bg=LIGHT_BG)
    app.icon = Path(__file__).resolve().with_name("yaytd_logo_64.png").as_posix()
    app.tk.minsize(APP_WIDTH, APP_HEIGHT)
    apply_light_palette()

    # Widgets
    main_menu = MenuBar(app, toplevel=["File", "Help"], options=[[["Paste", menu_file_paste],["Exit", menu_file_exit]],[["About",menu_help_about]]])

    title_box_input = TitleBox(app, text="Youtube video link", width="fill")
    configure_light_widget(title_box_input, bg=LIGHT_PANEL_BG)
    input_box = Box(title_box_input, align="top", width="fill")
    input_box.bg = LIGHT_PANEL_BG
    yt_url = TextBox(input_box, align="left", width="fill", command=url_update)
    configure_light_widget(yt_url, input_widget=True)
    yt_url.when_right_button_pressed = show_context_menu
    yt_url.when_key_pressed = on_key_pressed
    load_url_button = PushButton(input_box, on_click_load_button, text="Load", align="left", enabled=False)
    configure_light_widget(load_url_button, bg=LIGHT_ACTIVE_BG)

    title_video_preview = TitleBox(app, text="Video info", width="fill")
    configure_light_widget(title_video_preview, bg=LIGHT_PANEL_BG)
    box_preview = Box(title_video_preview, layout="grid", align="left")
    box_preview.bg = LIGHT_PANEL_BG
    video_thumbnail = Picture(box_preview, grid=[0,0,1,6], width=VIDEO_PREVIEW_WIDTH, height=VIDEO_PREVIEW_HEIGHT, image=Image.new(mode="RGB", size=(VIDEO_PREVIEW_WIDTH,VIDEO_PREVIEW_HEIGHT), color="gray"), align="top")
    spacer = Box(box_preview, grid=[1,0], width=15, height="fill")
    spacer.bg = LIGHT_PANEL_BG
    title_label = Text(box_preview, grid=[2,0], text="Title:", align="left", bg=LIGHT_PANEL_BG, color=LIGHT_MUTED_FG)
    video_title = Text(box_preview, grid=[2,1], align="left")
    configure_light_widget(video_title, bg=LIGHT_PANEL_BG)
    author_label = Text(box_preview,grid=[2,2], text="Author:", align="left", bg=LIGHT_PANEL_BG, color=LIGHT_MUTED_FG)
    video_author = Text(box_preview,grid=[2,3], align="left")
    configure_light_widget(video_author, bg=LIGHT_PANEL_BG)
    duration_label = Text(box_preview, grid=[2,4], text="Duration:", align="left", bg=LIGHT_PANEL_BG, color=LIGHT_MUTED_FG)
    video_duration = Text(box_preview, grid=[2,5], align="left")
    configure_light_widget(video_duration, bg=LIGHT_PANEL_BG)

    stream_list = ListBox(app, width="fill", height="fill", scrollbar=True, command=stream_selected, multiselect=True)
    configure_light_widget(stream_list, input_widget=True)
    stream_list.text_size = 12
    stream_list.font = FONT
    box_bottom = Box(app, align="bottom", width="fill")
    box_bottom.bg = LIGHT_BG
    status_bar = Text(box_bottom, text="Yet Another YouTube Downloader", align="left")
    configure_light_widget(status_bar, bg=LIGHT_BG)
    download_button = PushButton(box_bottom, command=on_click_download_button, text="Download", enabled=False, align="right")
    configure_light_widget(download_button, bg=LIGHT_ACTIVE_BG)

    # TK Widgets
    context_menu = Menu(input_box.tk, tearoff = 0)
    context_menu.add_command(label ="Paste", command=menu_file_paste)

    # Windows
    about_window = Window(app, title="About", visible=False, width=320, height=240, bg=LIGHT_BG)
    about_window.tk.resizable(0,0)
    box = Box(about_window, align="left", width="fill")
    box.bg = LIGHT_BG
    close_button = PushButton(box, command=lambda : about_window._close_window(), text="Close", align="bottom")
    configure_light_widget(close_button, bg=LIGHT_ACTIVE_BG)
    Picture(box, image=Path(__file__).resolve().with_name("yaytd_logo_64.png").as_posix())
    about_title = Text(box, "YayTD", size=12)
    configure_light_widget(about_title)
    about_title.tk.configure(font=("bold"))
    yaytd_gh_link = Text(box, "https://github.com/frenchfaso/yaytd", color=LIGHT_LINK)
    yaytd_gh_link.when_clicked = lambda _ : webbrowser.open("https://github.com/frenchfaso/yaytd")
    configure_link(yaytd_gh_link)
    about_text = Text(box, "Yet Another YouTube Downloader\nis a simple GUI built on top of 'yt-dlp'\nwith 'guizero' and a little bit of 'tkinter'", size=10)
    configure_light_widget(about_text)
    box_links = Box(box)
    box_links.bg = LIGHT_BG
    ytdlp_link = Text(box_links, text="yt-dlp", color=LIGHT_LINK, align="left")
    ytdlp_link.when_clicked = lambda _ : webbrowser.open("https://github.com/yt-dlp/yt-dlp")
    configure_link(ytdlp_link)
    guizero_link = Text(box_links, "guizero", color=LIGHT_LINK, align="left")
    guizero_link.when_clicked = lambda _ : webbrowser.open("https://lawsie.github.io/guizero/")
    configure_link(guizero_link)
    tkinter_link = Text(box_links, "tkinter", color=LIGHT_LINK, align="left")
    tkinter_link.when_clicked = lambda _ : webbrowser.open("https://docs.python.org/3/library/tkinter.html")
    configure_link(tkinter_link)
    about_window.when_closed = on_about_close

    app.tk.bind("<FocusIn>", on_app_focus)
    app.when_closed = on_app_close

    app.display()

if(__name__ == "__main__"):
    os.environ['SSL_CERT_FILE'] = certifi.where()
    main()
