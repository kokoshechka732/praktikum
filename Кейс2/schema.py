import csv
import json
import math
import os
import textwrap

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "out")

W, H = 1480, 815
FONT = "Segoe UI, Arial, sans-serif"
BW = 170

NODES = {
    "A":  (25, 100, BW, 72, "Регистрация заявки", "system", "auto"),
    "B":  (275, 100, BW, 72, "Первичная проверка", "specialist", "task"),
    "C":  (525, 100, BW, 72, "Согласование руководителем", "manager", "task"),
    "D":  (775, 100, BW, 72, "Проверка бюджета", "finance", "task"),
    "F":  (1025, 100, BW, 72, "Исполнение закупки", "procurement", "task"),
    "G":  (1275, 100, BW, 72, "Заявка выполнена", "end", "end"),
    "R":  (525, 300, BW, 72, "Доработка заявки", "requester", "task"),
    "X2": (775, 300, BW, 72, "Заявка отменена", "end", "endbad"),
    "E":  (1025, 300, BW, 72, "Дополнительное согласование", "director", "hypo"),
    "X1": (275, 470, BW, 72, "Заявка отклонена", "end", "endbad"),
}

EDGES = [
    ("A", "B", [(195, 136), (275, 136)], "1 000|100 %", "main"),
    ("B", "C", [(445, 136), (525, 136)], "1 129|96,2 %", "main"),
    ("B", "X1", [(325, 172), (325, 470)], "45|3,8 %", "alt"),
    ("C", "D", [(695, 136), (775, 136)], "911|80,7 %", "main"),
    ("C", "R", [(600, 172), (600, 300)], "174|15,4 %", "alt"),
    ("R", "B", [(525, 336), (495, 336), (495, 205), (425, 205), (425, 172)], "174|100 %", "loop"),
    ("C", "X1", [(680, 172), (680, 225), (410, 225), (410, 470)], "18|1,6 %", "alt"),
    ("C", "X2", [(665, 172), (665, 250), (860, 250), (860, 300)], "26|2,3 %", "alt"),
    ("D", "F", [(945, 136), (1025, 136)], "702|77,1 %", "main"),
    ("D", "E", [(900, 172), (900, 265), (1060, 265), (1060, 300)], "209|22,9 %", "hypo"),
    ("E", "F", [(1110, 300), (1110, 172)], "209|100 %", "hypo"),
    ("F", "G", [(1195, 136), (1275, 136)], "911|100 %", "main"),
]

STYLE = {
    "auto": ("#eef4ff", "#5b8def"),
    "task": ("#ffffff", "#3c4a5c"),
    "end": ("#eaf7ee", "#3fa96a"),
    "endbad": ("#fdeeee", "#d97070"),
    "hypo": ("#fffbe8", "#d0a53a"),
}

ARROW = {"main": ("#2f3b4a", 2.2, ""), "alt": ("#7a8899", 1.4, ""),
         "loop": ("#5b8def", 1.9, ""), "hypo": ("#c9962c", 1.8, "6 4")}


def wrap(text, width=16):
    return textwrap.wrap(text, width=width) or [text]


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def box(node_id):
    x, y, w, h, label, role, kind = NODES[node_id]
    fill, stroke = STYLE[kind]
    dash = ""
    if kind == "hypo":
        dash = ' stroke-dasharray="7 5"'
    lines = wrap(label)
    out = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="{fill}" '
           f'stroke="{stroke}" stroke-width="2"{dash}/>']
    base_y = y + h / 2 - (len(lines) - 1) * 8 - (7 if role != "end" else 0)
    for i, ln in enumerate(lines):
        out.append(f'<text x="{x + w / 2}" y="{base_y + i * 17 + 4}" text-anchor="middle" '
                   f'font-family="{FONT}" font-size="13" font-weight="600" fill="#1b2430">{esc(ln)}</text>')
    if role != "end":
        out.append(f'<text x="{x + w / 2}" y="{y + h - 10}" text-anchor="middle" font-family="{FONT}" '
                   f'font-size="10.5" fill="#6b7887">{role}</text>')
    return out


def arrow(points, color, width, dash):
    xp, yp = points[-2]
    xn, yn = points[-1]
    dx = xn - xp
    dy = yn - yp
    ln = max(math.hypot(dx, dy), 1e-9)
    ux = dx / ln
    uy = dy / ln
    head = 10
    bx = xn - ux * head
    by = yn - uy * head
    px = -uy * head * 0.45
    py = ux * head * 0.45
    body = points[:-1] + [(bx, by)]
    d = "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in body)
    dash_attr = ""
    if dash:
        dash_attr = f' stroke-dasharray="{dash}"'
    return (f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}" '
            f'stroke-linejoin="round"{dash_attr}/>'
            f'<path d="M {xn:.1f} {yn:.1f} L {bx + px:.1f} {by + py:.1f} L {bx - px:.1f} {by - py:.1f} Z" '
            f'fill="{color}"/>')


def label(points, text):
    top, share = (text.split("|") + [""])[:2]
    best = points[:2]
    best_len = -1
    for i in range(len(points) - 1):
        (x0, y0), (x1, y1) = points[i], points[i + 1]
        ln = math.hypot(x1 - x0, y1 - y0)
        if ln > best_len:
            best = ((x0, y0), (x1, y1))
            best_len = ln
    (x0, y0), (x1, y1) = best
    mx = (x0 + x1) / 2
    my = (y0 + y1) / 2
    w = max(7.0 * len(top), 7.0 * len(share)) + 14
    if abs(y1 - y0) < 1:
        rx = mx - w / 2
        ry = my - 42
    else:
        rx = mx + 8
        ry = my - 20
    cx = rx + w / 2
    return [f'<rect x="{rx:.1f}" y="{ry:.1f}" width="{w:.1f}" height="32" rx="6" '
            f'fill="#ffffff" fill-opacity="0.95" stroke="#e2e7ee"/>',
            f'<text x="{cx:.1f}" y="{ry + 13:.1f}" text-anchor="middle" font-size="11.5" '
            f'font-weight="600" font-family="{FONT}" fill="#3a4653">{esc(top)}</text>',
            f'<text x="{cx:.1f}" y="{ry + 26:.1f}" text-anchor="middle" font-size="10.5" '
            f'font-family="{FONT}" fill="#7b8794">{esc(share)}</text>']


def build_svg():
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="100%" height="auto" '
             f'viewBox="0 0 {W} {H}" font-family="{FONT}">',
             f'<rect width="{W}" height="{H}" fill="#ffffff"/>',
             '<text x="30" y="42" font-size="21" font-weight="700" fill="#16202b">'
             'Наблюдаемый процесс закупки: модель, восстановленная по журналу (1 000 заявок, 6 508 событий)</text>',
             '<text x="30" y="66" font-size="13" fill="#6b7887">'
             'На переходах — число наблюдённых пар активностей и доля от всех выходов исходной активности</text>']
    for node_id in NODES:
        parts += box(node_id)
    for src, dst, pts, lab, kind in EDGES:
        color, width, dash = ARROW[kind]
        parts.append(arrow(pts, color, width, dash))
        parts += label(pts, lab)

    ly = 600
    parts.append(f'<rect x="25" y="{ly}" width="1420" height="192" rx="12" fill="#fafbfc" stroke="#e2e7ee"/>')
    parts.append(f'<text x="48" y="{ly + 30}" font-size="14" font-weight="700" fill="#16202b">Легенда</text>')
    legend = [
        ("main", "основной поток — маршрут самого частого варианта (V01, 567 заявок)"),
        ("alt", "наблюдаемая альтернатива: отказ, отмена, возврат на доработку"),
        ("loop", "возврат на доработку: руководитель → доработка → проверка → руководитель"),
        ("hypo", "ветка с условием, которого нет в журнале: сумма ≥ 150 000 (гипотеза, 19 исключений)"),
    ]
    y = ly + 56
    for kind, text in legend:
        color, width, dash = ARROW[kind]
        dash_attr = ""
        if dash:
            dash_attr = f' stroke-dasharray="{dash}"'
        parts.append(f'<path d="M 48 {y} L 118 {y}" stroke="{color}" stroke-width="{width}" '
                     f'stroke-linecap="round"{dash_attr}/>')
        parts.append(f'<text x="134" y="{y + 5}" font-size="12.5" fill="#33404d">{esc(text)}</text>')
        y += 26
    notes = [
        "Заявка отклонена — 63 кейса (6,3 %): 45 после первичной проверки, 18 после согласования руководителем.",
        "Доработка заявки — 156 кейсов, 174 задания (18 кейсов проходили цикл дважды); все возвраты идут с этапа согласования.",
        "Дополнительное согласование (20,9 % заявок): порог 150 000 объясняет 209 из 209 случаев ветки и ошибается на 19 кейсах,",
        "поэтому условие на схеме показано пунктиром как гипотеза, а не как установленное правило.",
    ]
    y += 2
    for note in notes:
        parts.append(f'<text x="48" y="{y}" font-size="12" fill="#54606e">{esc(note)}</text>')
        y += 19
    parts.append("</svg>")
    return "\n".join(parts)


def build_mermaid(freq):
    def lab(a, b):
        return freq.get((a, b), "")

    return f"""%% Кейс 2. Эквивалентное представление модели с явными XOR-шлюзами.
%% Рендер: mermaid-cli или mermaid.live. Частоты — из out/transitions_freq.csv.
flowchart LR
  S((старт)) --> A["Регистрация заявки<br/><i>system</i>"]
  A -->|"{lab('Регистрация заявки', 'Первичная проверка')}"| B["Первичная проверка<br/><i>specialist</i>"]
  B --> G1{{решение специалиста}}
  G1 -->|"accept 96,2%"| C["Согласование руководителем<br/><i>manager</i>"]
  G1 -->|"reject 3,8%"| X1(["Заявка отклонена"])
  C --> G2{{решение руководителя}}
  G2 -->|"accept 80,7%"| D["Проверка бюджета<br/><i>finance</i>"]
  G2 -->|"return 15,4%"| R["Доработка заявки<br/><i>requester</i>"]
  G2 -->|"reject 1,6%"| X1
  G2 -->|"cancel 2,3%"| X2(["Заявка отменена"])
  R -->|"исправлено 100%"| B
  D --> G3{{порог суммы — гипотеза}}
  G3 -->|"сумма < 150 000 — 77,1%"| F["Исполнение закупки<br/><i>procurement</i>"]
  G3 -.->|"сумма ≥ 150 000 — 22,9%"| E["Дополнительное согласование<br/><i>director</i>"]
  E -.->|"согласовано 100%"| F
  F -->|"100%"| END(["Заявка выполнена"])
  classDef hyp fill:#fffbe8,stroke:#d0a53a,stroke-dasharray:6 4;
  class E hyp;
"""


def main():
    with open(os.path.join(OUT, "summary.json"), encoding="utf-8") as fh:
        summary = json.load(fh)
    freq = {}
    with open(os.path.join(OUT, "transitions_freq.csv"), encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            freq[(row["SourceActivity"], row["TargetActivity"])] = (
                f'{row["Count"]} · {float(row["Probability"]) * 100:.1f} %')
    svg = build_svg()
    with open(os.path.join(OUT, "schema.svg"), "w", encoding="utf-8") as fh:
        fh.write(svg)
    with open(os.path.join(OUT, "schema.mmd"), "w", encoding="utf-8") as fh:
        fh.write(build_mermaid(freq))
    print(f"schema.svg {len(svg) // 1024} KB; transition labels: {len(freq)}")
    print("gateway:", json.dumps(summary["gateway"]["best_threshold"], ensure_ascii=False))


if __name__ == "__main__":
    main()
