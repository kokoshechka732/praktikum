import collections
import csv
import json
import os
import random

import pandas as pd
import pm4py

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "out")
SRC = os.path.join(BASE, "students2.csv")
SEED = 1356

with open(SRC, encoding="utf-8-sig", newline="") as fh:
    rows = list(csv.DictReader(fh))

df = pd.DataFrame({
    "case:concept:name": [r["ProcessInstanceId"] for r in rows],
    "concept:name": [r["ActivityName"] for r in rows],
    "time:timestamp": pd.to_datetime([r["Timestamp"] for r in rows], utc=True),
    "EventIndex": [int(r["EventIndex"]) for r in rows],
})
df = df.sort_values(["case:concept:name", "EventIndex"])
log = pm4py.format_dataframe(df, case_id="case:concept:name", activity_key="concept:name",
                             timestamp_key="time:timestamp")

observed = collections.Counter()
for cid in df["case:concept:name"].unique():
    observed[tuple(df[df["case:concept:name"] == cid]["concept:name"])] += 1
observed_share = {}
for v, c in observed.items():
    observed_share[v] = c / sum(observed.values())

result = {"observed_variants": len(observed), "cases": len(observed)}
simulated = {}


def simulate(net, im, fm, seed):
    random.seed(seed)
    traces = pm4py.play_out(net, im, fm, num_traces=5000)
    variants = collections.Counter()
    for t in traces:
        variants[tuple(e["concept:name"] for e in t)] += 1
    return variants


def summarise(name, net, im, fm, seed):
    fit = pm4py.fitness_token_based_replay(log, net, im, fm)
    try:
        prec = pm4py.precision_token_based_replay(log, net, im, fm)
    except Exception as exc:
        prec = f"n/a: {exc}"
    sim_variants = simulate(net, im, fm, seed)
    simulated[name] = sim_variants
    unseen = sum(c for v, c in sim_variants.items() if v not in observed)
    total = sum(sim_variants.values())
    precision = prec
    if isinstance(prec, float):
        precision = round(prec, 4)
    return {
        "model": name,
        "places": len(net.places),
        "transitions": len(net.transitions),
        "silent_transitions": sum(1 for t in net.transitions if t.label is None),
        "fitness_log": round(fit["log_fitness"], 4),
        "fitting_traces": round(fit["percentage_of_fitting_traces"] / 100, 4),
        "precision": precision,
        "simulated_traces": total,
        "distinct_simulated_variants": len(sim_variants),
        "share_simulated_unseen_in_log": round(unseen / max(1, total), 4),
    }


net_i, im_i, fm_i = pm4py.discover_petri_net_inductive(log, noise_threshold=0.2)
result["inductive_miner"] = summarise("Inductive Miner (noise 0.2)", net_i, im_i, fm_i, SEED)

try:
    net_h, im_h, fm_h = pm4py.discover_petri_net_heuristics(log)
    result["heuristic_miner"] = summarise("Heuristic Miner", net_h, im_h, fm_h, SEED)
except Exception as exc:
    result["heuristic_miner"] = {"model": "Heuristic Miner", "error": str(exc)}

manual = set()


def walk(prefix, reworks):
    manual.add(tuple(prefix + ["Заявка отклонена"]))
    head = prefix + ["Согласование руководителем"]
    manual.add(tuple(head + ["Заявка отклонена"]))
    manual.add(tuple(head + ["Заявка отменена"]))
    if reworks < 2:
        walk(head + ["Доработка заявки", "Первичная проверка"], reworks + 1)
    base = head + ["Проверка бюджета"]
    manual.add(tuple(base + ["Исполнение закупки", "Заявка выполнена"]))
    manual.add(tuple(base + ["Дополнительное согласование", "Исполнение закупки", "Заявка выполнена"]))


walk(["Регистрация заявки", "Первичная проверка"], 0)

manual_in_log = [v for v in manual if v in observed]
result["manual_model"] = {
    "model": "Ручная модель (варианты + наблюдённые развилки)",
    "enumerated_variants": len(manual),
    "variants_present_in_log": len(manual_in_log),
    "share_present_in_log": round(len(manual_in_log) / max(1, len(manual)), 4),
    "coverage_of_log": round(sum(observed_share[v] for v in manual_in_log), 4),
    "note": "цикл доработки ограничен двумя повторами",
}

with open(os.path.join(OUT, "bonus_simulated_variants.csv"), "w", encoding="utf-8", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["Model", "Route", "SimulatedCount", "PresentInLog"])
    for route, c in simulated["Inductive Miner (noise 0.2)"].most_common(20):
        w.writerow(["Inductive Miner", " > ".join(route), c, route in observed])

with open(os.path.join(OUT, "bonus_models.json"), "w", encoding="utf-8") as fh:
    json.dump(result, fh, ensure_ascii=False, indent=2)
print(json.dumps(result, ensure_ascii=False, indent=2))
