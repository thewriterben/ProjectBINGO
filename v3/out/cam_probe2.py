import urllib.request
HOST = "192.168.1.230"
urls = [
    # UI proxy (Fluidd/Mainsail commonly proxy /webcam/)
    f"http://{HOST}:4408/webcam/?action=snapshot",
    f"http://{HOST}:4408/webcam/?action=stream",
    f"http://{HOST}/webcam/?action=snapshot",
    # port 8000 — likely camera service; try go2rtc / mediamtx / creality shapes
    f"http://{HOST}:8000/api/frame.jpeg",
    f"http://{HOST}:8000/api/streams",
    f"http://{HOST}:8000/snapshot.jpg",
    f"http://{HOST}:8000/image",
    f"http://{HOST}:8000/jpg",
    f"http://{HOST}:8000/",
    f"http://{HOST}:8000/stream",
    f"http://{HOST}:8000/0/stream",
    f"http://{HOST}:8000/cam.jpg",
]
for url in urls:
    try:
        r = urllib.request.urlopen(url, timeout=6)
        b = r.read(200)
        ct = r.headers.get_content_type()
        jpeg = b[:2] == b"\xff\xd8"
        head = b[:40]
        print(f"{url}\n   {r.status} ct={ct} jpeg={jpeg} first={head!r}\n")
    except Exception as e:
        print(f"{url}\n   FAIL {repr(e)[:90]}\n")
