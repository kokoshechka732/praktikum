import json
import os
import re

import duckdb

BASE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(BASE, "data")
OUT = os.path.join(BASE, "out")
con = duckdb.connect()
con.execute(f"CREATE VIEW types AS SELECT * FROM read_csv_auto('{OUT}/log_error_types.csv')")
con.execute(f"CREATE VIEW us AS SELECT * FROM read_csv_auto('{OUT}/log_users.csv')")
con.execute(f"CREATE VIEW ver AS SELECT * FROM read_csv_auto('{OUT}/log_by_version.csv')")
con.execute(f"CREATE VIEW day AS SELECT * FROM read_csv_auto('{OUT}/log_by_day.csv')")

s = json.load(open(os.path.join(OUT, "log_summary.json"), encoding="utf-8"))
print("== общее ==")
for k, v in s.items():
    print(f"  {k}: {v}")

print("\n== топ Error-шаблонов ==")
for r in con.sql("""
    SELECT scope_message, events, users,
           round(100.0 * events / (SELECT sum(events) FROM types WHERE level='Error'), 1) AS pct
    FROM types WHERE level='Error' ORDER BY events DESC LIMIT 10
""").fetchall():
    print(f"  {r[1]:>9}  {r[3]:>5}%  users={r[2]:>4}  {r[0][:100]}")

print("\n== классы (по регуляркам) ==")
CLASSES = [
    (r"failed to retrieve response.*(closed pipe|deadline|eof|reset)", "DNS-over-HTTPS не проходит"),
    (r"cannot find the pending request", "DNS: потерян pending-запрос"),
    (r"failed to lookup ip", "DNS: имя не разрешилось"),
    (r"connection was refused", "локальный прокси отказал"),
    (r"proxy/vless/outbound|tunnel", "VLESS-туннель"),
    (r"tls|handshake|certificate|x509", "TLS/сертификат"),
    (r"unauthorized|401|auth", "авторизация"),
    (r"i/o timeout|timeout|deadline exceeded", "таймауты"),
]
rows = con.sql("SELECT scope_message, events, users FROM types WHERE level='Error'").fetchall()
agg = {}
for msg, ev, uu in rows:
    low = msg.lower()
    name = "прочее"
    for pat, cls in CLASSES:
        if re.search(pat, low):
            name = cls
            break
    a = agg.setdefault(name, {"events": 0, "users": 0})
    a["events"] += ev
    a["users"] = max(a["users"], uu)
total_err = sum(a["events"] for a in agg.values())
for name, a in sorted(agg.items(), key=lambda kv: -kv[1]["events"]):
    print(f"  {name:35s} {a['events']:>9}  {100*a['events']/total_err:5.1f}%")

print("\n== концентрация по пользователям (Error) ==")
print(con.sql("""
    WITH u AS (SELECT errors FROM us), r AS (SELECT errors, row_number() OVER (ORDER BY errors DESC) rn,
    count(*) OVER () n FROM u)
    SELECT (SELECT count(*) FROM u WHERE errors=0) zero, (SELECT count(*) FROM u) n,
           (SELECT median(errors) FROM u WHERE errors>0) med_pos,
           (SELECT quantile_cont(errors,0.9) FROM u WHERE errors>0) p90_pos,
           (SELECT quantile_cont(errors,0.99) FROM u WHERE errors>0) p99_pos,
           (SELECT max(errors) FROM u) max_err,
           (SELECT round(100.0*sum(errors)/(SELECT sum(errors) FROM u),1) FROM r WHERE rn <= n*0.01) top1
""").fetchall())

print("\n== по ОС ==")
for r in con.sql("""
    SELECT os, count(*) users, sum(errors) errors, round(avg(errors),0) avg_u,
           sum(CASE WHEN errors>0 THEN 1 ELSE 0 END) with_err
    FROM us GROUP BY os ORDER BY errors DESC
""").fetchall():
    print("  ", r)

print("\n== по версиям (>=10 пользователей) ==")
for r in con.sql("""
    SELECT os, app_version, users, errors, round(errors*1.0/users,0) per_user
    FROM ver WHERE users>=10 ORDER BY per_user DESC LIMIT 10
""").fetchall():
    print("  ", r)

print("\n== по дням ==")
print("  дней:", con.sql("SELECT count(*), min(date), max(date) FROM day").fetchall())
for r in con.sql("SELECT date, errors FROM day ORDER BY errors DESC LIMIT 5").fetchall():
    print("  ", r)

print("\n== на сессию ==")
print(con.sql("""
    SELECT sum(sessions) sessions, sum(errors) errors,
           round(sum(errors)*1.0/sum(sessions),1) err_per_session,
           round(sum(lines)*1.0/sum(sessions),0) lines_per_session
    FROM us
""").fetchall())
