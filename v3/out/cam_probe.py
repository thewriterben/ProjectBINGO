import socket, urllib.request, json
HOST = "192.168.1.230"

# 1) port scan
ports = [80,81,88,443,4408,4409,8080,8081,8000,8888,3031,10000,8554,1984,8889,7125,9999]
open_ports = []
for p in ports:
    s = socket.socket(); s.settimeout(1.5)
    try:
        s.connect((HOST, p)); open_ports.append(p)
    except Exception:
        pass
    finally:
        s.close()
print("OPEN TCP:", open_ports)

# 2) candidate snapshot URLs across open HTTP ports
paths = ["/webcam/?action=snapshot", "/?action=snapshot", "/snapshot",
         "/webcam?action=snapshot", "/cam/snapshot", "/webcam/snapshot"]
http_ports = [p for p in open_ports if p not in (9999, 8554, 1984)]
for port in http_ports:
    base = f"http://{HOST}:{port}" if port != 80 else f"http://{HOST}"
    for path in paths:
        url = base + path
        try:
            r = urllib.request.urlopen(url, timeout=5)
            b = r.read(4)
            ct = r.headers.get_content_type()
            jpeg = b[:2] == b"\xff\xd8"
            print(f"  {url}  ->  {r.status} {ct} first4={b!r} {'JPEG!' if jpeg else ''}")
        except Exception as e:
            pass  # quiet on failures
print("done")
