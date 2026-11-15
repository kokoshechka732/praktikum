import collections
import csv
import json
import os
import sys
import datetime as dt

import duckdb

BASE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(BASE, "data")
OUT = os.path.join(BASE, "out")
os.makedirs(OUT, exist_ok=True)

con = duckdb.connect()
con.execute("PRAGMA threads=4")

NAMES = {
    "users": ["id", "name", "email", "password", "is_verified", "created_at", "updated_at", "deleted_at",
              "logout_at", "trial_used_at", "remna_id", "remna_short_id", "referrer_user_id",
              "referal_balance", "role", "referral_config_id", "dashamail_id", "segment_id",
              "ga4_client_id", "is_was_guest", "beta_tester", "appmetrica_device_id",
              "appmetrica_profile_id"],
    "orders": ["id", "user_id", "product_id", "amount", "status", "created_at", "updated_at",
               "pre_payment", "trial", "period_id", "provider_id"],
    "subscribe": ["id", "user_id", "product_id", "expired_time", "created_at", "order_id",
                  "disabled_at", "next_product_id", "pre_payment", "pre_payment_notification",
                  "next_period_id"],
    "transactions": ["id", "order_id", "amount", "payment_link", "status", "raw_response_payment",
                     "created_at", "updated_at"],
    "devices": ["id", "user_id", "device_identifier", "device_name", "client_type", "os", "last_seen",
                "in_sub", "brand", "fcm_push_token", "hms_push_token", "push_tokens_updated_at"],
    "saved_payment_methods": ["id", "user_id", "payment_method_id", "disabled_at", "created_at",
                              "updated_at", "card_info", "provider_id"],
    "adv_view_history": ["id", "user_id", "created_at"],
    "sessions": ["id", "user_id", "device_id", "created_at", "last_accessed_at", "revoked_at",
                 "ip_address", "user_agent", "expired_at"],
    "user_connection_logs": ["id", "user_id", "node_id", "subscribe_id", "created_at"],
    "product": ["id", "name", "gradient_color", "limit_id", "image_url", "tap_url", "created_at",
                "amount", "currency"],
    "product_trial": ["id", "product_id", "amount", "currency", "duration", "enabled",
                      "duration_days"],
    "external_accounts": ["id", "account_id", "service_name", "user_id", "created_at", "raw_info"],
    "referral_history": ["id", "referrer_id", "referal_id", "transaction_id", "accrual", "percentage",
                         "created_at"],
}

KEY_TYPES = {
    "users": {"id": "BIGINT"},
    "orders": {"user_id": "BIGINT", "product_id": "BIGINT"},
    "subscribe": {"id": "BIGINT", "user_id": "BIGINT", "product_id": "BIGINT"},
    "transactions": {},
    "devices": {"user_id": "BIGINT"},
    "saved_payment_methods": {"user_id": "BIGINT"},
    "adv_view_history": {"id": "BIGINT", "user_id": "BIGINT"},
    "user_connection_logs": {"id": "BIGINT", "user_id": "BIGINT"},
    "product": {"id": "BIGINT"},
    "product_trial": {"id": "BIGINT", "product_id": "BIGINT"},
    "external_accounts": {"id": "BIGINT", "user_id": "BIGINT"},
    "referral_history": {"id": "BIGINT"},
}


def view(table, alias=None):
    path = os.path.join(D, table + ".csv")
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    names = "[" + ",".join("'" + n + "'" for n in NAMES[table]) + "]"
    alias = alias or table
    types = {}
    for key in KEY_TYPES.get(table, {}):
        if key in NAMES[table]:
            types[key] = KEY_TYPES[table][key]
    if types:
        types_sql = "{" + ",".join("'" + k + "':'" + v + "'" for k, v in types.items()) + "}"
    else:
        types_sql = "{}"
    sql = ("CREATE OR REPLACE VIEW {} AS SELECT * FROM read_csv('{}', delim=';', header=false, "
           "quote='\"', escape='\"', null_padding=true, ignore_errors=true, names={}, types={})")
    con.execute(sql.format(alias, path, names, types_sql))
    return alias


def rows(sql):
    return con.sql(sql).fetchall()


def one(sql):
    res = con.sql(sql).fetchall()
    return res[0] if res else (None,)


def naive(x):
    if x is None:
        return None
    if getattr(x, "tzinfo", None):
        return x.replace(tzinfo=None)
    return x


def dump_csv(name, header, data):
    with open(os.path.join(OUT, name), "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(data)


def save(name, obj):
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2, default=str)


SUMMARY = {}

view("users")
view("orders")
view("subscribe")
view("transactions")
view("referral_history")
view("product")
view("product_trial")
quality = {
    "users": one("select count(*), min(created_at), max(created_at) from users"),
    "orders": one("select count(*), min(created_at), max(created_at) from orders"),
    "subscribe": one("select count(*), min(created_at), max(created_at) from subscribe"),
    "transactions": one("select count(*), min(created_at), max(created_at) from transactions"),
    "trials": one("select count(*) from users where trial_used_at is not null"),
    "deleted_users": one("select count(*) from users where deleted_at is not null"),
    "guests": one("select count(*) from users where role='guest'"),
    "clients": one("select count(*) from users where role='client'"),
    "appmetrica_filled": one("select count(*) from users where appmetrica_device_id is not null "
                             "and appmetrica_device_id<>''"),
    "products": rows("select id, name, amount from product order by id"),
    "trial_rule": rows("select product_id, duration_days, amount from product_trial"),
    "orders_by_status": rows("select status, count(*), round(sum(amount)) from orders group by 1 order by 2 desc"),
    "transactions_by_status": rows("select status, count(*), round(sum(amount)) from transactions group by 1 order by 2 desc"),
}
SUMMARY["data_quality"] = {}
for k, v in quality.items():
    if isinstance(v, tuple):
        SUMMARY["data_quality"][k] = list(map(str, v))
    else:
        SUMMARY["data_quality"][k] = v
print("== data quality ==")
for k, v in quality.items():
    print(" ", k, v)


def h1_identity():
    view("users")
    view("devices")
    view("saved_payment_methods")
    view("external_accounts")

    dev_kinds = rows("""
        select case when regexp_matches(device_identifier,'^[0-9a-f]{8}-[0-9a-f]{4}') then 'uuid'
                    when device_identifier is null or device_identifier='' then 'empty' else 'buildtag' end kind,
               count(*), count(distinct device_identifier), count(distinct user_id)
        from devices group by 1 order by 2 desc""")
    top_buildtags = rows("""
        select device_identifier, count(distinct user_id) u from devices
        where device_identifier is not null and device_identifier<>''
          and not regexp_matches(device_identifier,'^[0-9a-f]{8}-[0-9a-f]{4}')
        group by 1 order by 2 desc limit 5""")

    edges = []
    dev_groups = rows("""
        select device_identifier, list(user_id) from devices
        where regexp_matches(device_identifier,'^[0-9a-f]{8}-[0-9a-f]{4}')
        group by 1 having count(distinct user_id) between 2 and 10""")
    for did, users in dev_groups:
        for i in range(1, len(users)):
            edges.append((users[0], users[i], "device_uuid"))
    card_groups = rows("""
        select card_info, list(user_id) from saved_payment_methods
        where card_info is not null and card_info<>'' and card_info<>'{}'
        group by 1 having count(distinct user_id) between 2 and 10""")
    for card, users in card_groups:
        for i in range(1, len(users)):
            edges.append((users[0], users[i], "card_fingerprint"))
    ext = one("select count(*) from (select account_id from external_accounts "
              "group by 1 having count(distinct user_id)>1)")

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

    for a, b, signal in edges:
        union(int(a), int(b))

    clusters = collections.defaultdict(set)
    for uid in list(parent):
        clusters[find(uid)].add(uid)

    ids = ",".join(str(u) for c in clusters.values() for u in c)
    profile = {}
    for uid, created, trial, deleted, paid_cnt, paid_sum in rows("""
            select u.id, u.created_at, u.trial_used_at, u.deleted_at,
                   (select count(*) from orders o where o.user_id=u.id and o.status='paid'),
                   (select coalesce(sum(o.amount),0) from orders o where o.user_id=u.id and o.status='paid')
            from users u where u.id in ({})""".format(ids)):
        profile[int(uid)] = (naive(created), naive(trial), naive(deleted), int(paid_cnt),
                             float(paid_sum or 0))

    clusters_out = []
    for root, members in clusters.items():
        trials = [m for m in members if profile.get(m, (None, None))[1] is not None]
        payers = [m for m in members if profile.get(m, (None, None, None, 0))[3] > 0]
        stamps = sorted(profile[m][0] for m in members if profile.get(m))
        if len(stamps) > 1:
            span_days = (stamps[-1] - stamps[0]).days
        else:
            span_days = 0
        seq = 0
        trial_times = sorted(profile[m][1] for m in trials)
        creates = sorted(profile[m][0] for m in members if profile.get(m))
        for t in trial_times:
            seq += sum(1 for c in creates if t <= c <= t + dt.timedelta(days=14))
        chain = seq >= 1 and len(trials) >= 2
        clusters_out.append({
            "cluster_id": min(members), "users": len(members), "trial_users": len(trials),
            "payers": len(payers), "revenue": round(sum(profile[m][4] for m in members), 2),
            "created_span_days": span_days, "sequential_trials": seq, "chain": int(chain),
            "signals": len(set(s for a, b, s in edges if a in members or b in members)),
        })
    clusters_out.sort(key=lambda c: (-c["trial_users"], -c["users"], c["cluster_id"]))

    n_trial = one("select count(*) from users where trial_used_at is not null")[0]
    in_clusters = sum(c["users"] for c in clusters_out)
    trial_in_clusters = sum(c["trial_users"] for c in clusters_out)
    multi_trial_clusters = [c for c in clusters_out if c["trial_users"] >= 2]
    abuse = [c for c in clusters_out if c["chain"]]
    long_span = [c for c in clusters_out if c["created_span_days"] > 365]

    dump_csv("h1_identity_clusters.csv",
             ["cluster_id", "users", "trial_users", "payers", "revenue", "created_span_days",
              "sequential_trials", "chain", "signals"],
             [[c["cluster_id"], c["users"], c["trial_users"], c["payers"], c["revenue"],
               c["created_span_days"], c["sequential_trials"], c["chain"], c["signals"]]
              for c in clusters_out])

    res = {
        "device_identifier_kinds": dev_kinds,
        "device_identifier_trap_top": top_buildtags,
        "device_uuid_groups": len(dev_groups),
        "card_groups": len(card_groups),
        "shared_external_accounts": ext,
        "clusters_2plus": len(clusters_out),
        "users_in_clusters": in_clusters,
        "trials_total": n_trial,
        "trial_users_in_clusters": trial_in_clusters,
        "share_trials_in_clusters": round(trial_in_clusters / n_trial, 4),
        "clusters_with_2plus_trials": len(multi_trial_clusters),
        "clusters_with_sequential_trials": len(abuse),
        "top_clusters": clusters_out[:10],
        "validation": {
            "clusters_span_over_365d": len(long_span),
            "share_span_over_365d": round(len(long_span) / max(1, len(clusters_out)), 4),
            "clusters_single_trial_no_revenue": sum(1 for c in clusters_out
                                                    if c["trial_users"] == 1 and c["revenue"] == 0),
            "note": "device_identifier в этой выгрузке — build-тег Android (AP3A.240905.015.A2 и т.п.), "
                    "поэтому как признак тождества используется только UUID-подобный идентификатор",
        },
        "revenue_in_clusters": round(sum(c["revenue"] for c in clusters_out), 2),
    }
    save("h1_summary.json", res)
    return res


def km(times, events, horizon):
    pairs = sorted(zip(times, events))
    n = len(pairs)
    surv = 1.0
    out = {}
    at_risk = n
    i = 0
    marks = sorted(set(horizon))
    while i < len(pairs) and marks:
        t = pairs[i][0]
        d = 0
        c = 0
        while i < len(pairs) and pairs[i][0] == t:
            if pairs[i][1]:
                d += 1
            else:
                c += 1
            i += 1
        if at_risk > 0 and d:
            surv *= (1 - d / at_risk)
        at_risk -= d + c
        while marks and marks[0] <= t:
            out[marks.pop(0)] = round(surv, 4)
    for m in marks:
        out[m] = round(surv, 4)
    return out


def h3_time_to_purchase():
    view("users")
    view("subscribe")
    view("orders")
    con.execute("""
        CREATE OR REPLACE VIEW purchase AS
        select s.user_id, min(s.created_at) purchased_at
        from subscribe s join users u on u.id = s.user_id
        where s.product_id in (2,3,4,5)
          and not (s.product_id = 5 and u.trial_used_at is not null
                   and s.created_at <= u.trial_used_at + interval 4 day)
        group by 1""")
    cohort = rows("""
        select u.id, u.created_at, u.trial_used_at, p.purchased_at
        from users u left join purchase p on p.user_id = u.id
        where u.created_at >= '2025-05-01' and u.created_at < '2026-07-01'""")
    obs_end = dt.datetime(2026, 9, 29, 12, 17)
    strata = {"trial": ([], []), "no_trial": ([], [])}
    for uid, created, trial, first_paid in cohort:
        if first_paid:
            end = first_paid
        else:
            end = obs_end
        days = (end - created).total_seconds() / 86400
        if days < 0:
            continue
        if trial is not None:
            key = "trial"
        else:
            key = "no_trial"
        strata[key][0].append(days)
        if first_paid:
            strata[key][1].append(1)
        else:
            strata[key][1].append(0)
    horizon = [1, 3, 7, 14, 30, 90, 180]
    res = {"cohort_users": len(cohort), "horizon_days": horizon, "strata": {}}
    surv_rows = []
    for key, pair in strata.items():
        times, events = pair
        s = km(times, events, horizon)
        converted = sum(events)
        paid_days = sorted(x for x, e in zip(times, events) if e)
        if paid_days:
            median_days = paid_days[len(paid_days) // 2]
        else:
            median_days = None
        res["strata"][key] = {
            "users": len(times), "converted": converted,
            "conversion_rate": round(converted / max(1, len(times)), 4),
            "survival_no_purchase": s,
            "median_days_to_purchase": median_days,
        }
        for h in horizon:
            surv_rows.append([key, h, s[h]])
    dump_csv("h3_survival.csv", ["stratum", "horizon_days", "share_without_purchase"], surv_rows)

    payers = one("select count(*) from purchase")[0]
    payers_no_trial = one("""select count(*) from purchase p join users u on u.id=p.user_id
                             where u.trial_used_at is null""")[0]
    trial_to_paid = rows("""
        with t as (select id, trial_used_at from users where trial_used_at is not null)
        select count(*), count(p.user_id),
               round(avg(datediff('day', t.trial_used_at, p.purchased_at)), 1),
               round(median(datediff('day', t.trial_used_at, p.purchased_at)), 1)
        from t left join purchase p on p.user_id = t.id""")[0]
    buckets = rows("""
        with t as (select id, trial_used_at from users where trial_used_at is not null),
             d as (select datediff('day', t.trial_used_at, p.purchased_at) lag
                   from t join purchase p on p.user_id = t.id)
        select case when lag <= 0 then '0 (в день старта триала)'
                    when lag <= 3 then '1-3 дня (в период триала)'
                    when lag <= 7 then '4-7 дней'
                    when lag <= 30 then '8-30 дней'
                    else '31+ дней' end bucket, count(*)
        from d group by 1 order by 2 desc""")
    res.update({
        "payers_total": payers,
        "payers_without_trial": payers_no_trial,
        "share_payers_without_trial": round(payers_no_trial / max(1, payers), 4),
        "trial_users": trial_to_paid[0],
        "trial_users_who_paid": trial_to_paid[1],
        "trial_to_paid_rate": round(trial_to_paid[1] / max(1, trial_to_paid[0]), 4),
        "mean_days_trial_to_payment": trial_to_paid[2],
        "median_days_trial_to_payment": trial_to_paid[3],
        "trial_to_purchase_lag_buckets": buckets,
        "orders_window": one("select min(created_at), max(created_at), count(*) from orders"),
        "subscribe_window": one("select min(created_at), max(created_at), count(*) from subscribe"),
    })
    save("h3_summary.json", res)
    return res


def h4_payments():
    view("orders")
    view("transactions")
    view("product")
    view("subscribe")
    by_product = rows("""
        select o.product_id, p.name, count(*) attempts,
               sum(case when o.status='paid' then 1 else 0 end) paid,
               sum(case when o.status='failed' then 1 else 0 end) failed,
               sum(case when o.status='pending' then 1 else 0 end) pending,
               round(avg(case when o.status='paid' then o.amount end),2) avg_paid_amount
        from orders o left join product p on p.id::varchar=o.product_id::varchar
        group by 1,2 order by 3 desc""")
    by_month = rows("""
        select strftime(created_at,'%Y-%m') m, count(*) n,
               sum(case when status='paid' then 1 else 0 end) paid,
               round(sum(case when status='failed' then 1 else 0 end)*100.0/count(*),1) fail_rate
        from orders group by 1 order by 1""")
    attempts = rows("""
        select attempts, count(*) orders from (
            select o.id, count(t.id) attempts from orders o
            left join transactions t on t.order_id=o.id group by 1) group by 1 order by 1""")
    retry = rows("""
        with a as (select o.id, o.status,
                          sum(case when t.status='failed' then 1 else 0 end) failed_attempts,
                          sum(case when t.status='completed' then 1 else 0 end) ok_attempts
                   from orders o left join transactions t on t.order_id=o.id group by 1,2)
        select case when failed_attempts=0 then '0' when failed_attempts=1 then '1'
                    when failed_attempts between 2 and 3 then '2-3' else '4+' end fails,
               count(*) orders,
               round(sum(case when status='paid' then 1 else 0 end)*100.0/count(*),1) paid_share
        from a group by 1 order by 1""")
    timing = one("""
        select round(median(epoch(updated_at)-epoch(created_at))/60,1),
               round(avg(epoch(updated_at)-epoch(created_at))/60,1), count(*)
        from transactions where status='failed'""")
    orphan = one("""select count(*) from transactions t left join orders o on o.id=t.order_id
                    where o.id is null""")[0]
    dump_csv("h4_payments.csv", ["cut", "label", "value"],
             [["product", "{} ({})".format(r[1], r[0]), r[2]] for r in by_product]
             + [["month", r[0], r[3]] for r in by_month])
    res = {
        "attempts_by_product": by_product,
        "failure_rate_by_month": by_month,
        "attempts_per_order": attempts,
        "paid_share_by_failed_attempts": retry,
        "failed_timeout_minutes": timing,
        "transactions_without_order": orphan,
        "orders_total": one("select count(*) from orders")[0],
        "transactions_total": one("select count(*) from transactions")[0],
        "failed_share": round(one("select sum(case when status='failed' then 1 else 0 end)*1.0/count(*) from transactions")[0], 4),
    }
    save("h4_summary.json", res)
    return res


def h5_funnel():
    view("users")
    view("orders")
    con.execute("""
        CREATE OR REPLACE VIEW purchase AS
        select s.user_id, min(s.created_at) purchased_at
        from subscribe s join users u on u.id = s.user_id
        where s.product_id in (2,3,4,5)
          and not (s.product_id = 5 and u.trial_used_at is not null
                   and s.created_at <= u.trial_used_at + interval 4 day)
        group by 1""")
    funnel = rows("""
        with monthly as (select strftime(created_at,'%Y-%m') m, id, is_verified, trial_used_at from users)
        select m, count(*) registered,
               sum(case when is_verified then 1 else 0 end) verified,
               sum(case when trial_used_at is not null then 1 else 0 end) trials,
               sum(case when id in (select user_id from purchase) then 1 else 0 end) payers
        from monthly group by 1 order by 1""")
    dump_csv("h5_funnel.csv", ["month", "registered", "verified", "trials", "payers"],
             [list(map(str, r)) for r in funnel])
    ref = one("""select count(*) from users where referrer_user_id is not null""")[0]
    ref_paid = one("""select count(distinct u.id) from users u join purchase p on p.user_id=u.id
                      where u.referrer_user_id is not null""")[0]
    nonref_paid = one("""select count(distinct u.id) from users u join purchase p on p.user_id=u.id
                         where u.referrer_user_id is null""")[0]
    nonref_users = one("select count(*) from users where referrer_user_id is null")[0]
    accr = one("select count(*), round(sum(accrual),2) from referral_history")
    res = {
        "funnel_by_month": funnel,
        "referred_users": ref,
        "referred_payers": ref_paid,
        "organic_payers": nonref_paid,
        "referral_accruals": accr,
        "referral_payer_share": round(ref_paid / max(1, ref), 4),
        "organic_payer_share": round(nonref_paid / max(1, nonref_users), 4),
        "nonreferred_users": nonref_users,
    }
    save("h5_summary.json", res)
    return res


def h2_limits():
    FIXED = ["user_connection_logs_02_26.csv", "user_connection_logs_03_04_26.csv",
             "user_connection_logs_05_26.csv", "user_connection_logs_06_26.csv",
             "user_connection_logs_07_26.csv"]
    months = [f for f in FIXED if os.path.exists(os.path.join(D, f))]
    view("users")
    view("subscribe")
    view("orders")
    con.execute("""
        CREATE OR REPLACE VIEW purchase AS
        select s.user_id, min(s.created_at) purchased_at
        from subscribe s join users u on u.id = s.user_id
        where s.product_id in (2,3,4,5)
          and not (s.product_id = 5 and u.trial_used_at is not null
                   and s.created_at <= u.trial_used_at + interval 4 day)
        group by 1""")
    view("adv_view_history")
    adv_users = one("""select count(*), count(distinct user_id), min(created_at), max(created_at)
                        from adv_view_history""")
    adv_tier = rows("""
        with paid as (select distinct user_id from purchase)
        select case when a.user_id in (select user_id from paid) then 'paid' else 'free' end tier,
               count(*) views, count(distinct a.user_id) users,
               round(count(*)*1.0/count(distinct a.user_id),1) views_per_user,
               round(count(*)*1.0/count(distinct cast(a.created_at as date)),1) views_per_day
        from adv_view_history a group by 1 order by 1 desc""")
    adv_daily = rows("""
        with d as (select user_id, cast(created_at as date) dt, count(*) v from adv_view_history group by 1,2)
        select count(*) user_days, round(median(v),1) med, round(quantile_cont(v,0.9),1) p90,
               round(quantile_cont(v,0.99),1) p99, max(v) mx from d""")
    adv_by_month = rows("""
        select strftime(created_at,'%Y-%m') m, count(*) views, count(distinct user_id) users
        from adv_view_history group by 1 order by 1""")
    if not months:
        res = {"adv_views_total": adv_users, "adv_by_tier": adv_tier, "adv_user_day": adv_daily,
               "adv_by_month": adv_by_month,
               "status": "файлы user_connection_logs_* ещё не загружены — блок подключений не посчитан",
               "limitation": "объёма трафика в байтах в выгрузке нет; sub_limit не выгружена"}
        save("h2_summary.json", res)
        return res
    parts = []
    for f in months:
        path = os.path.join(D, f)
        names = "[" + ",".join("'" + n + "'" for n in NAMES["user_connection_logs"]) + "]"
        parts.append("SELECT id::BIGINT AS id, user_id::BIGINT AS user_id, node_id::BIGINT AS node_id, "
                     "subscribe_id::BIGINT AS subscribe_id, created_at "
                     "FROM read_csv('" + path + "', delim=';', header=false, quote='\"', "
                     "null_padding=true, ignore_errors=true, names=" + names + ")")
    con.execute("CREATE OR REPLACE VIEW conn AS " + " UNION ALL ".join(parts))
    daily = rows("""
        with c as (
          select user_id, cast(created_at as date) d, count(*) conns
          from conn group by 1,2),
        sub as (select distinct user_id from purchase),
        marked as (select c.*, case when c.user_id in (select user_id from sub) then 'paid' else 'free' end tier from c)
        select tier, count(*) user_days,
               round(median(conns),1) med, round(quantile_cont(conns,0.9),1) p90,
               round(quantile_cont(conns,0.99),1) p99, round(avg(conns),2) mean,
               round(sum(case when conns=1 then 1 else 0 end)*100.0/count(*),1) share_single
        from marked group by 1 order by 1 desc""")
    dump_csv("h2_limits.csv", ["cut", "label", "value"],
             [["daily", r[0], r[2]] for r in daily] + [["adv", r[0], r[1]] for r in adv_by_month])
    res = {"months_used": months, "connections_per_user_day": daily,
           "adv_views_total": adv_users, "adv_by_tier": adv_tier, "adv_user_day": adv_daily,
           "adv_views_by_month": adv_by_month,
           "limitation": "в выгрузке нет объёма трафика в байтах (user_connection_logs: user, node, "
                         "subscribe, created_at); таблица sub_limit не выгружена — лимиты 500 МБ/сутки "
                         "и 15 ГБ/месяц измеряются только прокси-метриками"}
    save("h2_summary.json", res)
    return res


def main():
    only = None
    if "--only" in sys.argv:
        only = set(sys.argv[sys.argv.index("--only") + 1].split(","))
    steps = [("H1", h1_identity), ("H3", h3_time_to_purchase), ("H4", h4_payments),
             ("H5", h5_funnel), ("H2", h2_limits)]
    for code, fn in steps:
        if only and code not in only:
            continue
        print("\n===== {} =====".format(code))
        try:
            SUMMARY[code] = fn()
            print(json.dumps(SUMMARY[code], ensure_ascii=False, indent=2, default=str)[:3500])
        except Exception as exc:
            SUMMARY[code] = {"error": "{}: {}".format(type(exc).__name__, exc)}
            print("ERROR", exc)
    path = os.path.join(OUT, "summary.json")
    merged = {}
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                merged = json.load(fh)
        except Exception:
            merged = {}
    merged.update(SUMMARY)
    save("summary.json", merged)


if __name__ == "__main__":
    main()
