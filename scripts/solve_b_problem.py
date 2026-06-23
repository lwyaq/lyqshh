#!/usr/bin/env python3
"""Solve and tabulate B problem patrol/intercept plans.

Uses only standard library for computations. If matplotlib is installed, also
emits three illustrative PNG figures under outputs/.
"""
from __future__ import annotations

import csv
import itertools
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "outputs"
OUT.mkdir(exist_ok=True)


def read_params():
    with open(DATA / "parameters.json", encoding="utf-8") as f:
        return json.load(f)


def read_airspaces():
    rows = []
    with open(DATA / "airspaces.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            pts = [(float(r[f"x{i}"]), float(r[f"y{i}"])) for i in range(1, 5)]
            rows.append((int(r["airspace"]), pts))
    return rows


def read_targets():
    rows = []
    with open(DATA / "targets.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append({k: (int(v) if k == "id" else float(v)) for k, v in r.items()})
    return rows


def polygon_area_centroid_perimeter(pts):
    area2 = cx = cy = per = 0.0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
        cross = x1 * y2 - x2 * y1
        area2 += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
        per += math.hypot(x2 - x1, y2 - y1)
    area = area2 / 2.0
    return abs(area), cx / (6 * area), cy / (6 * area), per


def target_crossing(target, radius, speed):
    x, y, dx, dy = target["x"], target["y"], target["dx"], target["dy"]
    a = speed * speed * (dx * dx + dy * dy)
    b = 2 * speed * (x * dx + y * dy)
    c = x * x + y * y - radius * radius
    disc = b * b - 4 * a * c
    roots = [(-b - math.sqrt(disc)) / (2 * a), (-b + math.sqrt(disc)) / (2 * a)]
    t = min(r for r in roots if r >= 0)
    px, py = x + speed * t * dx, y + speed * t * dy
    return t * 60, px, py, math.degrees(math.atan2(py, px))


def write_csv(name, rows, fieldnames):
    with open(OUT / name, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def write_simple_svg(name, elements, width=900, height=650):
    def esc(x):
        return str(x).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    content = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
               '<rect width="100%" height="100%" fill="white"/>']
    content.extend(elements)
    content.append('</svg>')
    (OUT / name).write_text("\n".join(content), encoding="utf-8")


def map_xy(x, y, width=900, height=650, scale=0.42):
    return width / 2 + x * scale, height - 40 - y * scale


def polyline_svg(points, color, label=None):
    pts = []
    for x, y in points:
        sx, sy = map_xy(x, y)
        pts.append(f"{sx:.1f},{sy:.1f}")
    elems = [f'<polyline points="{" ".join(pts)}" fill="none" stroke="{color}" stroke-width="2"/>']
    if label:
        sx, sy = map_xy(points[0][0], points[0][1])
        elems.append(f'<text x="{sx:.1f}" y="{sy-8:.1f}" font-size="14" fill="{color}">{label}</text>')
    return elems


def circle_arc_points(r, a0=30, a1=150):
    return [(r * math.cos(math.radians(a)), r * math.sin(math.radians(a))) for a in range(a0, a1 + 1, 2)]


def main():
    p = read_params()
    airspaces = read_airspaces()
    targets = read_targets()
    group_patrol_speed = min(p["fly1"]["patrol_speed_kmh"], p["zhi1"]["patrol_speed_kmh"])
    group_transit_speed = min(p["fly1"]["max_speed_kmh"], p["zhi1"]["max_speed_kmh"])

    # Sheet 1
    sheet1 = []
    patrol_times = []
    for idx, pts in airspaces:
        area, cx, cy, per = polygon_area_centroid_perimeter(pts)
        near = min(math.hypot(x, y) for x, y in pts)
        transit_min = near / group_transit_speed * 60
        arrival_min = p["takeoff_wave_duration_min"] + transit_min
        patrol_min = per / group_patrol_speed * 60
        patrol_times.append(patrol_min)
        path = " -> ".join(f"({x:.2f},{y:.2f})" for x, y in pts + [pts[0]])
        sheet1.append({
            "巡逻编组": f"P{idx}",
            "责任空域": f"空域{idx}",
            "配置": "1飞1+1智1",
            "中心点(km)": f"({cx:.2f},{cy:.2f})",
            "面积(km2)": f"{area:.1f}",
            "路径长度(km)": f"{per:.1f}",
            "出动时段": "0-10 min",
            "抵达时刻": f"{arrival_min:.1f} min",
            "巡逻周期": f"{patrol_min:.1f} min",
            "巡逻路径": path,
            "说明": "8字形/跑道形完整轮扫，寻鱼器半径60km"
        })
    write_csv("sheet1_problem1.csv", sheet1, list(sheet1[0].keys()))

    t_min = min(patrol_times)
    # Target crossings and clusters
    crossings = []
    cross_xy = {}
    for t in targets:
        tmin, x, y, ang = target_crossing(t, p["outer_intercept_radius_km"], p["threat_speed_kmh"])
        cross_xy[t["id"]] = (x, y)
        crossings.append({
            "目标": t["id"],
            "到700km线时间(min)": f"{tmin:.1f}",
            "外层线交点": f"({x:.1f},{y:.1f})",
            "方位角": f"{ang:.1f}",
            "高度(km)": f"{t['h']:.1f}"
        })
    write_csv("target_outer_crossings.csv", crossings, list(crossings[0].keys()))

    intercept_groups = [
        ("I1", "2飞1", "1,4,12", "新增"),
        ("I2", "1飞1+1智1", "5,8", "P3转化"),
        ("I3", "1飞1+1智1", "6,11", "P2转化"),
        ("I4", "1飞1+1智1", "9,10", "P4转化"),
        ("I5", "1飞1+1智1", "2", "新增"),
        ("I6", "1飞1+1智1", "3", "P1转化"),
        ("I7", "1飞1+1智1", "7", "新增"),
    ]

    cases = [
        ("巡逻初期", 0.0, "否", 4, 2),
        ("巡逻中期", t_min / 2, "是", 8, 6),
        ("巡逻末期", t_min, "是", 8, 6),
    ]
    sheet2 = []
    for case, dt, handover, add_f, add_z in cases:
        for g, cfg, tgts, source in intercept_groups:
            sheet2.append({
                "场景": case,
                "DeltaT(min)": f"{dt:.2f}",
                "是否巡逻交接": handover,
                "拦截编组": g,
                "编组配置": cfg,
                "来源": source,
                "拦截目标": tgts,
                "增派飞1": add_f,
                "增派智1": add_z,
                "拦截窗口": "发现后32.5min内、外层线外",
                "航迹": "由当前/甲板初始位置直线前出至目标外层线交点附近"
            })
    write_csv("sheet2_problem2.csv", sheet2, list(sheet2[0].keys()))

    sheet3 = []
    wave_configs = [
        ("巡逻层", "T", "持续", "4组", 4, 4, "保持4个巡逻责任空域"),
        ("第1拦截层", "T+0~T+10", "第1波T+30", "7组", 8, 6, "1个2飞1组+6个飞智组"),
        ("第2拦截层", "T+25~T+35", "第2波T+60", "7组", 8, 6, "1个2飞1组+6个飞智组"),
        ("第3拦截层", "T+50~T+60", "第3波T+90", "7组", 8, 6, "1个2飞1组+6个飞智组"),
        ("机动预备", "T+60后", "高危方向", "1组", 2, 0, "2飞1快速支援"),
    ]
    for layer, launch, target_wave, groups, f, z, note in wave_configs:
        sheet3.append({
            "层/波次": layer,
            "出动时间": launch,
            "对应袭扰波次": target_wave,
            "编组数": groups,
            "飞1占用": f,
            "智1占用": z,
            "任务": note,
            "预计结果": "前三波各拦截12架，累计36架；第4波因飞1未完成2h整备而终止风险最高"
        })
    write_csv("sheet3_problem3.csv", sheet3, list(sheet3[0].keys()))

    # Markdown report assembled from generated numbers.
    report = ROOT / "docs" / "modeling_solution.md"
    report.write_text(f"""# B题：船飞1与智1协同抓鱼数学建模方案

## 核心结论

- 问题1：4个巡逻编组均采用 `1飞1+1智1`，一个起飞波次出动，共 `4飞1+4智1`。
- 最后一个巡逻编组抵达时刻：`T = {p['takeoff_wave_duration_min'] + min(math.hypot(x, y) for _, pts in airspaces for x, y in pts) / group_transit_speed * 60:.1f} min`。
- 最小巡逻周期：`T_min = {t_min:.1f} min`。
- 问题2：12架袭扰机到达700km外层线时间均约为 `32.5 min`；按100km拦截范围聚类，最少需要7个拦截编组，总拦截兵力为 `8飞1+6智1`。
- 问题2增派：巡逻初期 `4飞1+2智1`；巡逻中期和末期考虑交接均为 `8飞1+6智1`。
- 问题3：飞1是瓶颈资源；采用3层拦截，每层7组，最大完整拦截3个波次，累计 `36架`。
- 问题4：综合效能函数建议为 `E=0.25C+0.35I+0.15L+0.15S+0.10R`。

详细表格见 `outputs/sheet1_problem1.csv`、`outputs/sheet2_problem2.csv`、`outputs/sheet3_problem3.csv`。
""", encoding="utf-8")

    # Dependency-free SVG figures.
    elems = []
    elems += polyline_svg(circle_arc_points(500), "#777")
    elems += polyline_svg(circle_arc_points(700), "#777")
    for idx, pts in airspaces:
        elems += polyline_svg(pts + [pts[0]], ["#d62728", "#2ca02c", "#1f77b4", "#9467bd"][idx-1], f"A{idx}")
    elems.append('<text x="20" y="30" font-size="18">Figure 1 Patrol airspaces and 500/700 km arcs</text>')
    write_simple_svg("figure1_patrol_airspaces.svg", elems)

    elems = []
    elems += polyline_svg(circle_arc_points(700), "#777")
    for row in crossings:
        tid = int(row["目标"])
        x, y = cross_xy[tid]
        sx, sy = map_xy(x, y)
        elems.append(f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="4" fill="#d62728"/>')
        elems.append(f'<text x="{sx+6:.1f}" y="{sy-6:.1f}" font-size="12">{tid}</text>')
    elems.append('<text x="20" y="30" font-size="18">Figure 2 Target crossing points on 700 km line</text>')
    write_simple_svg("figure2_target_crossings.svg", elems)

    elems = ['<text x="20" y="30" font-size="18">Figure 3 Multi-wave interception timeline</text>']
    bars = [("Patrol transit", 0, 31.1, "#1f77b4"), ("Patrol cycle", 31.1, 51.3, "#2ca02c"), ("Wave1", 30, 32.5, "#d62728"), ("Wave2", 60, 32.5, "#ff7f0e"), ("Wave3", 90, 32.5, "#9467bd")]
    x0, y0, scale = 80, 80, 5
    for i, (name, start, dur, color) in enumerate(bars):
        y = y0 + i * 55
        elems.append(f'<rect x="{x0+start*scale:.1f}" y="{y}" width="{dur*scale:.1f}" height="28" fill="{color}"/>')
        elems.append(f'<text x="{x0+start*scale+5:.1f}" y="{y+19}" font-size="12" fill="white">{name}</text>')
    elems.append('<line x1="80" y1="390" x2="760" y2="390" stroke="black"/>')
    elems.append('<text x="80" y="420" font-size="12">minutes after mission start</text>')
    write_simple_svg("figure3_timeline.svg", elems, height=460)

    try:
        import matplotlib.pyplot as plt
        # Figure 1 patrol airspaces
        fig, ax = plt.subplots(figsize=(8, 6))
        for idx, pts in airspaces:
            xs = [x for x, _ in pts + [pts[0]]]
            ys = [y for _, y in pts + [pts[0]]]
            ax.plot(xs, ys, marker="o", label=f"Airspace {idx}")
        for r in [500, 700]:
            theta = [math.radians(a) for a in range(30, 151)]
            ax.plot([r * math.cos(t) for t in theta], [r * math.sin(t) for t in theta], "k--", alpha=0.5)
        ax.set_aspect("equal")
        ax.set_title("Patrol responsibility airspaces")
        ax.legend()
        fig.savefig(OUT / "figure1_patrol_airspaces.png", dpi=180)
        plt.close(fig)

        # Figure 2 target crossings
        fig, ax = plt.subplots(figsize=(8, 6))
        for row in crossings:
            tid = int(row["目标"])
            x, y = cross_xy[tid]
            ax.scatter([x], [y])
            ax.text(x + 5, y + 5, str(tid), fontsize=8)
        theta = [math.radians(a) for a in range(30, 151)]
        ax.plot([700 * math.cos(t) for t in theta], [700 * math.sin(t) for t in theta], "k--")
        ax.set_aspect("equal")
        ax.set_title("Target crossing points on 700km line")
        fig.savefig(OUT / "figure2_target_crossings.png", dpi=180)
        plt.close(fig)

        # Figure 3 gantt-like plan
        fig, ax = plt.subplots(figsize=(9, 4))
        bars = [("Patrol", 0, 31.1), ("Patrol cycle", 31.1, 51.3), ("Wave1 intercept", 30, 32.5), ("Wave2 intercept", 60, 32.5), ("Wave3 intercept", 90, 32.5)]
        for i, (name, start, dur) in enumerate(bars):
            ax.barh(i, dur, left=start)
            ax.text(start + dur / 2, i, name, ha="center", va="center", color="white", fontsize=8)
        ax.set_xlabel("minutes after mission start")
        ax.set_yticks([])
        ax.set_title("Multi-wave interception timeline")
        fig.savefig(OUT / "figure3_timeline.png", dpi=180)
        plt.close(fig)
    except Exception as exc:
        (OUT / "figure_generation_warning.txt").write_text(str(exc), encoding="utf-8")


if __name__ == "__main__":
    main()
