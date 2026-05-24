
<div align="center">
<img src="https://user-images.githubusercontent.com/1913203/215260281-edf84b41-6622-4a88-8b44-1e04085e4404.png"/>
<h1>YayTD</h1>
<h5>Yet Another YouTube Downloader</h5>
<img src="https://user-images.githubusercontent.com/1913203/215547904-42a7a829-a272-4c91-a626-d4cf397f9600.png"/>
</div>


# What
YayTD is a simple GUI built on top of [yt-dlp](https://github.com/yt-dlp/yt-dlp) with [tkinter.ttk](https://docs.python.org/3/library/tkinter.ttk.html) and [sv-ttk](https://github.com/rdbende/Sun-Valley-ttk-theme).

It lets you find all streams associated with a YouTube video (audio only, video only or both combined) and download them to your machine for your convenience.
# Did we really need another one?
Probably not. But it seemed the perfect toy-project to learn about tkinter, additionally, as an occasional user of the yt-dlp cli I wondered how a handy GUI would have looked like.
# How
## Install
Head to the [releases](https://github.com/frenchfaso/YayTD/releases) and download the zip for your OS (Linux, Mac, Windows).  
Unzip and run the application.
## Build
Or clone this repo and do:
```console
python -m venv env
source env/bin/activate
```
to create a python virtual environment in which to pip install the required modules:
```console
pip install -r requirements.txt
```
now you can either run YayTD with
```console
python main.py
```
or build a single-file executable for your platform:

Linux
```console
pyinstaller yaytd_lin.spec
```
Windows
```console
pyinstaller yaytd_win.spec
```
Mac
```console
pyinstaller yaytd_mac.spec
```
which should appear shortly after in the `dist` folder.
