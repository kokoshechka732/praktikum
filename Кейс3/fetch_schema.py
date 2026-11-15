import json
import os
import urllib.parse
import urllib.request

KEY = "https%3A%2F%2Fdisk.yandex.ru%2Fd%2FUYuFNCrHvWR3DQ"
BASE = os.path.dirname(os.path.abspath(__file__))
DEST = os.path.join(BASE, "data", "db_structure")


def api(path):
    q = "public_key=" + KEY + "&limit=200&path=" + urllib.parse.quote(path)
    url = "https://cloud-api.yandex.net/v1/disk/public/resources?" + q
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def href(path):
    q = "public_key=" + KEY + "&path=" + urllib.parse.quote(path)
    url = "https://cloud-api.yandex.net/v1/disk/public/resources/download?" + q
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)["href"]


def main():
    os.makedirs(DEST, exist_ok=True)
    js = api("/db_structure")
    items = js["_embedded"]["items"]
    print("файлов в db_structure:", len(items))
    for it in items:
        name = it["name"]
        out = os.path.join(DEST, name)
        if os.path.exists(out) and os.path.getsize(out) == it.get("size", 0):
            continue
        req = urllib.request.Request(href("/db_structure/" + name), headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as r, open(out, "wb") as fh:
            fh.write(r.read())
        print("  ", name, it.get("size"), "байт")
    print("готово")


if __name__ == "__main__":
    main()
