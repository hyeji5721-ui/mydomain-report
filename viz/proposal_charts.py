# -*- coding: utf-8 -*-
"""제안서 전용 그래프 (9W Day3) — 인라인 SVG 문자열만 돌려준다.

HTML 에 그대로 박아 쓴다. 외부 CDN·이미지·웹폰트를 안 쓴다 — 문자열
하나로 끝나야 한다. 색은 강조 1 · 기본 1 · 회색 1 까지만 쓴다(전부
config.COLORS/BRAND에서 가져온다 — 여기서 새 색을 만들지 않는다).

**값이 없는 계열은 그리지 않는다.** 0 으로 그리면 "값이 0"과 "데이터
없음"이 구분되지 않는다. 좌표·막대 길이는 전부 실제 값에서 계산한다 —
예시 숫자를 남기지 않는다.
"""
from __future__ import annotations

from core import config as C

_ACCENT = C.COLORS["block"]     # 병목 · 최저 칸 — 문제가 있는 자리
_BASE = C.BRAND["primary"]      # 기본
_GREY = C.BRAND["muted"]        # 나머지(비교 대상 아님)
_LINE = C.BRAND["line"]
_INK = C.BRAND["ink"]


def _esc(s) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def funnel_svg(steps: list[dict], caption: str = "") -> str:
    """현황 — 단계별 도달 막대. 병목 구간 하나만 강조색, 나머지는 기본색.

    steps 는 metrics.topic_evidence() 의 "현황" 그대로
    ([{"단계","도달","전환율","병목"}, ...]) — report/proposal.py 는 여기에
    raw DataFrame 을 넘기지 않는다. 값이 없는 계열(도달 0)은 그리지 않는다.
    """
    rows = [r for r in steps if r.get("도달")]
    if not rows:
        return ""
    max_n = max(r["도달"] for r in rows) or 1
    label_w, bar_max = 170, 380
    row_h = 40
    W = label_w + bar_max + 130
    H = 16 + len(rows) * row_h + (20 if caption else 0)
    parts = [f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" '
             f'font-family="sans-serif" font-size="12">']
    for i, r in enumerate(rows):
        y = 8 + i * row_h
        n = r["도달"]
        w = n / max_n * bar_max
        color = _ACCENT if r.get("병목") else _BASE
        parts.append(f'<text x="{label_w - 10}" y="{y + 16}" text-anchor="end" '
                     f'fill="{_INK}">{_esc(r["단계"])}</text>')
        parts.append(f'<rect x="{label_w}" y="{y}" width="{w:.1f}" height="24" '
                     f'fill="{color}" rx="3"/>')
        rate = r.get("전환율")
        rate_txt = "" if rate is None else f" (전 단계의 {rate:.1f}%)"
        bottleneck = " ← 병목" if r.get("병목") else ""
        parts.append(f'<text x="{label_w + w + 8:.1f}" y="{y + 17}" '
                     f'fill="{_INK}" font-weight="700">{n:,}건{rate_txt}'
                     f'{bottleneck}</text>')
    if caption:
        parts.append(f'<text x="0" y="{H - 6}" fill="{_GREY}" font-size="10.5">'
                     f'{_esc(caption)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def gap_svg(cells: list[dict], dim: str, caption: str = "") -> str:
    """원인 — 축별 전환율 가로 막대. 최고·최저만 색, 나머지는 회색.

    cells 는 metrics.topic_evidence() 의 "원인"->"칸" 그대로
    ([{<dim>: 값, "전환율", "표시": "최고"|"최저"|""}, ...]) — 최고·최저
    판정은 metrics.py 가 이미 내려 둔 "표시" 를 그대로 쓴다(여기서 다시
    비교하지 않는다).
    """
    rows = [r for r in cells if r.get("전환율") is not None]
    if not rows:
        return ""
    max_rate = max(r["전환율"] for r in rows) or 1
    label_w, bar_max = 170, 380
    row_h = 32
    W = label_w + bar_max + 90
    H = 12 + len(rows) * row_h + (20 if caption else 0)
    parts = [f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" '
             f'font-family="sans-serif" font-size="11.5">']
    for i, r in enumerate(sorted(rows, key=lambda r: -r["전환율"])):
        y = 6 + i * row_h
        rate = r["전환율"]
        w = rate / max_rate * bar_max
        mark = r.get("표시")
        color = _BASE if mark == "최고" else _ACCENT if mark == "최저" else _GREY
        label = str(r.get(dim, ""))
        parts.append(f'<text x="{label_w - 10}" y="{y + 15}" text-anchor="end" '
                     f'fill="{_INK}">{_esc(label)}</text>')
        parts.append(f'<rect x="{label_w}" y="{y}" width="{w:.1f}" height="20" '
                     f'fill="{color}" rx="3"/>')
        parts.append(f'<text x="{label_w + w + 8:.1f}" y="{y + 15}" '
                     f'fill="{_INK}" font-weight="700">{rate:.1f}%</text>')
    if caption:
        parts.append(f'<text x="0" y="{H - 6}" fill="{_GREY}" font-size="10.5">'
                     f'{_esc(caption)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def trend_svg(points: list[dict], threshold: float | None = None,
             caption: str = "") -> str:
    """규모/추세 — 최근 코호트 꺾은선. 임계선이 있으면 점선으로.

    points 는 [{"기간": str, "값": float}, ...] (metrics.topic_evidence() 의
    "추세" 그대로). 2개 미만이면 추세를 그릴 수 없어 빈 문자열을 돌려준다.
    """
    pts = [p for p in points if p.get("값") is not None]
    if len(pts) < 2:
        return ""
    vals = [p["값"] for p in pts]
    lo, hi = min(vals + ([threshold] if threshold is not None else [])), \
        max(vals + ([threshold] if threshold is not None else []))
    span = (hi - lo) or 1
    W, H = 560, 220
    pad_l, pad_r, pad_t, pad_b = 50, 20, 16, 40
    plot_w, plot_h = W - pad_l - pad_r, H - pad_t - pad_b

    def xy(i, v):
        x = pad_l + (i / (len(pts) - 1)) * plot_w
        y = pad_t + (1 - (v - lo) / span) * plot_h
        return x, y

    coords = [xy(i, p["값"]) for i, p in enumerate(pts)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
    parts = [f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" '
             f'font-family="sans-serif" font-size="11">']
    # 축 눈금 — 최소·최대만 표시(장식적 눈금선은 안 넣는다)
    parts.append(f'<line x1="{pad_l}" y1="{pad_t}" x2="{pad_l}" y2="{pad_t + plot_h}" '
                 f'stroke="{_LINE}"/>')
    parts.append(f'<line x1="{pad_l}" y1="{pad_t + plot_h}" '
                 f'x2="{pad_l + plot_w}" y2="{pad_t + plot_h}" stroke="{_LINE}"/>')
    if threshold is not None:
        ty = pad_t + (1 - (threshold - lo) / span) * plot_h
        parts.append(f'<line x1="{pad_l}" y1="{ty:.1f}" x2="{pad_l + plot_w}" '
                     f'y2="{ty:.1f}" stroke="{_ACCENT}" stroke-width="1.5" '
                     f'stroke-dasharray="5,4"/>')
        parts.append(f'<text x="{pad_l + plot_w}" y="{ty - 4:.1f}" '
                     f'text-anchor="end" fill="{_ACCENT}">임계선 {threshold:g}</text>')
    parts.append(f'<polyline points="{line}" fill="none" stroke="{_BASE}" '
                 f'stroke-width="2.5"/>')
    for (x, y), p in zip(coords, pts):
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="{_BASE}"/>')
        parts.append(f'<text x="{x:.1f}" y="{y - 10:.1f}" text-anchor="middle" '
                     f'fill="{_INK}" font-weight="700">{p["값"]:g}</text>')
        parts.append(f'<text x="{x:.1f}" y="{pad_t + plot_h + 16:.1f}" '
                     f'text-anchor="middle" fill="{_GREY}" font-size="9.5">'
                     f'{_esc(p["기간"])}</text>')
    if caption:
        parts.append(f'<text x="0" y="{H - 4}" fill="{_GREY}" font-size="10.5">'
                     f'{_esc(caption)}</text>')
    parts.append("</svg>")
    return "".join(parts)
