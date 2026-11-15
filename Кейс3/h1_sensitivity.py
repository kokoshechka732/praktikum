import collections
import datetime as dt
import json
import os

import duckdb

BASE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(BASE, "data")
OUT = os.path.join(BASE, "out")
Q = '"'

con = duckdb.connect()
con.execute(f"""CREATE VIEW users AS SELECT id, created_at, trial_used_at FROM read_csv('{D}/users.csv',
    delim=';', header=false, quote='{Q}', null_padding=true, ignore_errors=true, types={{'id':'BIGINT'}},
    names=['id','name','email','password','is_verified','created_at','updated_at','deleted_at','logout_at',
            'trial_used_at','remna_id','remna_short_id','referrer_user_id','referal_balance','role',
            'referral_config_id','dashamail_id','segment_id','ga4_client_id','is_was_guest','beta_tester',
            'appmetrica_device_id','appmetrica_profile_id'])""")
con.execute(f"""CREATE VIEW devices AS SELECT user_id, device_identifier FROM read_csv('{D}/devices.csv',
    delim=';', header=false, quote='{Q}', null_padding=true, ignore_errors=true,
    types={{'user_id':'BIGINT','id':'BIGINT'}},
    names=['id','user_id','device_identifier','device_name','client_type','os','last_seen','in_sub','brand',
            'fcm_push_token','hms_push_token','push_tokens_updated_at'])""")
con.execute(f"""CREATE VIEW cards AS SELECT user_id, card_info FROM read_csv('{D}/saved_payment_methods.csv',
    delim=';', header=false, quote='{Q}', null_padding=true, ignore_errors=true, types={{'user_id':'BIGINT'}},
    names=['id','user_id','payment_method_id','disabled_at','created_at','updated_at','card_info','provider_id'])""")
con.execute(f"""CREATE VIEW sessions AS SELECT user_id, ip_address, user_agent FROM read_csv('{D}/sessions.csv',
    delim=';', header=false, quote='{Q}', null_padding=true, ignore_errors=true,
    types={{'user_id':'BIGINT','id':'BIGINT','device_id':'BIGINT'}},
    names=['id','user_id','device_id','created_at','last_accessed_at','revoked_at','ip_address','user_agent',
            'expired_at'])""")
con.execute(f"""CREATE VIEW orders AS SELECT user_id, status FROM read_csv('{D}/orders.csv',
    delim=';', header=false, quote='{Q}', null_padding=true, ignore_errors=true,
    types={{'user_id':'BIGINT','product_id':'BIGINT'}},
    names=['id','user_id','product_id','amount','status','created_at','updated_at','pre_payment','trial',
            'period_id','provider_id'])""")

interesting = set()
for r in con.sql("""
    SELECT id FROM users WHERE trial_used_at IS NOT NULL
    UNION SELECT user_id FROM orders WHERE status='paid'""").fetchall():
    interesting.add(int(r[0]))


def groups(sql):
    out = []
    for r in con.sql(sql).fetchall():
        out.append(list(r[1]))
    return out


device_groups = groups("""
    SELECT device_identifier, list(user_id) FROM devices
    WHERE regexp_matches(device_identifier, '^[0-9a-f]{8}-[0-9a-f]{4}')
    GROUP BY 1 HAVING count(DISTINCT user_id) BETWEEN 2 AND 10""")
card_groups = groups("""
    SELECT card_info, list(user_id) FROM cards
    WHERE card_info IS NOT NULL AND card_info NOT IN ('', '{}')
    GROUP BY 1 HAVING count(DISTINCT user_id) BETWEEN 2 AND 10""")
ipua_groups = groups("""
    SELECT ip_address || '|' || coalesce(user_agent,''), list(user_id)
    FROM sessions
    WHERE ip_address IS NOT NULL AND ip_address NOT IN ('', '0.0.0.0')
    GROUP BY 1 HAVING count(DISTINCT user_id) BETWEEN 2 AND 4""")

profile = {}
for r in con.sql("SELECT id, created_at, trial_used_at FROM users").fetchall():
    profile[int(r[0])] = (r[1], r[2])
paid = set()
for r in con.sql("SELECT DISTINCT user_id FROM orders WHERE status='paid'").fetchall():
    paid.add(int(r[0]))


def clusters(groups_list):
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra = find(a)
        rb = find(b)
        if ra != rb:
            parent[rb] = ra

    for _, groups_ in groups_list:
        for members in groups_:
            members = [int(m) for m in members]
            for other in members[1:]:
                union(members[0], other)

    comp = collections.defaultdict(set)
    for uid in list(parent):
        comp[find(uid)].add(uid)

    trials = 0
    payers = 0
    seq_clusters = 0
    multi_trial = 0
    for members in comp.values():
        t = [m for m in members if profile.get(m, (None, None))[1] is not None]
        trials += len(t)
        payers += sum(1 for m in members if m in paid)
        if len(t) >= 2:
            multi_trial += 1
        creates = sorted(profile[m][0] for m in members if m in profile)
        trial_times = sorted(profile[m][1] for m in t)
        if len(t) >= 2:
            naive = [x.replace(tzinfo=None) if x.tzinfo else x for x in trial_times]
            cr = [x.replace(tzinfo=None) if x.tzinfo else x for x in creates]
            if any(tt <= c <= tt + dt.timedelta(days=14) for tt in naive for c in cr):
                seq_clusters += 1
    return {
        "clusters": len(comp),
        "users": sum(len(v) for v in comp.values()),
        "trial_users": trials,
        "payers": payers,
        "clusters_2plus_trials": multi_trial,
        "clusters_sequential": seq_clusters,
    }


variants = {
    "card+device": [("card", card_groups), ("device", device_groups)],
    "card+device+ipua": [("card", card_groups), ("device", device_groups), ("ipua", ipua_groups)],
    "ipua_only": [("ipua", ipua_groups)],
}
result = {
    "signal_groups": {"card": len(card_groups), "device": len(device_groups), "ipua": len(ipua_groups)},
    "interesting_users": len(interesting),
    "trials_total": sum(1 for v in profile.values() if v[1] is not None),
}
for name, gl in variants.items():
    result[name] = clusters(gl)
    print(name, result[name])

base_trials = result["card+device"]["trial_users"]
full_trials = result["card+device+ipua"]["trial_users"]
result["delta"] = {
    "trial_users_added_by_ipua": full_trials - base_trials,
    "share_base": round(base_trials / result["trials_total"], 4),
    "share_with_ipua": round(full_trials / result["trials_total"], 4),
    "note": "IP+User-Agent — слабый признак: мобильные операторы используют NAT, поэтому "
            "группы 2–4 пользователя могут быть попутчиками, а не одним человеком. "
            "Базовый граф (карта + UUID устройства) даёт нижнюю оценку, расширенный — верхнюю.",
}
result["abuse_cost_estimate"] = {
    "trials_in_clusters": base_trials,
    "lite_month_price_units": 249,
    "units_per_trial_day": round(249 / 30, 2),
    "lost_units_base": round(base_trials * 3 * 249 / 30, 1),
    "lost_units_upper": round(full_trials * 3 * 249 / 30, 1),
    "note": "оценка «стоимости» 3-дневного триала по цене месячной подписки Lite (249 в единицах orders.amount)",
}
with open(os.path.join(OUT, "h1_sensitivity.json"), "w", encoding="utf-8") as fh:
    json.dump(result, fh, ensure_ascii=False, indent=2, default=str)
print(json.dumps(result["delta"], ensure_ascii=False, indent=2))
print(json.dumps(result["abuse_cost_estimate"], ensure_ascii=False, indent=2))
