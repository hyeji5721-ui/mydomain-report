# -*- coding: utf-8 -*-
"""리포트 8장 조립.

────────────────────────────────────────────────────────────────────
자동으로 쓰는 장과 사람이 쓰는 장이 나뉜다. 가르는 질문은 하나다.

    이 문장이 틀렸을 때 누가 책임지는가?
        사람이 진다        → 사람이 쓴다   (2 배경 · 6 해석 · 8 제안)
        사실이 틀린 것뿐   → 자동으로 쓴다 (1 요약 · 3 방법 · 4 결과 · 5 실험 · 7 한계)

**해석과 제안을 자동화하는 순간 책임이 사라진다.** 그것이 이 수업의 결론이다.
────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import datetime

from core import config as C, metrics as M, validate as V
from core.todo import todo

# ★ 자동 생성 문장에 인과를 단정하는 말을 쓰지 않는다.
#   관측 데이터로는 인과를 주장할 수 없는데, 방심하면 자동 문장이 인과를 쓴다.
#   내 도메인에만 있는 단정 표현이 있으면 여기에 더한다.
BANNED = ["때문에", "덕분에", "효과로", "입증되었", "증명되었", "확실히",
          "기여하였다", "제고되었다", "개선되었음이 확인됨", "견인했다",
          "성공적으로", "유의미한"]

# 금지어를 피하는 것만으로는 문장이 안 나온다 — 두 지표를 엮어 써야 할 때
# 쓸 안전한 형태도 같이 있어야 한다. 인과어를 빼고 "A가 낮다"만 남기면 한
# 지표만 말할 수 있다. 두 지표를 관계 짓고 싶을 때는 구간을 나눠 나란히
# 놓는다 — "A 때문에 B" 대신 "A가 낮은 구간에서 B도 낮다". 관계는 말하되
# 방향(무엇이 무엇을 일으켰는지)은 주장하지 않는다.
SAFE_PHRASING_EXAMPLE = 'A가 낮은 구간에서 B도 낮다'


def check_phrasing(text: str) -> list[str]:
    """자동 생성 문장에 인과 단정 표현이 섞였는지 스스로 검사한다.

    **그대로 쓴다.** 사람이 쓴 장에도 걸어라 — 사람이 더 자주 쓴다.
    """
    return [w for w in BANNED if w in text]


def check_placeholders(text: str) -> list[str]:
    """예시 문장의 [ ] 자리표시자가 안 지워지고 남았는지 검사한다.

    **그대로 쓴다.** check_phrasing() 과 같은 자리다 — 저장을 막지 않고
    경고만 한다. 채우거나 지우는 것은 사람의 몫이다.
    """
    return re.findall(r"\[([^\[\]]*)\]", text)


def _fmt(n, unit=""):
    return f"{n:,.0f}{unit}"


# ── 자동으로 쓰는 장 ──────────────────────────────────────────────
def _s1_summary(t: dict) -> dict:
    """1. 요약

    **수치는 쓰되 인과는 쓰지 않는다.** "A가 낮다"는 되고 "B 때문에 A가 낮다"는 안 된다.
    두 지표를 엮어 써야 하면 SAFE_PHRASING_EXAMPLE 형태("A가 낮은 구간에서
    B도 낮다")로 쓴다 — 관계는 말하되 방향은 주장하지 않는다.
    다 쓰고 나서 check_phrasing() 으로 자기 문장을 검사한다.

    ★ metrics.kpis() 가 돌려주는 지표를 **그대로** 쓴다 — 이름·값을 여기서
    다시 계산하거나 외워 적지 않는다. kpis() 가 지표를 더하거나 빼도 이
    함수는 그대로 맞게 돈다.

    ★ 2026-09-05: 지표를 "kpi_cards"(카드용 구조화 값)로도 반환한다 — 화면
    (st.metric)과 PDF(색 있는 박스)가 각자 강조해서 그린다("tables"와 같은
    화면/PDF 분리 패턴). 값은 카드가 이미 크게 보여주므로 body 의 불릿 나열은
    없애고 짧은 안내 한 줄만 남겼다 — 같은 숫자를 텍스트로 또 나열하면 카드
    바로 위에서 중복된다.

    반환: {"title": "1. 요약", "kind": "auto", "body": "...", "kpi_cards": [...]}
    """
    k = M.kpis(t)
    kpi_cards = [
        {"name": name, "value": v["fmt"].format(v["value"]),
         "status": M.status_of(name, v["value"])}
        for name, v in k.items()
    ]
    body = "이 리포트가 보는 지표는 아래와 같습니다."
    return {"title": "1. 요약", "kind": "auto", "body": body, "kpi_cards": kpi_cards}


def _s3_method(t: dict) -> dict:
    """3. 방법

    **분석 단위(그레인)를 반드시 밝힌다.** 읽는 사람이 숫자를 다시 세어볼 수 있어야 한다.
    무엇을 어떻게 셌는지, 무엇을 뺐는지, 어떤 검정을 썼는지.

    지표의 정의는 **위키가 원본**이다. 여기서 새로 정의하지 않는다.

    ★ 여기 나오는 건수(590·64 등)는 t 에서 그때그때 다시 센다 — 데이터가
    갱신되면 이 문장도 같이 갱신된다. 글자로 박아 두지 않는다.
    """
    pl, ev = t["plans"], t["plan_stage_events"]
    n_plans = len(pl)
    n_dup = int(ev.duplicated().sum())
    body = (
        f"분석 단위는 계획안 1건입니다. plan_id 로 고유하게 셉니다.\n"
        f"데이터 기간은 {C.PERIOD[0]} ~ {C.PERIOD[1]}이고, plans 는 {n_plans}건입니다.\n"
        f"단계 통과는 plan_stage_events 에서 완전중복 {n_dup}행을 제거한 뒤, "
        f"result가 \"통과\"인 행만 도달로 셉니다.\n"
        f"주지표(전체 통과율)는 2026 코호트도 포함해서 봅니다. 가드레일(계획-실적 "
        f"괴리율)은 2025년까지만 봅니다 — 2026년 확정배포 건 중 plan_actuals 가 "
        f"0건이라 실적 대조 자체가 아직 존재하지 않기 때문입니다."
    )
    return {"title": "3. 방법", "kind": "auto", "body": body}


def _bottleneck_by_department(t: dict):
    """병목 구간을 찾아 department_name 으로 쪼갠 결과까지 한 번에 돌려준다.

    4장(결과)과 사람이 쓰는 장의 가이드(2·6·8장)가 같은 분해를 쓴다 — 두 곳에서
    따로 계산하면 병목이 옮겨갔을 때 한쪽만 갱신될 수 있으므로 한 곳에 둔다.

    반환: (f, bn, step_from, step_to, by_dept)
    """
    f = M.funnel(t["plan_stage_events"])
    bi = max(int(f.index[f.is_bottleneck][0]), 1)
    bn = f.iloc[bi]
    step_from, step_to = f.step.iloc[bi - 1], bn.step
    by_dept = M.funnel_by(t, "department_name", step_from, step_to)
    return f, bn, step_from, step_to, by_dept


def _s4_results(t: dict) -> dict:
    """4. 결과

    숫자를 나열하되 **해석하지 않는다.** 해석은 6장이고 사람이 쓴다.
    "낮다"까지가 결과이고 "왜 낮은가"는 해석이다.

    ★ metrics.funnel() 의 단계별 값과, 병목 구간을 department_name 으로 쪼갠
    metrics.funnel_by() 분해 결과를 나열한다. 병목 구간(step_from → step_to)은
    f.is_bottleneck 에서 매번 다시 찾는다 — 데이터가 바뀌어 병목이 옮겨가도
    이 문장이 따라간다.

    2026-09-05 에 병목 원인 후보 표 둘을 더했다 — briefing_pass_rate()(사전
    설명회 여부)·prep_days_by_outcome()(준비기간). **여전히 해석하지 않는다** —
    "사전 설명회를 안 해서 반려됐다"는 문장은 안 쓰고, "실시 여부에 따라 통과율이
    이렇게 갈린다"는 사실만 표로 보여준다. 인과 해석은 6장 몫이다. 둘 다 아직
    병목 구간에만 값이 있는 컬럼이라(metrics.py 참고) 표본이 비면(다른 구간이면)
    빈 리스트가 돼 표 자체를 안 붙인다.

    단계별·부서별·원인 후보 숫자는 본문 텍스트가 아니라 "tables"(캡션 + 행
    딕셔너리 목록의 리스트)로 반환한다 — 화면(st.dataframe)과 PDF(fpdf2
    pdf.table())가 각자 표로 그린다. 2026-09-05 변경: 전엔 단계·부서 숫자 다
    "- 라벨 N건 (…)" 줄글로 body 에 있었는데, 특히 부서별은 13줄이 그대로
    나열돼 읽기 힘들다는 지적이 있었다.

    charts 키에 차트 이름을 넣으면 PDF에 그려진다.
    """
    f, bn, step_from, step_to, by_dept = _bottleneck_by_department(t)

    funnel_table = [
        {"단계": row.label, "도달": int(row.n),
         "직전 단계 대비": None if row.step_rate != row.step_rate
                         else round(row.step_rate * 100, 2),
         "1단계 대비 누적": round(row.cum_rate * 100, 2)}
        for _, row in f.iterrows()
    ]

    covered = float(by_dept.비중.sum())
    dim_col = by_dept.columns[0]
    dept_table = [
        {"부서": getattr(r, dim_col), "도달": int(r.도달), "전환": int(r.전환),
         "전환율": round(r.전환율 * 100, 2)}
        for r in by_dept.sort_values("전환율").itertuples()
    ]

    briefing = M.briefing_pass_rate(t, step_to)
    briefing_table = [
        {"사전 설명회": r.pre_briefing, "도달": int(r.n),
         "전환율": round(r.pass_rate, 2)}
        for r in briefing.itertuples()
    ]

    prep = M.prep_days_by_outcome(t, step_to)
    prep_table = [
        {"결과": r.outcome, "도달": int(r.n),
         "평균 준비기간(일)": round(r.prep_days, 1)}
        for r in prep.itertuples()
    ]

    body = (
        "퍼널 단계별 도달 수와 전환율은 아래와 같습니다.\n\n"
        f"가장 낮은 전환율 구간은 {bn.label} 직전 단계 대비 "
        f"{bn.step_rate * 100:.2f}%입니다.\n\n"
        f"이 구간({C.FUNNEL_LABELS.get(step_from, step_from)} → "
        f"{C.FUNNEL_LABELS.get(step_to, step_to)})을 부서별로 나눈 값은 "
        f"아래와 같습니다 (표본 {C.MIN_CELL_SAMPLE}건 미만 부서는 제외, "
        f"표시된 부서의 비중 합 {covered * 100:.1f}%).\n\n"
        "같은 구간을 사전 설명회 실시 여부·준비기간(착수~제출 소요일)으로 "
        "나눈 값도 아래와 같습니다."
    )

    tables = [
        {"caption": "퍼널 단계별", "rows": funnel_table},
        {"caption": f"{bn.label} 직전 구간 부서별 분해", "rows": dept_table},
    ]
    if briefing_table:
        tables.append({"caption": f"{bn.label} 직전 구간 사전 설명회 여부별 전환율",
                       "rows": briefing_table})
    if prep_table:
        tables.append({"caption": f"{bn.label} 직전 구간 통과/반려별 평균 준비기간",
                       "rows": prep_table})

    return {"title": "4. 결과", "kind": "auto", "body": body,
            "tables": tables,
            "charts": ["funnel", "device"]}


def _s5_experiments(t: dict) -> dict:
    """5. 실험 — 이 도메인엔 A/B 실험(무작위 배정)이 없어 전후 비교로 대체한다

    **무효 판정된 실험은 사유만 적고 수치를 쓰지 않는다.** 화면에서 감춘 숫자를
    리포트에 쓰면 감춘 의미가 없다.

    ★ metrics.experiment_results() 대신 metrics.cohort_cards() 를 쓴다 — 연도
    코호트를 앞뒤로 이은 전후 비교다. cohort_compare() 의 판정 순서(못 믿을
    조건 → 주지표 → 가드레일)를 계산 앞으로 옮긴 것과 이어진다: verdict 가
    "가드레일 없음"·"효과 없음"인 코호트는 그 값이 계산되지 않았거나 화면에서
    감춘 값이므로, 여기서도 reason 문장만 적고 primary·guardrail 의 실제
    값(퍼센트)은 쓰지 않는다.

    2026-09-05: 코호트별 문장 나열을 표(tables)로 바꿨다 — 4장과 표기를
    맞췄다. 전/후/증감을 한 칸에 문자열로 합쳐서(예: "76.07% → 69.49%
    (-6.58%p)") 넣는다 — 세 칸으로 쪼개면 코호트마다 6개 숫자 칸이 생겨
    "사유" 문장 하나 놓을 자리가 더 좁아진다. 감춘 코호트는 이 칸에 "-"만
    넣고 사유 칸만 채운다.

    실험이 없으므로 **"인과를 주장할 수 없다"를 첫 문단(본문)에 남긴다** — 각주가
    아니다.
    """
    HIDDEN_VERDICTS = {"가드레일 없음", "효과 없음"}
    cards = M.cohort_cards(t)

    rows = []
    for r in cards:
        cohort = f"{r['base']} → {r['comp']}"
        if r["verdict"] in HIDDEN_VERDICTS:
            rows.append({"코호트": cohort, "판정": r["verdict"],
                        "전체 통과율": "-", "계획-실적 괴리율": "-",
                        "사유": r["reason"]})
            continue
        p, g = r["primary"], r["guardrail"]
        primary_str = f"{p['base']:.2f}% → {p['comp']:.2f}% ({p['delta']:+.2f}%p)"
        guard_str = (f"{g['base']:.2f}%p → {g['comp']:.2f}%p ({g['delta']:+.2f}%p)"
                    if g else "-")
        rows.append({"코호트": cohort, "판정": r["verdict"],
                    "전체 통과율": primary_str, "계획-실적 괴리율": guard_str,
                    "사유": r["reason"]})

    body = (
        "이 도메인에는 A/B 실험(무작위 배정)이 없습니다. 아래는 연도 코호트를 "
        "앞뒤로 이은 전후 비교이고, 무작위 배정이 아니므로 인과를 주장할 수 "
        "없습니다."
    )
    return {"title": "5. 실험", "kind": "auto", "body": body,
            "tables": [{"caption": "연도 코호트 전후 비교", "rows": rows}]}


# 사람이 st.data_editor 에서 "출처" 를 고르는 칸. 3개뿐이다 — 한계는 이
# 셋에서만 온다는 것이 7장의 원래 규칙이다(검증 경고 · 못 한 것 · 찾았는데 없음).
# **"찾았는데 없음"도 반드시 적는다 — "없음"도 결과다.** 안 적으면 다음
# 사람이 같은 것을 또 찾는다. (division_type 무격차가 이 칸에 들어간다)
LIMITS_SOURCES = ["검증 경고", "못 한 것", "찾았는데 없음"]

# **늘 있는 한계는 표에 안 올린다.** 이 둘은 "찾은 것"이 아니라 이 리포트가
# 구조적으로 못 답하는 것이라 표에서 지울 수 있게 두면 안 된다 — 항상 고정으로
# 붙인다.
_LIMITS_ALWAYS = [
    "관측 데이터이므로 인과를 주장할 수 없습니다.",
]


def limits_always(t: dict) -> list[str]:
    return _LIMITS_ALWAYS + [
        f"기간이 {C.PERIOD[0]} ~ {C.PERIOD[1]} 이므로 그보다 긴 주기의 변화는 "
        "관측되지 않습니다."]


def _limits_rows(t: dict) -> list[dict]:
    """7. 한계에 올릴 사실을 (출처, 내용) 행으로 조립한다. t 에서 매번 다시 센다.

    ★ 이 목록이 st.data_editor 의 초깃값이다 — pages/3_리포트.py 가 사람이
    지우거나 새로 추가한 행과 이 목록을 대조해서 "원래 있던 행을 지웠다"를
    판단한다. 여기서 이름·문구를 바꾸면 지우지 않았는데도 지운 것으로 잡힌다.
    """
    rows = []

    checks = V.run_checks(t)
    for c in checks:
        if c["level"] == "warn":
            rows.append({"출처": "검증 경고", "내용": f"{c['name']}: {c['msg']}"})
        for clause in c.get("detail", "").split(" · "):
            if "한계로 옮기십시오" in clause:
                fact = clause.split(" — ")[0].strip()
                rows.append({"출처": "못 한 것", "내용": f"{fact}."})

    for r in M.cohort_cards(t):
        if r.get("untrust"):
            rows.append({"출처": "못 한 것",
                        "내용": (f"{r['base']} → {r['comp']} 코호트는 가드레일을 "
                               f"판정하지 못했습니다 — {r['reason']}.")})

    pl, pa = t["plans"], t["plan_actuals"]
    confirmed = pl.loc[pl.final_status == "확정배포", "plan_id"].astype(str)
    has_actual = set(pa.plan_id.astype(str))
    n_confirmed = len(confirmed)
    n_covered = int(confirmed.isin(has_actual).sum())
    n_missing = n_confirmed - n_covered
    missing_years = sorted(pl.loc[confirmed[~confirmed.isin(has_actual)].index,
                                  "cycle_year"].unique().tolist())
    years_str = "·".join(f"{y}" for y in missing_years) + "년으로"
    rows.append({"출처": "못 한 것",
                "내용": (f"계획-실적 괴리율(plan_actuals)은 확정배포 {n_confirmed}건 "
                       f"중 {n_covered}건에만 존재합니다. 나머지 {n_missing}건은 "
                       f"전부 {years_str}, 실적 대조 기간이 아직 안 지나 존재하지 "
                       "않습니다.")})
    rows.append({"출처": "못 한 것",
                "내용": ("부서 축(department_name) 15칸 중 IT팀(27건)·해외사업팀"
                       f"(28건) 2칸은 표본 {C.MIN_CELL_SAMPLE}건 미만이라 병목 구간 "
                       "전환율을 판정하지 않았습니다.")})
    rows.append({"출처": "찾았는데 없음",
                "내용": ("division_type(사업부/지원부서)으로 병목 구간을 쪼개 "
                       "확인했으나 격차가 0.2%p 로 실제로 갈리지 않았습니다 — "
                       "판정 축에서는 뺐고 화면 후보로만 남겼습니다.")})
    return rows


def render_limits(t: dict, rows: list[dict]) -> str:
    """행 목록에서 "포함" 이 True(또는 없음 — 기본값)인 것만 본문으로 합친다."""
    lines = [f"- {s}" for s in limits_always(t)]
    lines += [f"- [{r['출처']}] {r['내용']}"
             for r in rows if r.get("포함", True)]
    return "\n".join(lines)


def _s7_limits(t: dict) -> dict:
    """7. 한계 — 검증 경고에서 조립하고, 화면에서 사람이 고칠 수 있다

    **사람이 매번 쓰는 것이 아니라 경고를 그대로 옮긴다.** 검증에서 경고가
    났는데 한계에 안 적히면 **그 경고는 사라진 것과 같다.**

    ★ pages/3_리포트.py 가 이 함수의 rows 를 st.data_editor 초깃값으로 보여주고
    사람이 행을 끄거나(포함 체크) 지우거나 새로 추가하게 한다. 그 편집 결과는
    build() 의 limits_rows 인자로 다시 들어와 이 함수의 rows 를 덮어쓴다 —
    이 함수 자체는 항상 "지금 데이터라면 무엇이 있어야 하는가"만 다시 계산한다.

    반환의 "rows" 는 편집 UI 의 초깃값이자, 사람이 원래 있던 행을 지웠는지
    판단하는 기준(원본)이다. "body" 는 rows 를 그대로(전부 포함) 렌더링한
    기본값이다 — 편집되지 않았을 때 화면·PDF에 쓰인다.
    """
    rows = _limits_rows(t)
    body = render_limits(t, rows)
    return {"title": "7. 한계", "kind": "auto", "body": body, "rows": rows}


# ── 사람이 쓰는 장 (제공) ─────────────────────────────────────────
# **가이드는 사실만 나열한다.** "왜"·"무엇을 할지"는 여기서 판단하지 않는다 —
# 그 판단을 넘기면 이 장을 사람이 쓰는 이유(책임 소재)가 사라진다. 가이드가
# 하는 일은 사람이 찾아보지 않아도 되게 숫자를 한곳에 모아 주는 것뿐이다.
GUIDE_DISCLAIMER = ("이 내용은 지금 데이터로 자동 생성한 참고용 가이드입니다. "
                    "그대로 쓰지 말고, 담당자가 검토하여 직접 작성한 뒤 확정하십시오.")


def _guide_background(t: dict) -> list[str]:
    """2. 배경 가이드 재료 — 지금 지표 상태와 최근 코호트 판정만 보여준다."""
    k = M.kpis(t)
    _, bn, step_from, step_to, _ = _bottleneck_by_department(t)
    cards = M.cohort_cards(t)
    lines = [
        f"{name} {v['fmt'].format(v['value'])} "
        f"(판정: {_STATUS_KO[M.status_of(name, v['value'])]})"
        for name, v in k.items()
    ]
    lines.append(
        f"퍼널 병목 구간: {C.FUNNEL_LABELS.get(step_from, step_from)} → "
        f"{C.FUNNEL_LABELS.get(step_to, step_to)} (직전 단계 대비 {bn.step_rate * 100:.2f}%)")
    if cards:
        latest = cards[-1]
        lines.append(f"가장 최근 전후 비교({latest['base']}→{latest['comp']}) 판정: "
                     f"\"{latest['verdict']}\"")
    return lines


def _guide_interpretation(t: dict) -> list[str]:
    """6. 해석 가이드 재료 — 병목 구간의 부서별 격차·원인 후보(사전 설명회·
    준비기간)·코호트 판정 분포를 보여준다."""
    _, bn, step_from, step_to, by_dept = _bottleneck_by_department(t)
    worst = by_dept.sort_values("전환율").head(3)
    dim = by_dept.columns[0]
    lines = [
        f"가장 낮은 전환율 구간: {C.FUNNEL_LABELS.get(step_from, step_from)} → "
        f"{C.FUNNEL_LABELS.get(step_to, step_to)} ({bn.step_rate * 100:.2f}%)",
    ]
    lines.append(
        "이 구간에서 전환율이 가장 낮은 부서 3곳: " +
        ", ".join(f"{r[dim]} {r.전환율 * 100:.2f}%" for _, r in worst.iterrows()))

    briefing = M.briefing_pass_rate(t, step_to)
    if len(briefing):
        lines.append(
            "같은 구간 사전 설명회 여부별 전환율: " +
            ", ".join(f"{r.pre_briefing} {r.pass_rate:.2f}%"
                     for r in briefing.itertuples()))
    prep = M.prep_days_by_outcome(t, step_to)
    if len(prep):
        lines.append(
            "같은 구간 통과/반려별 평균 준비기간: " +
            ", ".join(f"{r.outcome} {r.prep_days:.1f}일"
                     for r in prep.itertuples()))

    counts = Counter(r["verdict"] for r in M.cohort_cards(t))
    lines.append("전후 비교 코호트 판정 분포: " +
                ", ".join(f"{k} {v}건" for k, v in counts.items()))
    return lines


def _guide_proposal(t: dict) -> list[str]:
    """8. 제안 가이드 재료 — 주의가 필요한 지표·코호트 목록만 보여준다. 무엇을
    할지는 정하지 않는다 — 후보를 추리는 재료만 준다."""
    k = M.kpis(t)
    flagged = [name for name, v in k.items()
              if M.status_of(name, v["value"]) in ("warn", "block")]
    attention = [f"{r['base']}→{r['comp']}(\"{r['verdict']}\")"
                for r in M.cohort_cards(t) if r["verdict"] in ("주의 필요", "가드레일 없음")]
    _, bn, step_from, step_to, by_dept = _bottleneck_by_department(t)
    lines = [
        ("임계값 기준 주의/위험 지표: " + ", ".join(flagged)) if flagged else
        "임계값 기준 주의/위험 지표 없음",
        f"병목 구간({C.FUNNEL_LABELS.get(step_from, step_from)} → "
        f"{C.FUNNEL_LABELS.get(step_to, step_to)}) 판정 대상 부서 {len(by_dept)}개 "
        f"(표본 {C.MIN_CELL_SAMPLE}건 미만 부서는 4장에서 제외)",
    ]
    briefing = M.briefing_pass_rate(t, step_to)
    if len(briefing):
        lines.append(
            "같은 구간 사전 설명회 여부별 전환율: " +
            ", ".join(f"{r.pre_briefing} {r.pass_rate:.2f}%"
                     for r in briefing.itertuples()) +
            " — 개입 가능한 프로세스 레버 후보")
    if attention:
        lines.append("전후 비교에서 주의가 필요한 코호트: " + ", ".join(attention))
    return lines


# 예시 문장 — 텍스트 박스의 초기값으로 그대로 들어간다(순수 텍스트라 HTML
# 태그를 안 쓴다). 가이드의 사실을 문장으로 옮긴 부분까지만 완성하고, 판단이
# 들어가는 부분은 [...] 로 비워 둔다 — 그대로 제출하면 대괄호가 리포트에
# 그대로 실리므로, 저장 전에 반드시 채우거나 지워야 한다(pages/3_리포트.py 참고).
_STATUS_KO = {"ok": "정상", "warn": "주의", "block": "차단", "none": "판정 없음"}


def _i_ga(word: str) -> str:
    """받침 유무로 주격 조사 '이/가' 를 고른다. 지표 이름을 "…이 판정됐습니다"
    처럼 피동문 주어 자리에 그대로 끼워 넣을 때 쓴다."""
    if not word:
        return "가"
    code = ord(word[-1]) - 0xAC00
    has_batchim = 0 <= code < 11172 and code % 28 != 0
    return "이" if has_batchim else "가"


def _example_background(t: dict) -> str:
    """2. 배경 예시. 사실만 문장으로 옮기고, "왜 하는가"는 괄호로 남긴다.

    줄바꿈: 서두 문장 → 지표 불릿 → 빈 줄 → 판단 질문. 한 문장에 다 몰아
    쓰면 텍스트 박스 안에서 읽기 어렵다.
    """
    k = M.kpis(t)
    _, bn, step_from, step_to, _ = _bottleneck_by_department(t)
    bullets = [f"- {name} {v['fmt'].format(v['value'])}"
              f"({_STATUS_KO[M.status_of(name, v['value'])]})"
              for name, v in k.items()]
    bullets.append(
        f"- 병목 구간: {C.FUNNEL_LABELS.get(step_from, step_from)} → "
        f"{C.FUNNEL_LABELS.get(step_to, step_to)} "
        f"(직전 단계 대비 {bn.step_rate * 100:.2f}%)")
    return (
        "2026년 경영계획 수립 결과를 검토하기 위해 이 분석을 진행했습니다.\n\n"
        + "\n".join(bullets) +
        "\n\n[어떤 의사결정을 앞두고 이 분석을 하는지 적으십시오]")


def _example_interpretation(t: dict) -> str:
    """6. 해석 예시. 원인을 단정하지 않고 "가릴 수 없다"로 맺어, 판단은 넘긴다.

    줄바꿈: 사실 문장 → (있으면) 원인 후보 문장 → 빈 줄 뒤에 판단 질문.

    2026-09-05: 병목 구간에 원인 후보(사전 설명회·준비기간)가 생겨 한 줄 더
    넣었다 — 상관이지 인과가 아니므로("사전 설명회를 안 해서 반려됐다"는 못
    쓴다) "뚜렷한 차이가 있다"까지만 쓰고, "가릴 수 없다"는 맺음은 그대로 둔다.
    아직 그 구간에 원인 후보 데이터가 없으면(병목이 옮겨가면) 이 줄은 빠진다.
    """
    _, bn, step_from, step_to, _ = _bottleneck_by_department(t)
    briefing = M.briefing_pass_rate(t, step_to)
    extra = ("같은 구간에서 사전 설명회 실시 여부·준비기간과도 뚜렷한 차이가 "
             "있습니다.\n") if len(briefing) else ""
    return (
        f"병목 구간({C.FUNNEL_LABELS.get(step_from, step_from)} → "
        f"{C.FUNNEL_LABELS.get(step_to, step_to)}) 전환율이 부서에 따라 갈리고 있습니다.\n"
        f"{extra}"
        "이 데이터만으로는 그 격차가 제도 차이인지, 부서 특성인지, 우연인지 가릴 수 없습니다.\n\n"
        "[왜 이런 격차가 났다고 보는지, 추가로 무엇을 확인해야 하는지 적으십시오]")


def _example_proposal(t: dict) -> str:
    """8. 제안 예시. "할 것"과 "안 할 것"이 둘 다 있는 형태를 보여준다.

    줄바꿈: 근거 한 줄 → 빈 줄 → "할 것"/"안 할 것" 두 줄로 나눠, 선택지가
    하나의 뒤엉킨 문장이 아니라 서로 다른 두 결정임을 눈으로 보이게 한다.
    """
    k = M.kpis(t)
    flagged = [name for name, v in k.items()
              if M.status_of(name, v["value"]) in ("warn", "block")]
    subject = flagged[0] if flagged else "주의가 필요한 지표"
    return (
        f"{subject}{_i_ga(subject)} 주의 단계로 판정됐습니다.\n\n"
        "할 것: [무엇을 할지 — 예: 매월 모니터링한다]\n"
        "안 할 것: [무엇을 안 할지 — 예: 원인이 아직 불명확하므로 제도 변경은 보류한다]")


def _s2_background(t: dict, human: dict) -> dict:
    return {
        "title": "2. 배경", "kind": "human",
        "body": human.get("2. 배경", ""),
        "placeholder": "이 분석을 왜 했는지, 어떤 의사결정을 앞두고 있는지 적으십시오.",
        "guide": _guide_background(t), "guide_disclaimer": GUIDE_DISCLAIMER,
        "example": _example_background(t),
    }


def _s6_interpretation(t: dict, human: dict) -> dict:
    return {
        "title": "6. 해석", "kind": "human",
        "body": human.get("6. 해석", ""),
        "placeholder": ("숫자가 무엇을 뜻하는지 적으십시오. "
                        "자동으로 쓰지 않습니다 — 해석은 사람의 책임입니다. "
                        "두 지표를 엮어 쓸 때는 \"A 때문에 B\" 대신 "
                        "\"A가 낮은 구간에서 B도 낮다\"처럼 쓰십시오."),
        "guide": _guide_interpretation(t), "guide_disclaimer": GUIDE_DISCLAIMER,
        "example": _example_interpretation(t),
    }


def _s8_proposal(t: dict, human: dict) -> dict:
    return {
        "title": "8. 제안", "kind": "human",
        "body": human.get("8. 제안", ""),
        "placeholder": ("무엇을 할 것인지, 무엇을 하지 않을 것인지 적으십시오. "
                        "선택하지 않으면 제안이 아니라 보고입니다."),
        "guide": _guide_proposal(t), "guide_disclaimer": GUIDE_DISCLAIMER,
        "example": _example_proposal(t),
    }


# ── 조립 ──────────────────────────────────────────────────────────
def _safe(title: str, fn, *args) -> dict:
    """아직 안 채운 장은 "todo" 종류로 돌려준다. 골격 전용."""
    from core.todo import NotYet
    try:
        return fn(*args)
    except NotYet as e:
        return {"title": title, "kind": "todo", "body": "", "todo": e}


def build(t: dict, human: dict | None = None,
         limits_rows: list[dict] | None = None) -> list[dict]:
    """8장을 조립한다. human 은 사람이 쓴 장의 본문 딕셔너리.

    **순서와 자동/사람 구분은 바꾸지 않는다.** 장 개수는 도메인에 맞게 줄여도 되지만,
    해석과 제안을 자동으로 돌리는 것만은 하지 않는다.

    ★ limits_rows 를 주면 7.한계의 rows(원본은 _s7_limits() 가 t 에서 다시
    계산한 것)를 이 값으로 덮어써 body 를 다시 렌더링한다 — st.data_editor 로
    편집한 결과(행 추가·삭제·"포함" 체크)를 화면과 PDF가 같이 쓰게 하는
    통로다. 안 주면 _s7_limits() 의 기본값(전부 포함)을 그대로 쓴다.
    """
    human = human or {}
    limits = _safe("7. 한계", _s7_limits, t)
    if limits_rows is not None and limits["kind"] == "auto":
        limits = {**limits, "body": render_limits(t, limits_rows),
                 "edited_rows": limits_rows}
    return [
        _safe("1. 요약", _s1_summary, t),
        _s2_background(t, human),
        _safe("3. 방법", _s3_method, t),
        _safe("4. 결과", _s4_results, t),
        _safe("5. 실험", _s5_experiments, t),
        _s6_interpretation(t, human),
        limits,
        _s8_proposal(t, human),
    ]


def email_draft(t: dict, sections: list[dict]) -> dict:
    """이메일 초안. **실제로 보내지 않는다.**

    그대로 쓴다. 이메일 HTML은 인라인 스타일과 표 레이아웃만 쓴다 —
    외부 CSS·자바스크립트·이미지는 대부분의 메일 클라이언트가 막는다.

    받을 사람이 없으면 초안까지만 만들고, 게이트 3은 "보냈다고 치고" 기록만 남긴다.
    """
    summary = next((s["body"] for s in sections if s["title"].startswith("1.")), "")
    subject = f"[성장 리포트] {C.PERIOD[0][:7]}~{C.PERIOD[1][:7]}"
    html = (
        f'<div style="font-family:sans-serif;color:#0f172a;max-width:640px">'
        f'<h2 style="font-size:18px">{subject}</h2>'
        f'<p style="font-size:14px;line-height:1.7;white-space:pre-line">'
        f'{summary}</p>'
        f'<p style="font-size:12px;color:#64748b;margin-top:20px">'
        f'자동 생성 · {datetime.now(C.KST).strftime("%Y-%m-%d %H:%M")}</p></div>')
    return {"to": C.EMAIL_TO_EXAMPLE, "subject": subject, "html": html}
