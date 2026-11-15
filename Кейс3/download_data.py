import json
import os
import time
import urllib.parse
import urllib.request

KEY = "https%3A%2F%2Fdisk.yandex.ru%2Fd%2FUYuFNCrHvWR3DQ"
PUBLIC = "https://disk.yandex.ru/d/UYuFNCrHvWR3DQ"
DEST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

ORDER = [
    "product.csv", "product_periods.csv", "product_trial.csv", "product_period_discounts.csv",
    "payment_providers.csv", "payment_categories.csv", "currency_rates.csv", "locale.csv",
    "locations.csv", "nodes.csv", "server_categories.csv", "mobile_version.csv",
    "referral_config.csv", "referral_code_used.csv", "referral_history.csv",
    "user_blocks.csv", "client_app_config.csv", "country_disabled_products.csv",
    "metric_values.csv", "task_history.csv", "goose_db_version.csv", "advertising_ids.csv",
    "subscribe.csv", "orders.csv", "external_accounts.csv", "saved_payment_methods.csv",
    "save_location.csv", "device_code.csv", "users.csv", "transactions.csv",
    "devices.csv", "adv_view_history.csv", "sessions.csv",
    "proxy_user_connection_logs.csv",
    "user_connection_logs_02_26.csv", "user_connection_logs_03_04_26.csv",
    "user_connection_logs_05_26.csv", "user_connection_logs_06_26.csv",
    "user_connection_logs_07_26.csv", "user_connection_logs_08_26.csv",
    "user_connection_logs_09_26.csv",
]


def log(msg):
    line = time.strftime("%H:%M:%S ") + msg
    print(line, flush=True)
    with open(os.path.join(os.path.dirname(DEST), "download.log"), "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def listing():
    url = ("https://cloud-api.yandex.net/v1/disk/public/resources"
           f"?public_key={KEY}&limit=200")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    js = json.load(urllib.request.urlopen(req, timeout=60))
    return {it["name"]: it for it in js["_embedded"]["items"]}


def href_for(name):
    q = "public_key=" + KEY + "&path=" + urllib.parse.quote("/" + name)
    url = "https://cloud-api.yandex.net/v1/disk/public/resources/download?" + q
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            return json.load(urllib.request.urlopen(req, timeout=60))["href"]
        except Exception as exc:
            log(f"  href retry {attempt + 1} {name}: {exc}")
            time.sleep(2 + 3 * attempt)
    raise RuntimeError("no href for " + name)


def download(name, size):
    path = os.path.join(DEST, name)
    if os.path.exists(path) and os.path.getsize(path) == size:
        log(f"skip {name} (already {size} bytes)")
        return
    part = path + ".part"
    have = os.path.getsize(part) if os.path.exists(part) else 0
    href = href_for(name)
    req = urllib.request.Request(href, headers={"User-Agent": "Mozilla/5.0"})
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
    os.replace(part, path)
    elapsed = max(time.time() - t0, 0.001)
    log(f"done {name} {size / 1e6:.1f} MB in {elapsed:.0f}s ({(size / 1e6) / elapsed:.2f} MB/s)")


def main():
    os.makedirs(DEST, exist_ok=True)
    items = listing()
    total = sum(i.get("size", 0) for n, i in items.items() if n in ORDER)
    log(f"listing ok: {len(items)} entries, planned {total / 1e9:.2f} GB")
    for name in ORDER:
        it = items.get(name)
        if not it:
            log(f"missing in share: {name}")
            continue
        try:
            download(name, it.get("size", 0))
        except Exception as exc:
            log(f"FAIL {name}: {exc}")
    log("ALL DONE")


if __name__ == "__main__":
    main()
