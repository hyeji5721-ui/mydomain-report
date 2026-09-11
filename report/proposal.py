# -*- coding: utf-8 -*-
"""제안서 조립 (9W Day3 — 처음부터 다시 짠 버전).

────────────────────────────────────────────────────────────────────
제안서는 분석 문서가 아니라 결재 문서다. 절 이름·순서·자동/사람 구분은
`core.config.PROPOSAL_SECTIONS` 에서만 바꾼다 — 이 파일에 절 제목을
박지 않는다. 자동 절(현황·원인·규모·제안)은 evidence 에 있는 값만
쓴다 — 없으면 그 사실을 그대로 적지, 지어내지 않는다. 사람이 쓰는 절은
"위험_철회"·"요청" 둘뿐이다.

**계산 과정은 여기 안 들어간다.** funnel()·funnel_by() 같은 함수 이름,
컬럼 이름, 판정 로직은 문서에 안 쓴다 — 궁금하면 앱을 보면 된다.
────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import html as _html
import re

from core import config as C
from report.sections import check_phrasing
from viz import proposal_charts as PC

_ORDER = ["하지 말 것", "다시 할 것", "할 것"]
_CLASS_WORD_KEY = {"하지 말 것": "분류_하지말것", "다시 할 것": "분류_다시할것",
                  "할 것": "분류_할것"}


def _word(key: str) -> str:
    """config.PROPOSAL_WORDS 에서 찍히는 말을 가져온다. 없는 키는 키 그대로
    쓴다 — 에러를 내지 않는다(9W Day3 판단 기준 ⑥)."""
    slot = C.PROPOSAL_WORDS.get(key)
    return slot["chosen"] if slot else key


_CODE_SPAN = re.compile(r"`[^`]+`")


def _strip_code(text: str) -> str:
    """제안카드.md 의 근거 문장엔 함수 이름·파일명이 백틱으로 박혀 있다
    (어제 카드는 분석 문서용이었다). 결재 문서에는 계산 과정을 안 넣는다
    (9W Day3 — "궁금하면 앱을 열면 된다") — 백틱 구간을 통째로 지우고
    남은 공백·구두점을 정리한다."""
    out = _CODE_SPAN.sub("", text or "")
    out = re.sub(r"\(\s*\)", "", out)       # 백틱만 들어 있던 괄호가 비면 지운다
    out = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", out, flags=re.DOTALL)  # 마크다운 굵게 -> HTML
    out = re.sub(r"\s{2,}", " ", out)
    out = re.sub(r"\s+([.,·])", r"\1", out)
    return out.strip()


# ── 카드 읽기 (제안카드.md, 읽기 전용) ────────────────────────────
_ROW = re.compile(r"^\|(?!-)(.*)\|\s*$", re.MULTILINE)
_CARD_HEADER = re.compile(r"^## 제안 \d+ — (.+)$", re.MULTILINE)
_META = re.compile(r"작성 시작:\s*(\S+)\s+최종 갱신:\s*(\S+)")


def _table_dict(block: str) -> dict:
    """"키 | 값" 두 칸짜리 표 여러 개를 한 dict 로 읽는다."""
    d = {}
    for m in _ROW.finditer(block):
        cells = [c.strip() for c in m.group(1).split("|")]
        if len(cells) != 2:
            continue
        key = cells[0].strip("* ").strip()
        if key:
            d[key] = cells[1].strip()
    return d


def load_cards(path=None) -> dict:
    """제안카드.md 를 읽는다. **읽기만 한다 — 여기서 파일을 고치지 않는다.**"""
    path = path or (C.ROOT / "제안카드.md")
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        return {"items": []}

    result: dict = {"items": []}
    meta_m = _META.search(text)
    if meta_m:
        result["started"], result["updated"] = meta_m.group(1), meta_m.group(2)

    parts = _CARD_HEADER.split(text)
    for i in range(1, len(parts), 2):
        title, body = parts[i].strip(), parts[i + 1]
        head, _, _rest = body.partition("### 반증")
        result["items"].append({"title": title, **_table_dict(head)})
    return result


def _items(cards: dict) -> list[dict]:
    return cards.get("items", []) or []


# ── 주제 ↔ 카드 매칭 ─────────────────────────────────────────────
def _topic_tokens(topic: dict, evidence: dict) -> list[str]:
    """주제를 가리키는 낱말 후보 — 카드 제목·근거에서 이 낱말을 찾는다.
    분해 축 주제는 "최저 칸"(문제가 있는 쪽), 퍼널 주제는 구간 이름,
    지표 주제는 지표 이름이 후보다."""
    tokens = []
    cause = evidence.get("원인")
    if cause and cause.get("칸"):
        worst = next((c for c in cause["칸"] if c.get("표시") == "최저"), None)
        if worst:
            tokens.append(str(worst.get(cause["축"], "")))
    if topic.get("구간"):
        tokens += topic["구간"].split(" → ")
    if topic.get("지표"):
        tokens.append(topic["지표"])
    return [tok for tok in tokens if tok]


def match_card(cards: dict, topic: dict, evidence: dict) -> dict | None:
    """이 주제에 대응하는 제안 카드를 찾는다. 여러 개 걸리면 "할 것"
    분류를 우선한다 — 구체적 조치가 적힌 카드가 "제안" 절에 가장 맞는다.
    없으면 None(있는 척 지어내지 않는다)."""
    tokens = _topic_tokens(topic, evidence)
    if not tokens:
        return None
    hits = [c for c in _items(cards)
           if any(tok in (c.get("title", "") + c.get("근거", "")) for tok in tokens)]
    if not hits:
        return None
    hits.sort(key=lambda c: c.get("분류") != "할 것")
    return hits[0]


# ── 절 빌더 ────────────────────────────────────────────────────────
def _sentence_규모(topic: dict) -> str:
    n = topic.get("규모_연간건수")
    if n is None:
        return ""
    가정 = " · ".join(topic.get("가정", []))
    return (f'<span class="lab est">추정</span> 연 {n}건 규모로 추산됩니다.'
           + (f' ({가정})' if 가정 else ""))


def _build_현황(topic, evidence, cards, human, title, question, kind):
    steps = evidence.get("현황") or []
    본 = next((s for s in steps if s.get("병목")), None)
    문장 = []
    if 본:
        문장.append(f'<span class="lab obs">관측</span> {본["단계"]} 단계 도달은 '
                   f'{본["도달"]:,}건입니다.')
    if topic.get("한줄"):
        문장.append(f'<span class="lab obs">관측</span> {topic["한줄"]}.')
    body = " ".join(문장)
    return {"제목": title, "질문": question, "kind": kind, "문장": body,
           "차트": ("funnel", steps), "표": None}


def _build_원인(topic, evidence, cards, human, title, question, kind):
    cause = evidence.get("원인")
    if not cause:
        사유 = evidence.get("원인_사유", "이 주제는 축 비교가 없습니다.")
        return {"제목": title, "질문": question, "kind": kind,
               "문장": f'<span class="unknown">확인 필요</span> — {사유}',
               "차트": None, "표": None}
    dim = cause["축"]
    best = next((c for c in cause["칸"] if c.get("표시") == "최고"), None)
    worst = next((c for c in cause["칸"] if c.get("표시") == "최저"), None)
    문장 = ""
    if best and worst:
        문장 = (f'<span class="lab obs">관측</span> {best[dim]} '
               f'{best["전환율"]:.1f}%, {worst[dim]} {worst["전환율"]:.1f}%로 '
               f'{best["전환율"] - worst["전환율"]:.1f}%p 벌어져 있습니다.')
    return {"제목": title, "질문": question, "kind": kind, "문장": 문장,
           "차트": ("gap", cause["칸"], dim), "표": None}


def _build_규모(topic, evidence, cards, human, title, question, kind):
    trend = evidence.get("추세")
    # 그림 하나엔 그것이 증명하는 문장 하나가 있어야 한다(9W Day3 판단 기준③)
    # — 추세 그림을 붙일 땐 "무엇이 어떻게 변했는지"를 먼저 문장으로 적는다.
    앞문장 = f'<span class="lab obs">관측</span> {topic["한줄"]}.' if trend else ""
    문장 = " ".join(s for s in (앞문장, _sentence_규모(topic)) if s)
    표 = [{"기간": p["기간"], "값": p["값"]} for p in trend] if trend else None
    return {"제목": title, "질문": question, "kind": kind, "문장": 문장,
           "차트": (("trend", trend) if trend else None), "표": 표}


def _build_제안(topic, evidence, cards, human, title, question, kind):
    card = match_card(cards, topic, evidence)
    if not card:
        return {"제목": title, "질문": question, "kind": kind,
               "문장": '<span class="unknown">확인 필요</span> — 이 주제에 '
                      "대응하는 제안 카드가 아직 없습니다. 제안 카드를 먼저 "
                      "채워야 합니다.",
               "차트": None, "표": None, "카드": None}
    cls_word = _word(_CLASS_WORD_KEY.get(card.get("분류", ""), ""))
    문장 = (f'<b>{_strip_code(card.get("title", ""))}</b> — {cls_word}<br>'
           f'근거: {_strip_code(card.get("근거", ""))}<br>'
           f'비용: {_strip_code(card.get("비용", "")) or _word("확인_필요")}<br>'
           f'효과: {_strip_code(card.get("효과", ""))}<br>'
           f'되돌림: {_strip_code(card.get("되돌림", ""))}')
    return {"제목": title, "질문": question, "kind": kind, "문장": 문장,
           "차트": None, "표": None, "카드": card}


def _build_위험_철회(topic, evidence, cards, human, title, question, kind):
    return {"제목": title, "질문": question, "kind": kind,
           "문장": human.get(title, ""),
           "placeholder": ("이 판단이 틀릴 수 있는 지점을 적으십시오. 철회 "
                          "조건도 함께 — [무엇이] [얼마]가 될 때까지 "
                          "[어느 지표]가 [얼마]에 이르지 못하면 철회한다."),
           "차트": None, "표": None}


def _build_요청(topic, evidence, cards, human, title, question, kind):
    n = topic.get("규모_연간건수") or 0
    quarterly = round(n / 4)
    선택지 = [
        {"이름": "승인", "설명": "제안된 조치를 바로 실행합니다."},
        {"이름": "조건부 승인", "설명": "표시된 확인 필요 항목을 먼저 채운 뒤 실행합니다."},
        {"이름": "보류", "설명": f"결정을 미루면 다음 분기까지 약 {quarterly}건이 "
                              "이 문제로 더 누적됩니다."},
    ]
    body = human.get(title, "")
    검사 = check_phrasing(body) if body else []
    has_decision_verb = any(v in body for v in ("승인", "결정", "판단"))
    return {"제목": title, "질문": question, "kind": kind, "문장": body,
           "placeholder": ("무엇을 결정해 달라고 할지 적으십시오. 승인·결정·"
                          "판단 중 하나가 문장에 있어야 합니다."),
           "규모_연간건수": n, "선택지": 선택지,
           "결정동사있음": has_decision_verb, "인과검사": 검사,
           "차트": None, "표": None}


_BUILDERS = {
    "현황": _build_현황, "원인": _build_원인, "규모": _build_규모,
    "제안": _build_제안, "위험_철회": _build_위험_철회, "요청": _build_요청,
}


def build(topic: dict | None, evidence: dict | None,
         cards: dict, human: dict | None = None) -> list[dict]:
    """제안서 절 목록을 조립한다. 절 순서·이름·자동/사람 구분은
    config.PROPOSAL_SECTIONS 를 그대로 따른다 — 여기서 새로 정하지 않는다.

    topic 이 없으면(주제를 아직 안 골랐으면) 모든 절이 "주제를 고르십시오"
    상태로 돌아간다 — 빈 화면 대신 이유를 보여준다.
    """
    human = human or {}
    if topic is None or evidence is None:
        return [{"제목": title, "질문": question, "kind": kind,
                 "문장": "주제를 먼저 고르십시오.", "차트": None, "표": None}
                for _key, title, question, _fn, kind in C.PROPOSAL_SECTIONS]

    secs = []
    for key, title, question, _fn, kind in C.PROPOSAL_SECTIONS:
        secs.append(_BUILDERS[key](topic, evidence, cards, human,
                                   title, question, kind))
    return secs


# ── HTML 로 내보내기 (9W Day3 — 템플릿 파일을 안 읽는다) ─────────────
_CSS = """
:root{--ink:#0f172a;--muted:#64748b;--primary:#4f46e5;--block:#f43f5e;
      --line:#e2e8f0;--bg:#f8fafc}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-size:10.5pt;
     line-height:1.7;font-family:"Malgun Gothic","Apple SD Gothic Neo",sans-serif}
.page{max-width:820px;margin:0 auto;padding:28px 30px 60px;background:#fff}
h1{font-size:20px;font-weight:800;margin:0 0 4px}
h2{font-size:15px;font-weight:800;margin:22px 0 2px;page-break-after:avoid}
.q{font-size:11px;color:var(--muted);margin:0 0 8px}
.summary{border:1px solid var(--line);border-left:4px solid var(--primary);
        border-radius:10px;padding:14px 18px;margin-bottom:20px;font-size:11.5px}
.summary .row{display:flex;gap:10px;padding:4px 0}
.summary .k{flex:0 0 46px;font-weight:700;color:var(--muted);font-size:10.5px}
table{width:100%;border-collapse:collapse;margin:8px 0 4px;font-size:10.5px}
th,td{border:none;border-bottom:1px solid var(--line);padding:5px 8px;
      text-align:left;vertical-align:top}
th{background:#f1f5f9;font-weight:700}
td.num,th.num{text-align:right}
.num{font-variant-numeric:tabular-nums;font-weight:700}
.num small{font-weight:400;font-size:9px;color:var(--muted)}
.lab{font-size:9px;font-weight:700;padding:1px 5px;border-radius:3px;
    margin-right:4px}
.lab.obs{background:rgba(79,70,229,.12);color:var(--primary)}
.lab.est{background:rgba(100,116,139,.15);color:var(--muted)}
.unknown{color:var(--block);font-weight:700}
.choices{margin:6px 0 0;padding-left:0;list-style:none;font-size:10.5px}
.choices li{padding:3px 0;border-top:1px solid var(--line)}
.choices b{color:var(--primary)}
.decision-warn{border:1px solid var(--block);color:var(--block);
              border-radius:6px;padding:6px 10px;font-size:10px;margin-top:6px}
.todo{border:1.5px dashed var(--muted);border-radius:6px;padding:6px 10px;
     color:var(--muted);font-style:italic;font-size:10.5px}
figure{margin:8px 0 4px}
@page{size:A4;margin:18mm 16mm}
@media print{body{background:#fff}.page{max-width:none;padding:0}}
"""


def _render_chart(chart) -> str:
    if not chart:
        return ""
    kind = chart[0]
    if kind == "funnel":
        return f"<figure>{PC.funnel_svg(chart[1], caption='그레인: 계획안 1건')}</figure>"
    if kind == "gap":
        _, cells, dim = chart
        return (f"<figure>{PC.gap_svg(cells, dim, caption='그레인: 계획안 1건. 이 구간 도달자 기준')}"
               "</figure>")
    if kind == "trend":
        _, points = chart
        return f"<figure>{PC.trend_svg(points, caption='그레인: 코호트(제출월) 평균')}</figure>"
    return ""


def _render_table(rows) -> str:
    if not rows:
        return ""
    cols = list(rows[0].keys())
    head = "".join(f"<th>{_html.escape(str(c))}</th>" for c in cols)
    body = "".join(
        "<tr>" + "".join(f"<td>{_html.escape(str(r.get(c, '')))}</td>" for c in cols)
        + "</tr>" for r in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _summary_box(topic: dict, secs_by_title: dict) -> str:
    def line(k, title):
        s = secs_by_title.get(title, {})
        text = re.sub(r"<[^>]+>", "", s.get("문장", "") or "")
        return f'<div class="row"><div class="k">{k}</div><div>{_html.escape(text)}</div></div>'

    rows = []
    order = [("현황", 0), ("원인", 1), ("규모", 2), ("요청", 5)]
    titles = [t for _k, t, _q, _f, _kind in C.PROPOSAL_SECTIONS]
    for label, idx in order:
        rows.append(line(label, titles[idx]))
    return f'<div class="summary"><h1>{_html.escape(topic.get("제목", ""))}</h1>{"".join(rows)}</div>'


def to_html(secs: list[dict], topic: dict | None = None) -> str:
    """제안서 절 목록을 A4 인쇄용 단일 HTML 문서로 만든다.

    템플릿 파일을 읽지 않는다 — 이 함수가 직접 마크업을 만든다. 빈 절은
    그리지 않는다(자동 절은 evidence 가 있는 한 항상 채워지도록 build() 가
    보장한다 — 정말 빈 것은 사람이 아직 안 쓴 두 절뿐이고, 그건 todo 로
    표시한다). 외부 CDN·이미지·웹폰트가 없어 파일 하나로 열린다.
    """
    by_title = {s["제목"]: s for s in secs}
    parts = [f"<style>{_CSS}</style><div class=\"page\">"]

    if topic:
        parts.append(_summary_box(topic, by_title))

    for s in secs:
        parts.append(f'<h2>{_html.escape(s["제목"])}</h2>')
        parts.append(f'<p class="q">{_html.escape(s["질문"])}</p>')

        if s["kind"] == "human":
            body = (s.get("문장") or "").strip()
            # "요청" 절은 문서 마지막 줄이 결정 요구 문장이어야 한다 — 선택지
            # 목록·경고는 사람이 쓴 문장 "앞"에 두고, 그 문장을 맨 끝에 둔다.
            if s.get("선택지"):
                items = "".join(f'<li><b>{_html.escape(c["이름"])}</b> — '
                               f'{_html.escape(c["설명"])}</li>'
                               for c in s["선택지"])
                parts.append(f'<ul class="choices">{items}</ul>')
            if body:
                bad = check_phrasing(body)
                if bad:
                    parts.append(f'<div class="decision-warn">인과를 단정하는 표현이 '
                                 f'있습니다 — {_html.escape(", ".join(bad))}</div>')
                if s.get("선택지") and not s.get("결정동사있음"):
                    parts.append('<div class="decision-warn">결정을 요구하는 동사'
                                 "(승인·결정·판단)가 안 보입니다.</div>")
                parts.append(f'<p>{_html.escape(body)}</p>')
            else:
                parts.append(f'<p class="todo">{_html.escape(s.get("placeholder", ""))}</p>')
        else:
            parts.append(f'<p>{s.get("문장", "")}</p>')
            parts.append(_render_chart(s.get("차트")))
            parts.append(_render_table(s.get("표")))

    parts.append("</div>")
    return "".join(parts)
