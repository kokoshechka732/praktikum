import csv
import io
import json
import os
import re
import zipfile
from collections import Counter, defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(BASE, "data", "logs.zip")
OUT = os.path.join(BASE, "out")
os.makedirs(OUT, exist_ok=True)

LINE = re.compile(r"^(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2})\.(\d+) \[(\w+)\] ([^:]+): (.*)$")
HEAD = re.compile(r"Running on Os\.([^;]+); OS version ([^;]+); App version (\S+)")
IP = re.compile(r"\b\d{1,3}(?:[.:]\d{1,3}){1,3}(?::\d+)?\b")
DOMAIN = re.compile(r"\bfor ([A-Za-z0-9_.-]+)\.")
URL = re.compile(r'https?://\S+')


def norm(msg):
    m = DOMAIN.sub("for <host>.", msg)
    m = URL.sub("<url>", m)
    m = IP.sub("<ip>", m)
    m = re.sub(r"\s+", " ", m).strip()
    return m[:120]


types = defaultdict(lambda: {"events": 0, "users": set(), "first": "", "last": ""})
by_version = defaultdict(lambda: {"users": set(), "errors": 0, "lines": 0})
by_day = Counter()
users = {}
level_totals = Counter()

z = zipfile.ZipFile(PATH)
infos = [i for i in z.infolist() if i.filename.endswith(".zip")]
print(f"архивов: {len(infos)}", flush=True)
total = Counter()

for n, info in enumerate(infos, 1):
    parts = info.filename.split("/")
    user_id = parts[1] if len(parts) > 2 else "?"
    try:
        inner = zipfile.ZipFile(io.BytesIO(z.read(info)))
    except Exception as exc:
        print(f"skip {info.filename}: {exc}", flush=True)
        continue

    names = inner.namelist()
    logs = sorted(x for x in names if x.endswith(".log"))
    os_name = os_ver = app_ver = ""
    if logs:
        try:
            with inner.open(logs[0]) as fh:
                m = HEAD.search(fh.read(400).decode("utf-8", "replace"))
            if m:
                os_name, os_ver, app_ver = m.group(1), m.group(2), m.group(3)
        except Exception:
            pass

    n_err = n_warn = n_lines = 0
    if "vpn_error_log.txt" in names:
        try:
            text = inner.read("vpn_error_log.txt").decode("utf-8", "replace")
        except Exception:
            text = ""
        for ln in text.splitlines():
            m = LINE.match(ln)
            if not m:
                continue
            ts, frac, level, scope, msg = m.groups()
            label = scope.strip() + ": " + norm(msg)
            st = types[(level, label)]
            st["events"] += 1
            st["users"].add(user_id)
            if not st["first"] or ts < st["first"]:
                st["first"] = ts
            if ts > st["last"]:
                st["last"] = ts
            n_lines += 1
            total[level] += 1
            if level == "Error":
                by_day[ts[:10].replace("/", "-")] += 1
                n_err += 1
            elif level == "Warning":
                n_warn += 1

    u = users.setdefault(user_id, {"os": os_name, "os_ver": os_ver, "app": app_ver,
                                   "archives": 0, "sessions": 0, "errors": 0, "warnings": 0,
                                   "lines": 0, "access_bytes": 0})
    u["archives"] += 1
    u["sessions"] += len(logs)
    u["errors"] += n_err
    u["warnings"] += n_warn
    u["lines"] += n_lines
    if "vpn_access_log.txt" in names:
        u["access_bytes"] += inner.getinfo("vpn_access_log.txt").file_size

    v = by_version[(os_name, app_ver)]
    v["users"].add(user_id)
    v["errors"] += n_err
    v["lines"] += n_lines

    if n % 100 == 0:
        print(f"  {n}/{len(infos)}, строк {sum(total.values())}", flush=True)

with open(os.path.join(OUT, "log_error_types.csv"), "w", encoding="utf-8", newline="") as f:
    w = csv.writer(f)
    w.writerow(["level", "scope_message", "events", "users", "first_ts", "last_ts"])
    for (level, label), st in sorted(types.items(), key=lambda kv: -kv[1]["events"]):
        w.writerow([level, label, st["events"], len(st["users"]), st["first"], st["last"]])

with open(os.path.join(OUT, "log_users.csv"), "w", encoding="utf-8", newline="") as f:
    w = csv.writer(f)
    w.writerow(["user_id", "os", "os_version", "app_version", "archives", "sessions",
                "errors", "warnings", "lines", "access_bytes"])
    for uid, u in users.items():
        w.writerow([uid, u["os"], u["os_ver"], u["app"], u["archives"], u["sessions"],
                    u["errors"], u["warnings"], u["lines"], u["access_bytes"]])

with open(os.path.join(OUT, "log_by_version.csv"), "w", encoding="utf-8", newline="") as f:
    w = csv.writer(f)
    w.writerow(["os", "app_version", "users", "errors", "lines"])
    for (os_name, app), v in sorted(by_version.items(), key=lambda kv: -kv[1]["errors"]):
        w.writerow([os_name, app, len(v["users"]), v["errors"], v["lines"]])

with open(os.path.join(OUT, "log_by_day.csv"), "w", encoding="utf-8", newline="") as f:
    w = csv.writer(f)
    w.writerow(["date", "errors"])
    for d in sorted(by_day):
        w.writerow([d, by_day[d]])

summary = {
    "archives": len(infos),
    "users": len(users),
    "sessions": sum(u["sessions"] for u in users.values()),
    "lines_total": sum(total.values()),
    "by_level": dict(total.most_common()),
    "error_events": total.get("Error", 0),
    "warning_events": total.get("Warning", 0),
    "error_types": sum(1 for (lvl, _) in types if lvl == "Error"),
    "users_with_errors": sum(1 for u in users.values() if u["errors"]),
    "first_ts": min((s["first"] for (lvl, _), s in types.items() if s["first"]), default=""),
    "last_ts": max((s["last"] for (lvl, _), s in types.items() if s["last"]), default=""),
    "access_log_bytes": sum(u["access_bytes"] for u in users.values()),
}
json.dump(summary, open(os.path.join(OUT, "log_summary.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
