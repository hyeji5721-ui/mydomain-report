# -*- coding: utf-8 -*-
"""제안서 절 조립.

────────────────────────────────────────────────────────────────────
sections.py 와 같은 질문으로 자동/사람을 가른다 — 자동: 1 한 장 요약·2 하지 말 것·
3 다시 할 것·4 할 것·7 부록(카드에 있는 것을 그대로 옮길 뿐이다) / 사람: 5 이 제안이
틀린다면·6 적용(카드 여러 장을 종합해 하나로 판단해야 한다).
────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import html as _html
import re
from datetime import datetime

from core import config as C
from report.sections import BANNED, check_phrasing
from report.to_pdf import INK, LINE, MUTED, Report, _hex

_ORDER = ["하지 말 것", "다시 할 것", "할 것"]


# ── 카드 읽기 (제안카드.md, 읽기 전용) ────────────────────────────
_ROW = re.compile(r"^\|(?!-)(.*)\|\s*$", re.MULTILINE)
_CARD_HEADER = re.compile(r"^## 제안 \d+ — (.+)$", re.MULTILINE)
_META = re.compile(r"작성 시작:\s*(\S+)\s+최종 갱신:\s*(\S+)")


def _table_dict(block: str) -> dict:
    """"키 | 값" 두 칸짜리 표 여러 개를 한 dict 로 읽는다. 구분선(|---|---|)과
    빈 헤더행(| | |)은 건너뛴다. **굵게(`**키**`)도 맨키도 똑같이 읽는다.**"""
    d = {}
    for m in _ROW.finditer(block):
        cells = [c.strip() for c in m.group(1).split("|")]
        if len(cells) != 2:
            continue
        key = cells[0].strip("* ").strip()
        if not key:
            continue
        d[key] = cells[1].strip()
    return d


def _bracketed(text: str, pattern: str) -> str:
    """정규식으로 문장 하나를 뽑되, "[ ]" 로 안 채워진 자리표시자는 빈
    문자열로 본다 — 채운 것과 안 채운 것을 구분해야 나머지 코드가
    "카드에 없다"고 정확히 판단할 수 있다."""
    m = re.search(pattern, text)
    if not m:
        return ""
    val = m.group(1).strip()
    return "" if re.fullmatch(r"\[\s*\]", val) else val


def load_cards(path=None) -> dict:
    """제안카드.md 를 읽는다. **읽기만 한다 — 여기서 파일을 고치지 않는다.**

    지금 템플릿(표 셀 하나가 물리적으로 한 줄)에 맞춘 파서다. "크기"·"분모"·
    "조회_일시"·"표본"은 지금 카드 형식에 없는 필드라 여기서 채워지지
    않는다 — build() 의 _s1_summary() 가 그 자리를 todo 로 남긴다.
    """
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
        head, _, rest = body.partition("### 반증")
        item = {"title": title, **_table_dict(head)}

        if rest:
            falsify, _, rebuttal = rest.partition("### 받은 반박")
            item["반증"] = {
                "조건": _bracketed(falsify, r"이 제안이 틀렸다면 (.+?) 때문일 것이다\."),
                "확인방법": _bracketed(falsify, r"확인하려면 (.+?) 을 보면 된다\."),
                **_table_dict(falsify),
            }
            if rebuttal.strip():
                item["받은_반박"] = _table_dict(rebuttal)

        result["items"].append(item)
    return result


# ── 판단기준 읽기 (판단기준.md, 읽기 전용) ────────────────────────
_DATE_HEADER = re.compile(r"^## (\d{4}-\d{2}-\d{2})\s*$", re.MULTILINE)
_TODAY_DECISIONS = re.compile(
    r"^### 오늘 내린 결정\s*\n(.*?)(?=^### |\Z)", re.MULTILINE | re.DOTALL)
_BULLET = re.compile(r"^- (.+?)(?=^- |\Z)", re.MULTILINE | re.DOTALL)


def load_judgment_candidates(path=None) -> list[str]:
    """판단기준.md 최신 날짜 항목의 "오늘 내린 결정" 문장을 후보로 뽑는다.

    **읽기만 한다 — 여기서 파일을 고치지 않는다.** 판단기준.md 는 "## 날짜"
    로 회차를 가르고 각 회차에 "### 오늘 내린 결정" 절이 있다 — 가장 최근
    회차(파일의 마지막 "## 날짜")의 그 절만 후보로 쓴다. 불릿 하나를 통째로
    쓰지 않고 굵게 처리된 핵심 문장만 뽑는다 — 뒤따르는 설명까지 다 넣으면
    "후보 목록"이 아니라 그날 일지 전체가 된다.
    """
    path = path or (C.ROOT / "판단기준.md")
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        return []

    dates = list(_DATE_HEADER.finditer(text))
    if not dates:
        return []
    section = text[dates[-1].end():]

    m = _TODAY_DECISIONS.search(section)
    if not m:
        return []

    candidates = []
    for bullet in _BULLET.findall(m.group(1)):
        lead = re.search(r"\*\*(.+?)\*\*", bullet, re.DOTALL)
        text_ = lead.group(1) if lead else bullet
        candidates.append(re.sub(r"\s+", " ", text_).strip())
    return candidates


def _items(cards: dict) -> list[dict]:
    return cards.get("items", []) or []


def _by_class(cards: dict, label: str) -> list[dict]:
    return [c for c in _items(cards) if c.get("분류") == label]


# 확신도가 "낮다"로 잡히는 값. "확인됨"만 빼고 전부 — 비어 있으면(반증을 아직
# 안 채웠으면) 확신도를 모르는 것이니 이것도 "낮다"에 넣는다.
_LOW_CONFIDENCE = {"", "미확인", "추정"}


def _size(card: dict):
    """카드의 크기(격차×비중). 숫자가 아니면 None — 근거 문장에서 다시
    계산하거나 짐작하지 않는다. 카드에 없으면 없는 것이다."""
    v = card.get("크기")
    return v if isinstance(v, (int, float)) else None


def _finding_line(cards: dict) -> str:
    """발견 — 크기(격차×비중)가 가장 큰 카드 하나. 분모를 함께 적는다."""
    ranked = [(c, _size(c)) for c in _items(cards)]
    ranked = [(c, s) for c, s in ranked if s is not None]
    if not ranked:
        return "발견: todo — 카드에 크기(격차×비중) 값이 없어 고를 수 없다"
    best, size = max(ranked, key=lambda cs: cs[1])
    denom = best.get("분모") or best.get("근거")
    if not denom:
        return f"발견: todo — \"{best.get('title', '')}\"의 분모가 카드에 없다"
    return f"발견: {best.get('title', '(제목 없음)')} — 크기 {size} (분모: {denom})"


def _proposal_line(cards: dict) -> str:
    """제안 — 본문 순서와 같게, 하지 말 것 → 다시 할 것 → 할 것 제목만 나열한다."""
    parts = []
    for label in _ORDER:
        titles = [c.get("title", "(제목 없음)") for c in _by_class(cards, label)]
        if titles:
            parts.append(f"[{label}] " + ", ".join(titles))
    if not parts:
        return "제안: todo — 카드가 없다"
    return "제안: " + " → ".join(parts)


def _uncertain_line(cards: dict) -> str:
    """불확실 — 확신도가 낮거나 미확인인 카드 중 크기가 가장 큰 것 하나."""
    ranked = [(c, _size(c)) for c in _items(cards)
              if (c.get("반증") or {}).get("확신도", "") in _LOW_CONFIDENCE]
    ranked = [(c, s) for c, s in ranked if s is not None]
    if not ranked:
        return ("불확실: todo — 확신도가 낮거나 미확인인 카드 중 크기 값이 "
                "있는 것이 없다")
    worst, size = max(ranked, key=lambda cs: cs[1])
    conf = (worst.get("반증") or {}).get("확신도") or "미확인"
    return f"불확실: {worst.get('title', '(제목 없음)')} — 확신도 {conf} (크기 {size})"


def _basis_line(cards: dict) -> str:
    """근거 — 발견.md 의 조회 일시·표본·"상세는 부록". cards 최상위에
    없으면 그 자리만 todo 로 남긴다."""
    when = cards.get("조회_일시") or "todo — 조회 일시 없음"
    sample = cards.get("표본") or "todo — 표본 없음"
    return f"근거: {when} · {sample} · 상세는 부록"


# ── 자동으로 쓰는 절 ──────────────────────────────────────────────
def _s1_summary(cards: dict) -> dict:
    """1. 한 장 요약 — 넷을 넘기지 않는다. 다섯째 줄이 생기면 잘못 조립한 것이다.

    발견    카드 근거 중 크기(격차×비중)가 가장 큰 것 하나, 분모와 함께
    제안    본문 순서와 같게(하지 말 것 → 다시 할 것 → 할 것) 제목만 나열
    불확실  확신도가 낮거나 "미확인"인 카드 중 크기가 가장 큰 것 하나
    근거    발견.md 의 조회 일시 · 표본 · "상세는 부록"

    **카드에 없는 문장은 만들지 않는다** — 크기·분모·확신도·조회 일시·표본이
    없으면 그 줄은 "todo"로 남긴다. 대신 값을 지어내지 않는다.
    """
    lines = [
        _finding_line(cards),
        _proposal_line(cards),
        _uncertain_line(cards),
        _basis_line(cards),
    ]
    return {"title": "1. 한 장 요약", "kind": "auto", "body": "\n".join(lines)}


def _s_class(cards: dict, label: str, title: str) -> dict:
    """2~4. 하지 말 것 / 다시 할 것 / 할 것

    카드에 있는 근거·비용·효과·되돌림을 표로 그대로 옮긴다. **순서는 카드에
    적힌 순서 그대로다** — 여기서 다시 정렬하지 않는다.
    """
    rows = _by_class(cards, label)
    if rows:
        body = (f'"{label}"로 분류된 카드 {len(rows)}건입니다. 아래 순서는 '
                f"카드 작성 순서 그대로이며, 이 함수가 다시 매기지 않습니다.")
    else:
        body = f'이번 조회에서 "{label}"로 분류된 카드가 없습니다.'

    table_rows = [
        {"제안": c.get("title", ""),
         "근거": c.get("근거", "") or "미확인",
         "비용": c.get("비용", "") or "미확인",
         "효과": c.get("효과", "") or "미확인",
         "되돌림": c.get("되돌림", "") or "미확인"}
        for c in rows
    ]
    return {"title": title, "kind": "auto", "body": body,
            "tables": [{"caption": title, "rows": table_rows}]}


def _s7_appendix(cards: dict) -> dict:
    """7. 부록 — 근거 상세

    본문에서 요약한 카드의 전체 필드(반증·받은 반박 포함)를 빠짐없이 옮긴다.
    본문을 지워도 이 표를 보면 원본을 다시 찾을 수 있어야 한다.
    """
    rows = []
    for i, c in enumerate(_items(cards), start=1):
        r = c.get("반증") or {}
        b = c.get("받은_반박") or {}
        rows.append({
            "번호": i, "제목": c.get("title", ""), "분류": c.get("분류", ""),
            "근거": c.get("근거", "") or "미확인",
            "비용": c.get("비용", "") or "미확인",
            "효과": c.get("효과", "") or "미확인",
            "되돌림": c.get("되돌림", "") or "미확인",
            "반증 조건": r.get("조건", ""),
            "반증 확인방법": r.get("확인방법", ""),
            "반증 확신도": r.get("확신도", ""),
            "받은 반박": b.get("지적", ""),
            "반박 처리": b.get("처리", ""),
        })
    body = f"카드 {len(rows)}건의 전체 필드입니다. 본문 표에서 뺀 칸도 여기엔 다 있습니다."
    return {"title": "7. 부록 — 근거 상세", "kind": "auto", "body": body,
            "tables": [{"caption": "카드 전체", "rows": rows}]}


# ── 사람이 쓰는 절 ────────────────────────────────────────────────
def _guide_falsify(cards: dict) -> list[str]:
    """5. 이 제안이 틀린다면 가이드 재료 — 카드마다 채워 둔 반증 조건을
    후보로만 보여준다. **하나를 고르는 것은 사람 몫이다** — 카드마다 쓰면
    다섯 개가 되고 아무도 안 읽는다(§4)."""
    lines = []
    for c in _items(cards):
        r = c.get("반증") or {}
        cond = r.get("조건")
        if cond:
            lines.append(f"{c.get('title', '')}: {cond}")
    return lines or ["카드에 아직 채워진 반증 조건이 없습니다 — 카드의 "
                     '"반증" 절을 먼저 채우십시오.']


def _s5_falsify(cards: dict, human: dict) -> dict:
    return {
        "title": "5. 이 제안이 틀린다면", "kind": "human",
        "body": human.get("5. 이 제안이 틀린다면", ""),
        "placeholder": "이 제안이 틀렸다면 무엇 때문인지, 확인하려면 무엇을 보면 되는지 적으십시오.",
        "guide": _guide_falsify(cards),
    }


def _s6_apply(cards: dict, human: dict) -> dict:
    """6. 적용 — 본문은 사람이 쓰지만, 후보 목록은 판단기준.md 최근 회차의
    "오늘 내린 결정" 문장을 자동으로 먼저 보여준다.

    **후보 목록은 여기서 고치지 않는다** — load_judgment_candidates() 가
    읽은 그대로 "guide"에 담아 참고용으로만 내놓는다. 고르는 것과, "다음에
    무엇을 볼 것인가"를 쓰는 것은 사람 몫이라 "body"만 사람이 채운다.
    """
    return {
        "title": "6. 적용", "kind": "human",
        "body": human.get("6. 적용", ""),
        "placeholder": "판단기준.md 후보 중 무엇을 고를지, 다음에 무엇을 볼 것인지 적으십시오.",
        "guide": load_judgment_candidates(),
    }


# ── 조립 ──────────────────────────────────────────────────────────
def build(cards: dict, human: dict | None = None) -> list[dict]:
    """제안서 절을 조립한다. cards 는 제안카드.md 를 파싱한 딕셔너리.

    기대하는 형태:
        {"started": "<날짜>", "updated": "<날짜>",
         "조회_일시": "<발견.md 조회 일시>", "표본": "<발견.md 표본 요약>",
         "items": [{"title": str, "분류": "하지 말 것"|"다시 할 것"|"할 것",
                    "근거": str, "비용": str, "효과": str, "되돌림": str,
                    "크기": float,   # 격차×비중. 없으면 1.요약의 "발견"/"불확실"이 todo
                    "분모": str,     # 없으면 "근거"로 대신 쓴다
                    "반증": {"조건": str, "확인방법": str, "확신도": str, ...},
                    "받은_반박": {"지적": str, "처리": str, ...}}, ...]}

    ★ "조회_일시"·"표본"·카드별 "크기"·"분모"는 지금 파서가 안 채워 주는
    필드다 — 없으면 _s1_summary() 가 그 자리만 todo 로 남긴다(§8 카드에
    없는 문장은 만들지 않는다).

    **순서와 자동/사람 구분은 바꾸지 않는다.** human 은 사람이 쓴 절의 본문
    딕셔너리로, sections.py 와 같은 방식으로 절 제목이 키다
    (예: human["5. 이 제안이 틀린다면"]).

    ★ check_phrasing() 을 절마다 걸어 반환값에 "phrasing_warnings" 를
    붙인다 — sections.py 의 규칙("사람이 쓴 장에도 걸어라")과 같다. 카드의
    근거·효과 문구는 사람이 쓴 것이라 자동 절에도 인과 단정 표현이 섞여
    들어올 수 있다.
    """
    human = human or {}
    sections = [
        _s1_summary(cards),
        _s_class(cards, "하지 말 것", "2. 하지 말 것"),
        _s_class(cards, "다시 할 것", "3. 다시 할 것"),
        _s_class(cards, "할 것", "4. 할 것"),
        _s5_falsify(cards, human),
        _s6_apply(cards, human),
        _s7_appendix(cards),
    ]
    for s in sections:
        bad = check_phrasing(s.get("body", ""))
        if bad:
            s["phrasing_warnings"] = bad
    return sections


# ── HTML 로 내보내기 (수업자료/제안서_템플릿.html 을 읽어 그대로 쓴다) ──
# ★ 2026-09-09: 템플릿을 D:\STUDY\데이터 분석\제안서_템플릿.html 에서 찾았다
# (원래 기대한 "mydomain-report/수업자료/" 밑이 아니라 프로젝트 폴더의
# 형 폴더다). load_template() 이 두 위치를 다 찾아본다. 이 구조를 옮긴
# 코드라 — 값이 있는 자리는 채우고, 없는 자리는 템플릿이 원래 갖고 있던
# "[ ... ]" + class="todo" 를 **그대로 둔다.** 코드가 지어내지 않는다.
_BOLD = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_LABEL_PREFIX = re.compile(r"^(관측|가정|추정)\s*—\s*")
_LABEL_CLASS = {"관측": "l-obs", "가정": "l-asm", "추정": "l-est"}
_NUM = re.compile(r"\d[\d,]*\.?\d*")

# 템플릿의 세 카드 클래스(.prop stop/redo/go)·번호·배지가 가리키는 분류.
_PROP_META = {
    "하지 말 것": ("stop", "① 하지 말 것", "b-block", "✕"),
    "다시 할 것": ("redo", "② 다시 할 것", "b-warn", "▲"),
    "할 것": ("go", "③ 할 것", "b-ok", "●"),
}
# 반증.확신도 값 -> 템플릿의 badge 클래스. 템플릿 예시가 실제로 이렇게 쓴다
# (확인됨=b-ok, 추정=b-warn, 미확인=b-block) — 비어 있으면(아직 반증을 안
# 채웠으면) "판정 없음" 뜻의 b-none 을 더했다(§ 임계값 없는 지표는 none).
_CONF_BADGE = {"확인됨": ("b-ok", "●"), "추정": ("b-warn", "▲"),
              "미확인": ("b-block", "✕")}


def _wrap_numbers(escaped: str) -> str:
    return _NUM.sub(lambda m: f'<span class="num">{m.group(0)}</span>', escaped)


def _render_value(value, multiline: bool = True) -> str:
    """카드 필드 값 하나를 템플릿 클래스에 맞춰 렌더링한다.

    - 비어 있거나 "todo —"로 시작하면(§1.요약처럼 코드가 못 채운 자리)
      **채우지 않고** class="todo" 로 통째로 남긴다.
    - "미확인"으로 시작하면 그 토큰만 템플릿의 class="unknown" 으로 표시한다
      — 사람이 "모른다"고 정직하게 적은 카드라 todo(빈 자리)와는 다르다.
    - "관측 —"·"가정 —"·"추정 —" 로 시작하는 줄은 템플릿의 .lab 배지로 바꾼다
      (카드가 이미 이 접두어로 쓰여 있다 — 새로 라벨을 붙이는 게 아니다).
    - 줄 구분은 카드 안의 실제 "<br>"(제안카드.md 표 셀 안에 그대로 있다) 를
      쓴다. **굵게(`**`)** 는 <b> 로 바꾸고, 숫자는 class="num" 으로 감싼다.
    """
    text = str(value).strip() if value is not None else ""
    if not text:
        return '<span class="todo">[ 없음 ]</span>'
    if text.startswith("todo —") or text.startswith("todo -"):
        return f'<span class="todo">{_html.escape(text)}</span>'

    lines = text.split("<br>") if multiline else [text]
    out = []
    for line in lines:
        esc = _html.escape(line.strip())
        esc = _BOLD.sub(r"<b>\1</b>", esc)
        m = _LABEL_PREFIX.match(esc)
        if m:
            lab = m.group(1)
            esc = f'<span class="lab {_LABEL_CLASS[lab]}">{lab}</span> ' + esc[m.end():]
        if esc.startswith("미확인"):
            esc = '<span class="unknown">미확인</span>' + esc[len("미확인"):]
        out.append(_wrap_numbers(esc))
    return "<br>".join(out)


def _confidence_badge(conf: str) -> str:
    cls, mark = _CONF_BADGE.get(conf or "", ("b-none", "○"))
    return f'<span class="badge {cls}">{mark} {conf or "판정 없음"}</span>'


def _splice(text: str, start: str, end: str, middle: str) -> str:
    """start 부터(포함) end 직전까지를 middle 로 갈아 끼운다. end 는 그대로
    남긴다. start·end 둘 다 본문에 정확히 있어야 한다 — 없으면 템플릿이
    바뀐 것이니 조용히 넘어가지 않고 예외를 낸다."""
    i = text.index(start)
    j = text.index(end, i)
    return text[:i] + middle + text[j:]


def _table(headers: list[str], rows: list[list[str]]) -> str:
    head = "".join(f"<th>{_html.escape(h)}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows
    )
    return f'<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def load_template(path=None) -> str:
    """수업자료/제안서_템플릿.html 을 읽는다. **읽기만 한다.**

    기대했던 위치(mydomain-report/수업자료/)와, 실제로 있던 위치(프로젝트의
    형 폴더) 둘 다 찾아본다. 못 찾으면 예외를 낸다 — §0-1 "형식이 없으면
    만들지 않는다"와 같은 이유로, 템플릿 없이 조용히 다른 구조를 지어내지
    않는다.
    """
    for p in (path, C.ROOT / "수업자료" / "제안서_템플릿.html",
             C.ROOT.parent / "제안서_템플릿.html"):
        if p and __import__("os").path.exists(p):
            with open(p, encoding="utf-8") as f:
                return f.read()
    raise FileNotFoundError(
        "제안서_템플릿.html 을 못 찾았습니다 — 수업자료/ 밑이나 프로젝트 "
        "형 폴더에 두십시오. 템플릿 없이 구조를 새로 지어내지 않습니다.")


def to_html(secs: list[dict], template_path=None) -> str:
    """제안서 절 목록을 제안서_템플릿.html 구조·클래스 그대로 HTML 문서로 만든다.

    - 표지 제목·검증 배지처럼 secs 에 없는 값(제목은 사람이 정하는 것이라
      원래도 이 함수의 데이터가 아니다)은 템플릿의 "[ ]"+class="todo" 를
      **그대로 둔다.**
    - 1.발견(퍼널)·2.원인 절은 이 모듈(제안카드 기반)이 계산하지 않는 값이라
      템플릿 예시를 그대로 둔다 — report.sections.py 쪽 데이터가 필요하다.
    - 숫자에는 class="num" 을 붙인다. 외부 CSS·이미지·CDN 은 템플릿에도
      원래 없다 — <style> 을 그대로 문서 안에 넣는 단일 파일이다.
    """
    html = load_template(template_path)

    by_title = {s["title"]: s for s in secs}
    summary_lines = by_title.get("1. 한 장 요약", {}).get("body", "").split("\n")
    finding = summary_lines[0].split(": ", 1)[-1] if len(summary_lines) > 0 else ""
    uncertain = summary_lines[2].split(": ", 1)[-1] if len(summary_lines) > 2 else ""
    basis = summary_lines[3].split(": ", 1)[-1] if len(summary_lines) > 3 else ""

    appendix_rows = (by_title.get("7. 부록 — 근거 상세", {})
                     .get("tables", [{}])[0].get("rows", []))
    conf_by_title = {r["제목"]: r.get("반증 확신도", "") for r in appendix_rows}
    rebuttal_rows = [r for r in appendix_rows if (r.get("받은 반박") or "").strip()]

    rows_by_class = {
        label: (by_title.get(title, {}).get("tables", [{}])[0].get("rows", []))
        for label, title in zip(_ORDER, ["2. 하지 말 것", "3. 다시 할 것", "4. 할 것"])
    }

    # ── 표지 메타 — 데이터셋·기간은 config 값이라 채운다. 작성일·검증
    # 결과는 secs 에 없는 값이라(카드 파일 메타·검증 결과는 이 함수의
    # 입력이 아니다) 템플릿의 todo 를 그대로 둔다.
    meta = (
        f'<div class="meta">'
        f'<span>데이터셋 <b class="num">{_html.escape(C.DATASET)}</b></span>'
        f'<span>기간 <b class="num">{C.PERIOD[0]} ~ {C.PERIOD[1]}</b></span>'
        f'<span>작성 <b class="num todo">[ 날짜 ]</b></span>'
        f'<span>검증 <b><span class="badge b-none">○ <span class="todo">'
        f'[ 통과/경고/차단 ]</span></span></b></span></div>')
    html = _splice(html, '<div class="meta">', '\n</div>\n\n<!-- ══════════════ 한 장 요약', meta)

    # ── 한 장 요약 — _s1_summary() 가 이미 이 넷을 계산해 뒀다.
    plist = "".join(
        f'<li><span class="n">{_PROP_META[label][1][0]}</span><span>'
        f'<span class="badge {_PROP_META[label][2]}">{_PROP_META[label][3]} {label}</span> '
        + (", ".join(_render_value(r["제안"], multiline=False) for r in rows_by_class[label])
           if rows_by_class[label] else '<span class="todo">[ 없음 ]</span>')
        + '</span></li>'
        for label in _ORDER
    )
    summary = (
        '<div class="summary"><h2>한 장 요약</h2>'
        f'<div class="srow"><div class="k">발견</div><div class="v"><div class="lead">'
        f'{_render_value(finding, multiline=False)}</div></div></div>'
        f'<div class="srow"><div class="k">제안</div><div class="v">'
        f'<ul class="plist">{plist}</ul></div></div>'
        f'<div class="srow"><div class="k">불확실</div><div class="v">'
        f'{_render_value(uncertain, multiline=False)}</div></div>'
        f'<div class="srow"><div class="k">근거</div><div class="v small">'
        f'{_render_value(basis, multiline=False)}</div></div>'
        '</div>')
    html = _splice(html, '<div class="summary">',
                   '<!-- ══════════════ 1. 발견 ══════════════ -->', summary)

    # ── 3. 제안 — 분류당 카드 하나뿐이던 템플릿 예시를, 실제 카드 수만큼
    # 늘린다. 순서는 §본문 순서(하지 말 것 → 다시 할 것 → 할 것)를 지킨다.
    cards_html = []
    for label in _ORDER:
        cls, cls_label, *_rest = _PROP_META[label]
        for row in rows_by_class[label]:
            conf = conf_by_title.get(row["제안"], "")
            cards_html.append(
                f'<div class="prop {cls}"><div class="cls">{cls_label}</div>'
                f'<h4>{_render_value(row["제안"], multiline=False)}</h4><dl>'
                f'<dt>근거</dt><dd>{_render_value(row.get("근거"))}</dd>'
                f'<dt>비용</dt><dd>{_render_value(row.get("비용"))}</dd>'
                f'<dt>효과</dt><dd>{_render_value(row.get("효과"))}</dd>'
                f'<dt>되돌림</dt><dd>{_render_value(row.get("되돌림"))}</dd>'
                f'<dt>확신도</dt><dd>{_confidence_badge(conf)}</dd>'
                '</dl></div>')
    html = _splice(html, '<div class="prop stop">',
                   '<!-- ══════════════ 4. 틀린다면', "".join(cards_html))

    # ── 4. 이 제안이 틀린다면 — 사람이 안 썼으면(§1 한 장 요약과 달리 자유
    # 문장이라) 템플릿의 두 문단을 그대로 둔다. 철회 조건 콜아웃도 이
    # 함수의 데이터가 아니라 항상 그대로 둔다.
    falsify_body = (by_title.get("5. 이 제안이 틀린다면", {}).get("body") or "").strip()
    if falsify_body:
        html = _splice(
            html, '<p><b>가장 큰 위험은', '<div class="callout stop">',
            f'<p>{_render_value(falsify_body)}</p>\n\n')

    # ── 5. 적용 — 후보(guide)는 판단기준.md 에서 그대로 왔다. "적용하면
    # 무엇이 달라지나"는 카드에 없는 판단이라 칸마다 todo 로 남긴다.
    apply_sec = by_title.get("6. 적용", {})
    candidates = apply_sec.get("guide") or []
    apply_rows = [[_render_value(c, multiline=False),
                  '<span class="todo">[ 우리 어느 일에 적용하면 무엇이 달라지나 ]</span>']
                 for c in candidates]
    if apply_rows:
        html = _splice(
            html, '<table>\n  <thead><tr><th>판단 기준</th>',
            '\n\n<p class="small"><span class="todo">이번에 못 한 것',
            _table(["판단 기준", "어디에 적용하면 무엇이 달라지나"], apply_rows))
    apply_body = (apply_sec.get("body") or "").strip()
    if apply_body:
        html = _splice(
            html, '<p class="small"><span class="todo">이번에 못 한 것',
            '\n\n\n<!-- ══════════════ 부록',
            f'<p class="small"><b>다음에 볼 것 —</b> {_render_value(apply_body)}</p>')

    # ── 부록 A · 근거 상세 — 7.부록 표 전체를 옮긴다.
    if appendix_rows:
        cols = ["제목", "분류", "근거", "비용", "효과", "되돌림"]
        rows = [[_render_value(r.get(c), multiline=(c in ("근거", "효과")))
                for c in cols] for r in appendix_rows]
        html = _splice(
            html, '<p class="small"><span class="todo">[ 분해 표 전체',
            '\n\n<h2 class="sec">부록 B', _table(cols, rows))

    # ── 부록 D · 검토 이력 — 받은 반박이 있는 카드만 옮긴다. 없으면
    # 템플릿의 빈 예시 행을 그대로 둔다.
    if rebuttal_rows:
        rows = [[_render_value(r["받은 반박"]), _render_value(r.get("반박 처리"))]
               for r in rebuttal_rows]
        html = _splice(
            html, '<table>\n  <thead><tr><th>지적</th>',
            '\n\n<h2 class="sec">부록 E', _table(["지적", "처리"], rows))

    return html


# ── PDF 로 내보내기 (report.to_pdf.build_pdf() 와 같은 방식) ────────────
# 표지·목차·장 구분·한글 폰트는 report.to_pdf.Report 를 그대로 재사용한다
# (새로 만들지 않는다). 다만 본문은 build_pdf() 의 pdf.table() 그리드를
# 안 쓴다 — 카드의 근거·비용·효과·되돌림은 문단 길이라 fpdf2 의 표는 한
# 행 안에 다 못 넣으면 예외를 낸다(직접 겪어서 확인함). 그래서 카드 하나를
# 라벨 + multi_cell 문단 블록으로 그린다.
_PROP_TITLES = {"2. 하지 말 것", "3. 다시 할 것", "4. 할 것"}


def _pdf_card(pdf, title: str, fields: dict, confidence: str | None = None) -> None:
    pdf.set_font(pdf.base, "B", 11)
    pdf.set_text_color(*INK)
    pdf.multi_cell(0, 6.5, title or "(제목 없음)")
    pdf.ln(1)
    for label, value in fields.items():
        text = str(value).replace("<br>", "\n").strip() if value else "미확인"
        pdf.set_font(pdf.base, "B", 9)
        pdf.set_text_color(*MUTED)
        pdf.cell(0, 5, label, new_x="LMARGIN", new_y="NEXT")
        pdf.set_font(pdf.base, "", 9.5)
        pdf.set_text_color(*INK)
        pdf.multi_cell(0, 5.3, text)
        pdf.ln(0.5)
    if confidence is not None:
        pdf.set_font(pdf.base, "B", 9)
        pdf.set_text_color(*MUTED)
        pdf.cell(0, 5, f"확신도  {confidence or '판정 없음'}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.set_draw_color(*LINE)
    pdf.set_line_width(0.2)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(5)


def to_pdf(secs: list[dict], title: str = "제안서") -> bytes:
    """제안서 절 목록을 PDF로 만든다.

    표지 + 목차 + 장 구분은 report.to_pdf.build_pdf() 와 같은 순서·모양을
    쓴다. 절 안 내용만 다르게 그린다 — 2~4장(카드 분류)·7장(부록)은
    카드 하나당 _pdf_card() 블록으로, 1·5·6장은 본문 문단 + (있으면)
    참고 가이드 불릿으로 그린다.
    """
    pdf = Report()

    # ── 표지 + 목차 — build_pdf() 와 같은 순서 ─────────────────────
    pdf.add_page()
    pdf.ln(40)
    pdf.set_font(pdf.base, "B", 26)
    pdf.set_text_color(*INK)
    pdf.multi_cell(0, 12, title, align="L")
    pdf.ln(6)
    pdf.set_draw_color(*_hex(C.BRAND["primary"]))
    pdf.set_line_width(1.2)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + 40, pdf.get_y())
    pdf.ln(10)
    pdf.set_font(pdf.base, "", 10)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 6, f"생성 {datetime.now(C.KST).strftime('%Y-%m-%d %H:%M')}",
             new_x="LMARGIN", new_y="NEXT")

    pdf.ln(20)
    pdf.set_font(pdf.base, "B", 15)
    pdf.set_text_color(*INK)
    pdf.cell(0, 10, "목차", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    for s in secs:
        pdf.set_font(pdf.base, "", 11)
        pdf.set_text_color(*INK)
        mark = "" if s["kind"] == "auto" else "  (사람 작성)"
        pdf.cell(0, 8, s["title"] + mark, new_x="LMARGIN", new_y="NEXT")

    # ── 본문 ────────────────────────────────────────────────────────
    for i, s in enumerate(secs):
        if i == 0:
            pdf.add_page()
        elif pdf.get_y() > pdf.h - pdf.b_margin - 45:
            pdf.add_page()
        else:
            pdf.ln(12)
        pdf.set_font(pdf.base, "B", 15)
        pdf.set_text_color(*INK)
        pdf.multi_cell(0, 9, s["title"])
        pdf.ln(1)
        pdf.set_draw_color(*LINE)
        pdf.set_line_width(0.3)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
        pdf.ln(6)

        if s["title"] in _PROP_TITLES:
            rows = (s.get("tables") or [{}])[0].get("rows", [])
            if not rows:
                pdf.set_font(pdf.base, "", 10)
                pdf.set_text_color(*MUTED)
                pdf.multi_cell(0, 6, "이 분류의 카드가 없습니다.")
                continue
            for r in rows:
                _pdf_card(pdf, r.get("제안", ""), {
                    "근거": r.get("근거"), "비용": r.get("비용"),
                    "효과": r.get("효과"), "되돌림": r.get("되돌림"),
                })
        elif s["title"] == "7. 부록 — 근거 상세":
            rows = (s.get("tables") or [{}])[0].get("rows", [])
            for r in rows:
                _pdf_card(pdf, r.get("제목", ""), {
                    "분류": r.get("분류"), "근거": r.get("근거"),
                    "비용": r.get("비용"), "효과": r.get("효과"),
                    "되돌림": r.get("되돌림"),
                }, confidence=r.get("반증 확신도"))
        else:
            body = (s.get("body") or "").strip()
            if not body:
                pdf.set_font(pdf.base, "", 10)
                pdf.set_text_color(*MUTED)
                pdf.multi_cell(0, 6, f"[작성되지 않음] {s.get('placeholder', '')}")
            else:
                pdf.set_font(pdf.base, "", 10.5)
                pdf.set_text_color(*INK)
                for para in body.split("\n"):
                    pdf.multi_cell(0, 6.2, para.strip())
                    pdf.ln(2)
            if s.get("guide"):
                pdf.ln(2)
                pdf.set_font(pdf.base, "B", 9.5)
                pdf.set_text_color(*MUTED)
                pdf.cell(0, 6, "참고 가이드", new_x="LMARGIN", new_y="NEXT")
                pdf.set_font(pdf.base, "", 9.5)
                for g in s["guide"]:
                    pdf.multi_cell(0, 5.5, f"· {g}")
                    pdf.ln(0.5)

    out = pdf.output()
    return bytes(out)
