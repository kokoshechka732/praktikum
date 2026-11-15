import json
import os
import sys
import time
import urllib.parse
import urllib.request

KEY = "https%3A%2F%2Fdisk.yandex.ru%2Fd%2FUYuFNCrHvWR3DQ"
NAME = "logs.zip"
DEST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def href(name):
    q = "public_key=" + KEY + "&path=" + urllib.parse.quote("/" + name)
    url = "https://cloud-api.yandex.net/v1/disk/public/resources/download?" + q
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)["href"]


def size_of(name):
    url = ("https://cloud-api.yandex.net/v1/disk/public/resources"
           "?public_key=" + KEY + "&limit=200")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        js = json.load(r)
    for it in js["_embedded"]["items"]:
        if it["name"] == name:
            return it.get("size", 0)
    raise RuntimeError("not in share: " + name)


def main():
    os.makedirs(DEST, exist_ok=True)
    total = size_of(NAME)
    path = os.path.join(DEST, NAME)
    print(f"remote size {total / 1e9:.2f} GB", flush=True)
    if os.path.exists(path) and os.path.getsize(path) == total:
        print("already downloaded", flush=True)
        return
    part = path + ".part"
    have = os.path.getsize(part) if os.path.exists(part) else 0
    print(f"resume from {have} bytes", flush=True)
    req = urllib.request.Request(href(NAME), headers={"User-Agent": "Mozilla/5.0"})
    if have:
        req.add_header("Range", f"bytes={have}-")
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=120) as resp, open(part, "ab" if have else "wb") as out:
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            out.write(chunk)
            have += len(chunk)
            if have % (200 << 20) < (1 << 20):
                el = max(time.time() - t0, 0.001)
                print(f"{have / 1e9:.2f}/{total / 1e9:.2f} GB  {(have - (os.path.getsize(part) - have)) if False else ''}"
                      f"{(have / 1e6) / el:.1f} MB/s", flush=True)
    os.replace(part, path)
    print(f"done {os.path.getsize(path)} bytes in {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
