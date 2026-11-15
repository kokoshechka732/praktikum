import collections
import csv
import json
import os
import statistics

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE, "students2.csv")
OUT = os.path.join(BASE, "out")
os.makedirs(OUT, exist_ok=True)

START = "Регистрация заявки"
END_STATES = {"Заявка выполнена", "Заявка отклонена", "Заявка отменена"}

TASK_ACTIVITIES = ("Согласование руководителем", "Дополнительное согласование",
                   "Доработка заявки", "Первичная проверка", "Проверка бюджета",
                   "Исполнение закупки")


def load(path):
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


rows = load(SRC)

procs = collections.defaultdict(list)
for r in rows:
    procs[r["ProcessInstanceId"]].append(r)
for evs in procs.values():
    evs.sort(key=lambda e: int(e["EventIndex"]))

user_roles = collections.defaultdict(set)
for r in rows:
    if r["UserId"] and r["Role"]:
        user_roles[r["UserId"]].add(r["Role"])

roles_by_activity = {}
for act in TASK_ACTIVITIES:
    roles = collections.Counter()
    for evs in procs.values():
        for e in evs:
            if e["EventType"] == "task_completed" and e["ActivityName"] == act:
                roles[e["Role"]] += 1
    roles_by_activity[act] = dict(roles)

checks = {}
checks["events"] = len(rows)
checks["cases"] = len(procs)
checks["unique_event_id"] = len({r["EventId"] for r in rows}) == len(rows)
checks["one_start_per_case"] = all(
    sum(1 for e in evs if e["EventType"] == "process_started") == 1 for evs in procs.values())
checks["index_dense_from_1"] = all(
    [int(e["EventIndex"]) for e in evs] == list(range(1, len(evs) + 1)) for evs in procs.values())
checks["one_end_per_case"] = all(
    sum(1 for e in evs if e["EventType"] == "process_completed") == 1 for evs in procs.values())
checks["first_activity_is_registration"] = all(evs[0]["ActivityName"] == START for evs in procs.values())
checks["last_event_is_end_state"] = all(evs[-1]["ActivityName"] in END_STATES for evs in procs.values())
checks["event_types"] = dict(collections.Counter(r["EventType"] for r in rows))
checks["activities"] = dict(collections.Counter(r["ActivityName"] for r in rows).most_common())
checks["roles_by_activity"] = roles_by_activity
checks["ts_min"] = min(r["Timestamp"] for r in rows)
checks["ts_max"] = max(r["Timestamp"] for r in rows)
checks["distinct_users"] = len({r["UserId"] for r in rows if r["UserId"]})
checks["users_with_several_roles"] = sum(1 for s in user_roles.values() if len(s) > 1)
checks["amount_per_case_constant"] = all(len({e["Amount"] for e in evs}) == 1 for evs in procs.values())
checks["missing_columns"] = [c for c in ("Status", "RequestType", "TaskId_created") if c not in rows[0]]

route_of = {}
for pid, evs in procs.items():
    route_of[pid] = [e["ActivityName"] for e in evs]

variants = collections.Counter()
for route in route_of.values():
    variants[tuple(route)] += 1
n_cases = len(procs)

with open(os.path.join(OUT, "variants.csv"), "w", encoding="utf-8", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["Variant", "Route", "NumberOfCases", "Share"])
    for i, (route, cnt) in enumerate(sorted(variants.items(), key=lambda kv: (-kv[1], kv[0])), 1):
        w.writerow([f"V{i:02d}", " > ".join(route), cnt, f"{cnt / n_cases:.4f}"])

pairs = collections.Counter()
for route in route_of.values():
    for a, b in zip(route, route[1:]):
        if a != b:
            pairs[(a, b)] += 1

with open(os.path.join(OUT, "student_transitions.csv"), "w", encoding="utf-8", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["SourceActivity", "TargetActivity"])
    for (a, b), _ in sorted(pairs.items(), key=lambda kv: (-kv[1], kv[0])):
        w.writerow([a, b])

out_from = collections.Counter()
for (a, b), c in pairs.items():
    out_from[a] += c

with open(os.path.join(OUT, "transitions_freq.csv"), "w", encoding="utf-8", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["SourceActivity", "TargetActivity", "Count", "CasesFromSource", "Probability"])
    for (a, b), c in sorted(pairs.items(), key=lambda kv: (-kv[1], kv[0])):
        w.writerow([a, b, c, out_from[a], f"{c / out_from[a]:.4f}"])

pos_first = collections.Counter()
pos_last = collections.Counter()
for route in route_of.values():
    pos_first[route[0]] += 1
    pos_last[route[-1]] += 1

fulfilled = sum(1 for r in route_of.values() if r[-1] == "Заявка выполнена")
act_rows = []
for act in checks["activities"]:
    occ = [route.count(act) for route in route_of.values()]
    cases = sum(1 for x in occ if x)
    act_rows.append({
        "Activity": act,
        "Events": checks["activities"][act],
        "Cases": cases,
        "ShareOfCases": round(cases / n_cases, 4),
        "MaxRepeatsInCase": max(occ),
        "CasesWithRepeat": sum(1 for x in occ if x > 1),
        "Role": ",".join(sorted(checks["roles_by_activity"].get(act, {}))),
        "ShareOfFulfilled": round(
            sum(1 for r in route_of.values() if act in r and r[-1] == "Заявка выполнена")
            / max(1, fulfilled), 4),
    })
act_rows.sort(key=lambda d: -d["Cases"])

with open(os.path.join(OUT, "activity_stats.csv"), "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(act_rows[0]))
    w.writeheader()
    w.writerows(act_rows)

branch = "Дополнительное согласование"
with_appr = []
without_appr = []
for evs in procs.values():
    amount = float(evs[0]["Amount"])
    if any(e["ActivityName"] == branch for e in evs):
        with_appr.append(amount)
    else:
        without_appr.append(amount)

sweep = []
for thr in range(50_000, 400_001, 5_000):
    tp = sum(1 for a in with_appr if a >= thr)
    fn = len(with_appr) - tp
    fp = sum(1 for a in without_appr if a >= thr)
    tn = len(without_appr) - fp
    sweep.append({"threshold": thr, "tp": tp, "fn": fn, "fp": fp, "tn": tn,
                  "accuracy": round((tp + tn) / n_cases, 4),
                  "errors": fp + fn})
best = min(sweep, key=lambda d: (d["errors"], -d["accuracy"]))

with open(os.path.join(OUT, "gateway_amount.csv"), "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(sweep[0]))
    w.writeheader()
    w.writerows(sweep)

overlap = {
    "with_min": round(min(with_appr), 2),
    "with_max": round(max(with_appr), 2),
    "with_median": round(statistics.median(with_appr), 2),
    "without_max": round(max(without_appr), 2),
    "without_median": round(statistics.median(without_appr), 2),
    "without_in_with_range": sum(1 for a in without_appr if min(with_appr) <= a <= max(with_appr)),
    "with_below_with_max": sum(1 for a in with_appr if a <= max(without_appr)),
}

outcome_stats = {}
for outcome in sorted(END_STATES):
    routes = []
    amounts = []
    for pid, route in route_of.items():
        if route[-1] == outcome:
            routes.append(route)
            amounts.append(float(procs[pid][0]["Amount"]))
    outcome_stats[outcome] = {
        "cases": len(routes),
        "share": round(len(routes) / n_cases, 4),
        "amount_median": round(statistics.median(amounts), 2),
        "rework_cases": sum(1 for r in routes if "Доработка заявки" in r),
        "director_cases": sum(1 for r in routes if branch in r),
    }

returned = [e["ActivityName"] for evs in procs.values() for e in evs if e["Result"] == "return"]

loop_stats = {
    "rework_once": sum(1 for r in route_of.values() if r.count("Доработка заявки") == 1),
    "rework_twice": sum(1 for r in route_of.values() if r.count("Доработка заявки") == 2),
    "no_rework": sum(1 for r in route_of.values() if "Доработка заявки" not in r),
    "return_result_cases": len(returned),
    "return_stage": sorted(set(returned)),
}

summary = {
    "invariants": checks,
    "n_variants": len(variants),
    "top_variants": [{"route": list(r), "cases": c, "share": round(c / n_cases, 4)}
                     for r, c in sorted(variants.items(), key=lambda kv: -kv[1])[:10]],
    "transitions": len(pairs),
    "outcomes": outcome_stats,
    "loops": loop_stats,
    "gateway": {"branch": branch, "with": len(with_appr), "without": len(without_appr),
                "best_threshold": best, "overlap": overlap,
                "sweep_head": sorted(sweep, key=lambda d: -d["accuracy"])[:5]},
    "positions_first": dict(pos_first),
    "positions_last": dict(pos_last),
}

with open(os.path.join(OUT, "summary.json"), "w", encoding="utf-8") as fh:
    json.dump(summary, fh, ensure_ascii=False, indent=2)

print(json.dumps({k: summary[k] for k in ("n_variants", "transitions", "outcomes", "loops", "gateway")},
                 ensure_ascii=False, indent=2)[:4000])
print("\ninvariants:", {k: v for k, v in checks.items() if not isinstance(v, dict)})
