import collections
import csv
import datetime as dt
import json
import os
import statistics

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE, "students1.csv")
OUT = os.path.join(BASE, "out")
os.makedirs(OUT, exist_ok=True)

TZ = dt.timezone(dt.timedelta(hours=3))
SLICE = dt.datetime(2026, 7, 1, 0, 0, tzinfo=TZ)
WORK_START = 9
WORK_END = 18

EXPECTED_ROLE = {
    "Проверка заявки": "specialist",
    "Согласование руководителем": "manager",
    "Согласование бюджета": "finance",
    "Проверка договора": "legal",
    "Исполнение заявки": "procurement",
    "Доработка заявки": "requester",
    "Внеплановая проверка": "auditor",
}


def ts(s):
    return dt.datetime.fromisoformat(s)


def work_hours(t0, t1):
    total = 0.0
    day = t0.date()
    while day <= t1.date():
        if day.weekday() < 5:
            start = dt.datetime.combine(day, dt.time(WORK_START), tzinfo=TZ)
            end = dt.datetime.combine(day, dt.time(WORK_END), tzinfo=TZ)
            a = max(t0, start)
            b = min(t1, end)
            if b > a:
                total += (b - a).total_seconds() / 3600
        day += dt.timedelta(days=1)
    return total


with open(SRC, encoding="utf-8-sig", newline="") as fh:
    rows = list(csv.DictReader(fh))

P = collections.defaultdict(list)
for r in rows:
    P[r["ProcessInstanceId"]].append(r)
for evs in P.values():
    evs.sort(key=lambda e: int(e["EventIndex"]))

meta = {}
for pid, evs in P.items():
    first = evs[0]
    meta[pid] = {
        "type": first["RequestType"],
        "amount": float(first["Amount"]),
        "requester": first["UserId"],
        "start": ts(first["Timestamp"]),
    }

finished = {}
outcome = {}
for pid, evs in P.items():
    for e in evs:
        if e["EventType"] == "process_completed":
            finished[pid] = evs
            outcome[pid] = e["Result"]
            break

fulfilled = set()
for pid in outcome:
    if outcome[pid] == "fulfilled":
        fulfilled.add(pid)

tc_names = {}
for pid, evs in P.items():
    tc_names[pid] = [e["ActivityName"] for e in evs if e["EventType"] == "task_completed"]

durations = []
open_tasks = []
for pid, evs in P.items():
    created = {}
    for e in evs:
        if e["EventType"] == "task_created":
            created[e["TaskId"]] = e
    closed = set()
    for e in evs:
        if e["EventType"] == "task_completed" and e["TaskId"] in created:
            c = created[e["TaskId"]]
            cal = (ts(e["Timestamp"]) - ts(c["Timestamp"])).total_seconds() / 3600
            wh = work_hours(ts(c["Timestamp"]), ts(e["Timestamp"]))
            durations.append((pid, e["ActivityName"], e["TaskId"], cal, wh, e["UserId"], e["Role"]))
            closed.add(e["TaskId"])
    for tid, c in created.items():
        if tid not in closed:
            age = (SLICE - ts(c["Timestamp"])).total_seconds() / 3600
            open_tasks.append((pid, c["ActivityName"], tid, age, meta[pid]["type"]))

roles_of_user = collections.defaultdict(set)
for r in rows:
    if r["UserId"] and r["Role"]:
        roles_of_user[r["UserId"]].add(r["Role"])

users_multi_role = 0
for u, s in roles_of_user.items():
    if len(s) > 1:
        users_multi_role += 1

one_start_per_case = True
index_dense = True
time_order_ok = True
for evs in P.values():
    if sum(1 for e in evs if e["EventType"] == "process_started") != 1:
        one_start_per_case = False
    if [int(e["EventIndex"]) for e in evs] != list(range(1, len(evs) + 1)):
        index_dense = False
    times = [ts(e["Timestamp"]) for e in evs]
    for i in range(1, len(times)):
        if times[i - 1] > times[i]:
            time_order_ok = False

event_ids = set()
for r in rows:
    event_ids.add(r["EventId"])

neg_durations = 0
for d in durations:
    if d[3] < 0:
        neg_durations += 1

after_slice_events = 0
after_slice_cases = set()
for r in rows:
    if ts(r["Timestamp"]) > SLICE:
        after_slice_events += 1
        after_slice_cases.add(r["ProcessInstanceId"])

users = set()
for r in rows:
    if r["UserId"]:
        users.add(r["UserId"])

checks = {
    "events": len(rows),
    "cases": len(P),
    "unique_event_id": len(event_ids) == len(rows),
    "one_start_per_case": one_start_per_case,
    "index_dense": index_dense,
    "time_order_matches_index": time_order_ok,
    "duration_negative": neg_durations,
    "events_after_slice": after_slice_events,
    "cases_after_slice": len(after_slice_cases),
    "open_cases": len(P) - len(finished),
    "open_tasks": len(open_tasks),
    "users": len(users),
    "users_with_several_roles": users_multi_role,
    "ts_min": min(r["Timestamp"] for r in rows),
    "ts_max": max(r["Timestamp"] for r in rows),
}

cohort = collections.defaultdict(list)
cohort_work = collections.defaultdict(list)
for pid, act, tid, cal, wh, uid, role in durations:
    cohort[(meta[pid]["type"], act)].append(cal)
    cohort_work[(meta[pid]["type"], act)].append(wh)


def pct(v, q):
    v = sorted(v)
    return v[min(len(v) - 1, int(q * len(v)))]


def mad(v):
    m = statistics.median(v)
    return statistics.median([abs(x - m) for x in v])


base_rows = []
for key in sorted(cohort):
    rtype, act = key
    v = cohort[key]
    base_rows.append({
        "RequestType": rtype,
        "Activity": act,
        "N": len(v),
        "Median_cal_h": round(statistics.median(v), 2),
        "P90_cal_h": round(pct(v, 0.90), 2),
        "P99_cal_h": round(pct(v, 0.99), 2),
        "Max_cal_h": round(max(v), 2),
        "Median_work_h": round(statistics.median(cohort_work[key]), 2),
        "MAD_cal_h": round(mad(v), 2),
    })

with open(os.path.join(OUT, "baseline_durations.csv"), "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(base_rows[0]))
    w.writeheader()
    w.writerows(base_rows)

activities = set()
for evs in P.values():
    for e in evs:
        if e["EventType"] == "task_completed":
            activities.add(e["ActivityName"])

role_rows = []
for act in sorted(activities):
    c = collections.Counter(e["Role"] for evs in P.values() for e in evs
                            if e["EventType"] == "task_completed" and e["ActivityName"] == act)
    roles_obs = ", ".join(f"{k or '—'}={v}" for k, v in c.most_common())
    role_rows.append({
        "Activity": act,
        "ExpectedRole": EXPECTED_ROLE.get(act, ""),
        "RolesObserved": roles_obs,
        "Events": sum(c.values()),
    })

with open(os.path.join(OUT, "roles_by_activity.csv"), "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(role_rows[0]))
    w.writeheader()
    w.writerows(role_rows)

manager_share = {}
for t in ["urgent", "contract", "standard"]:
    done = [pid for pid in fulfilled if meta[pid]["type"] == t]
    with_mgr = [pid for pid in done if "Согласование руководителем" in tc_names[pid]]
    manager_share[t] = round(len(with_mgr) / max(1, len(done)), 4)

cand = []


def add(pid, atype, expl, severity, rule):
    cand.append({
        "ProcessInstanceId": pid,
        "AnomalyType": atype,
        "Explanation": expl,
        "Severity": severity,
        "Rule": rule,
    })


r1 = []
for pid in fulfilled:
    if "Согласование руководителем" not in tc_names[pid]:
        r1.append(pid)
for pid in r1:
    route = " > ".join(tc_names[pid])
    share = manager_share[meta[pid]["type"]] * 100
    add(pid, "Пропуск обязательного согласования",
        f"Заявка исполнена без этапа «Согласование руководителем»: маршрут "
        f"{route}. Ни одного задания руководителя в истории нет. "
        f"В когорте {meta[pid]['type']} руководитель участвует в "
        f"{share:.1f} % исполненных заявок.",
        1, "R1")

r2 = []
for pid, evs in P.items():
    seq = [e["ActivityName"] for e in evs if e["EventType"] == "task_completed"]
    first = {}
    for i, a in enumerate(seq):
        if a not in first:
            first[a] = i
    if "Согласование бюджета" in first and "Исполнение заявки" in first:
        if first["Исполнение заявки"] < first["Согласование бюджета"]:
            r2.append(pid)
for pid in r2:
    t = {}
    for e in P[pid]:
        if e["EventType"] == "task_completed":
            t[e["ActivityName"]] = e["Timestamp"]
    extra = ""
    if "Проверка договора" in t and t["Исполнение заявки"] < t["Проверка договора"]:
        extra = f" Юридическая проверка закрыта ещё позже — {t['Проверка договора'][:16]}."
    add(pid, "Нарушен порядок этапов",
        f"«Исполнение заявки» закрыто {t['Исполнение заявки'][:16]}, а «Согласование бюджета» — "
        f"только {t['Согласование бюджета'][:16]}: бюджет утверждён после фактического исполнения.{extra} "
        f"Для когорты {meta[pid]['type']} обратный порядок не встречается.",
        1, "R2")

mgr_closures = 0
for evs in P.values():
    for e in evs:
        if e["EventType"] != "task_completed":
            continue
        if e["ActivityName"] != "Согласование руководителем":
            continue
        if e["Role"] == "manager":
            mgr_closures += 1

r3 = []
for pid, evs in P.items():
    for e in evs:
        if e["EventType"] != "task_completed":
            continue
        if e["ActivityName"] != "Согласование руководителем":
            continue
        if e["Role"] == "manager":
            continue
        r3.append(pid)
        add(pid, "Этап выполнен не тем исполнителем",
            f"«Согласование руководителем» закрыто пользователем {e['UserId']} в роли "
            f"{e['Role']} (ожидается manager), задача {e['TaskId']}. Все остальные "
            f"{mgr_closures} закрытий этого этапа в журнале выполнены ролью manager.",
            1, "R3")
        if e["UserId"] == meta[pid]["requester"]:
            add(pid, "Самосогласование (нарушение четырёх глаз)",
                f"Инициатор заявки {meta[pid]['requester']} сам закрыл этап «Согласование руководителем» "
                f"{e['Timestamp'][:16]}: решение по своей же заявке принято без второго участника.",
                1, "R3b")

r4 = []
for pid, act, tid, cal, wh, uid, role in durations:
    key = (meta[pid]["type"], act)
    v_wh = cohort_work[key]
    med_wh = statistics.median(v_wh)
    thr_wh = max(med_wh + 10 * mad(v_wh), 8.0)
    if wh > thr_wh:
        r4.append(pid)
        started = [e["Timestamp"][11:16] for e in P[pid]
                   if e["TaskId"] == tid and e["EventType"] == "task_created"][0]
        add(pid, "Зависшее задание",
            f"Задание «{act}» (TaskId {tid}, исполнитель {uid}) заняло {wh:.0f} рабочих ч "
            f"({wh / 9:.1f} раб. дня, календарно {cal:.0f} ч) — в {wh / max(med_wh, 0.01):.0f} раза "
            f"дольше медианы когорты {key[0]}×{act} = {med_wh:.2f} раб. ч "
            f"(порог медиана + 10·MAD = {thr_wh:.1f} раб. ч, p99 когорты = {pct(v_wh, 0.99):.1f} раб. ч). "
            f"Задание стартовало в "
            f"{started}.",
            2, "R4")

r5 = []
for pid, evs in P.items():
    seq = [e for e in evs if e["EventType"] == "task_completed"]
    for i in range(1, len(seq)):
        a = seq[i - 1]
        b = seq[i]
        if a["ActivityName"] == "Проверка заявки" and b["ActivityName"] == "Проверка заявки":
            r5.append(pid)
            gap = (ts(b["Timestamp"]) - ts(a["Timestamp"])).total_seconds() / 60
            add(pid, "Повторное выполнение этапа без основания",
                f"Две проверки подряд: {a['Timestamp'][:16]} и {b['Timestamp'][:16]} "
                f"(исполнители {a['UserId']} и {b['UserId']}, разные задания), интервал "
                f"{gap:.0f} мин. Между ними нет ни возврата от руководителя, ни доработки — "
                f"в обязательном маршруте повторная проверка возможна только после доработки.",
                3, "R5")

cycle = []
for pid, evs in finished.items():
    end = None
    for e in evs:
        if e["EventType"] == "process_completed":
            end = e["Timestamp"]
            break
    cycle.append((ts(end) - meta[pid]["start"]).total_seconds() / 3600)
cycle_p99 = pct(cycle, 0.99)

r6 = []
for pid, act, tid, cal, rtype in open_tasks:
    age_days = (SLICE - meta[pid]["start"]).total_seconds() / 86400
    if age_days * 24 > cycle_p99:
        r6.append(pid)
        add(pid, "Зависшая заявка (открыта на срез)",
            f"Заявка открыта {meta[pid]['start'].date()} и не завершена на срез: "
            f"{age_days:.0f} дней (p99 полного цикла завершённых заявок = {cycle_p99 / 24:.1f} дн., "
            f"медиана {statistics.median(cycle) / 24:.1f} дн.). Последнее событие — «{act}» "
            f"(TaskId {tid}) не закрыто; для длительности задания известна только нижняя граница "
            f"{cal / 24 / 30:.0f} мес.",
            3, "R6")

r7 = []
for pid, evs in P.items():
    for e in evs:
        if e["ActivityName"] == "Внеплановая проверка":
            r7.append(pid)
            break
for pid in r7:
    aud = [e for e in P[pid] if e["EventType"] == "task_completed"
           and e["ActivityName"] == "Внеплановая проверка"]
    add(pid, "Внеплановая проверка (требует обоснования)",
        f"В маршруте {len(aud)} задания аудитора ({', '.join(e['Timestamp'][:16] for e in aud)}) — "
        f"этап вне обязательного маршрута; таких заявок 8 из 1000 ({0.8:.1f} %). Редкость сама по себе "
        f"не доказывает нарушения: сумма {meta[pid]['amount']:.0f}, тип {meta[pid]['type']}, "
        f"результат — исполнена. Нужно подтверждение основания проверки.",
        4, "R7")

rejected = []

contract_all = [pid for pid, evs in P.items() if meta[pid]["type"] == "contract"]
contract_wo_legal_all = [pid for pid in contract_all if "Проверка договора" not in tc_names[pid]]
contract_wo_legal_fulfilled = [pid for pid in contract_wo_legal_all if pid in fulfilled]
rejected.append({
    "Rule": "Договорная заявка без юридической проверки",
    "Fired": len(contract_wo_legal_all),
    "AfterScoping": len(contract_wo_legal_fulfilled),
    "Why": "все срабатывания — заявки, отклонённые/возвращённые руководителем до этапа юриста",
})

rejected.append({
    "Rule": "Открытая заявка на срез как аномалия",
    "Fired": len(P) - len(finished),
    "AfterScoping": len(r6),
    "Why": "по условию задачи открытая заявка — не аномалия; оставлены только те, что открыты дольше p99 цикла",
})

amt_out = 0
by_type = collections.defaultdict(list)
for pid, m in meta.items():
    by_type[m["type"]].append(m["amount"])
for t, v in by_type.items():
    v = sorted(v)
    q1 = v[len(v) // 4]
    q3 = v[3 * len(v) // 4]
    iqr = q3 - q1
    amt_out += sum(1 for x in v if x > q3 + 3 * iqr or x < q1 - 3 * iqr)
rejected.append({
    "Rule": "Аномальная сумма заявки (Тьюки, 3·IQR внутри типа)",
    "Fired": amt_out,
    "AfterScoping": 0,
    "Why": "в описании нет финансовых порогов согласования; выбросы суммы не образуют проверяемого нарушения",
})

rejected.append({
    "Rule": "События после объявленного среза",
    "Fired": checks["events_after_slice"],
    "AfterScoping": 0,
    "Why": "это дефект выгрузки, а не поведение процесса: 25 событий в 10 заявках после 2026-07-01 00:00; отражено в разделе ограничений",
})

role_mismatch = 0
for pid, act, tid, cal, wh, uid, role in durations:
    if role != EXPECTED_ROLE.get(act, role):
        role_mismatch += 1
rejected.append({
    "Rule": "Роль на этапе не совпадает с ожидаемой (все этапы)",
    "Fired": role_mismatch,
    "AfterScoping": len(r3),
    "Why": "единственное расхождение — «Согласование руководителем»; на остальных этапах роль всегда соответствует",
})

returns = 0
for evs in P.values():
    for e in evs:
        if e["Result"] in ("return", "reject"):
            returns += 1
rejected.append({
    "Rule": "Возвраты и отказы как аномалия",
    "Fired": returns,
    "AfterScoping": 0,
    "Why": "штатная ветка бизнес-процесса: 173 возврата и 51 отказ, все на этапе руководителя",
})

with open(os.path.join(OUT, "rejected_rules.csv"), "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=["Rule", "Fired", "AfterScoping", "Why"])
    w.writeheader()
    w.writerows(rejected)

cand.sort(key=lambda c: (c["Severity"], c["Rule"], c["ProcessInstanceId"]))
seen = set()
final = []
for c in cand:
    key = (c["ProcessInstanceId"], c["AnomalyType"])
    if key in seen:
        continue
    seen.add(key)
    final.append(c)

with open(os.path.join(BASE, "anomalies.csv"), "w", encoding="utf-8", newline="") as fh:
    w = csv.writer(fh, quoting=csv.QUOTE_MINIMAL)
    w.writerow(["ProcessInstanceId", "AnomalyType", "Explanation"])
    for c in final:
        w.writerow([c["ProcessInstanceId"], c["AnomalyType"], c["Explanation"]])

with open(os.path.join(OUT, "candidates.csv"), "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=["ProcessInstanceId", "AnomalyType", "Explanation", "Severity", "Rule"])
    w.writeheader()
    w.writerows(final)

r1_long = 0
for p in r1:
    if p in r4:
        r1_long += 1

open_bounds = []
for pid, act, tid, cal, rtype in open_tasks:
    open_bounds.append({"pid": pid, "activity": act, "days_open": round(cal / 24 / 30 * 30, 1)})

summary = {
    "invariants": checks,
    "baseline_rows": len(base_rows),
    "manager_share_fulfilled_by_type": manager_share,
    "cycle_hours": {
        "median": round(statistics.median(cycle), 1),
        "p99": round(cycle_p99, 1),
        "max": round(max(cycle), 1),
    },
    "groups": {
        "R1_no_manager": len(r1),
        "R1_subset_long_check": r1_long,
        "R2_order": len(r2),
        "R3_wrong_executor": len(r3),
        "R4_long_task": len(r4),
        "R5_double_check": len(r5),
        "R6_stalled_open": len(r6),
        "R7_audit": len(r7),
    },
    "rows": len(final),
    "unique_cases": len({c["ProcessInstanceId"] for c in final}),
    "by_type": dict(collections.Counter(c["AnomalyType"] for c in final)),
    "rejected": rejected,
    "open_task_lower_bounds": open_bounds,
}

with open(os.path.join(OUT, "summary.json"), "w", encoding="utf-8") as fh:
    json.dump(summary, fh, ensure_ascii=False, indent=2)

ids = set(P)
for c in final:
    assert c["ProcessInstanceId"] in ids
pairs = {(c["ProcessInstanceId"], c["AnomalyType"]) for c in final}
assert len(pairs) == len(final)
with open(os.path.join(BASE, "anomalies.csv"), encoding="utf-8") as fh:
    got = next(csv.reader(fh))
assert got == ["ProcessInstanceId", "AnomalyType", "Explanation"], got

print(json.dumps({k: summary[k] for k in ("groups", "rows", "unique_cases", "by_type", "cycle_hours")},
                 ensure_ascii=False, indent=2))
print("\ninvariants:", checks)
print("rejected:", [(r["Rule"], r["Fired"], r["AfterScoping"]) for r in rejected])
