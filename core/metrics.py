# -*- coding: utf-8 -*-
"""지표 계산.

**지표의 정의는 위키가 원본이다.** 이 파일은 위키에 적힌 정의를 코드로 옮긴 것일 뿐,
여기서 정의를 새로 만들지 않는다. 정의가 바뀌면 위키를 먼저 고친다.

────────────────────────────────────────────────────────────────────
★ 이 파일에는 통신사 컬럼명이 박혀 있다.

  billing_amount · is_churned · acquisition_channel · visitor_id ...

config.py 를 다 바꿔도 여기서 깨진다. **깨지는 것이 정상이다.**
컬럼명을 하나씩 내 것으로 맞추는 것이 이식 작업의 절반이다. → DESIGN.md §4-6
────────────────────────────────────────────────────────────────────

계산은 전부 pandas로 한다. 어디서 읽어왔든 입력은 동일한 DataFrame이다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st
from scipy import stats

from core import config as C
from core.load import to_dt
from core.todo import todo


# ── 퍼널 ──────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def funnel(fe: pd.DataFrame) -> pd.DataFrame:
    """단계별 도달 건수와 전환율.

    **그레인은 계획안 1건이다.** plan_id 고유값으로 센다.

        한 대상이 같은 단계를 두 번 밟을 수 있는가?
          있다 → 그냥 세면 안 된다. 고유값으로 센다 (nunique)   ← 이쪽이다
          없다 → 행을 그대로 세도 된다 (len)

    같은 (계획안, 단계) 조합이 두 번 이상 나타나는 경우가 436건 있다.
    행을 그대로 세면 재도전한 계획안이 여러 번 세어져 도달 수가 부풀려진다.

    세기 전에 두 가지를 걸러낸다.

        1. 완전중복 — 전 컬럼이 같은 행이 64건 섞여 있다(의도적으로 심긴 것)
        2. result   — "통과"만 센다. 반려 523 · 철회 74 는 도달이 아니다

    반환: DataFrame[step, label, n, step_rate, cum_rate, drop, is_bottleneck]

        step           config.FUNNEL_STEPS 의 값
        label          config.FUNNEL_LABELS 의 값 (화면 표시용)
        n              그 단계에 도달한 수
        step_rate      전 단계 대비 비율 (첫 단계는 NA — 전 단계가 없다)
        cum_rate       첫 단계 대비 비율
        drop           전 단계에서 빠진 수 (첫 단계는 NA — 전 단계가 없다)
        is_bottleneck  step_rate 가 가장 낮은 구간이면 True

    첫 단계의 step_rate 와 drop 은 둘 다 **결측**이다. 0 이 아니다 —
    0 으로 두면 "빠진 것이 없다"로 읽히는데 실제로는 "해당 없음"이다.

    config.FUNNEL_STEPS 의 값이 데이터에 없으면 **예외를 올린다.** 0 으로
    두면 "아무도 통과 못 했다"와 "단계 이름이 틀렸다"가 구분되지 않는다.
    (검증에서도 같은 것을 차단으로 막는다 — validate.run_checks() 규칙 4.
     대시보드·리포트는 검증을 거치지 않고 이 함수를 바로 부르므로 양쪽에 둔다)

    대조 기준은 mydomain/notes/02_퍼널실측.md 에 있다.
    590 -> 558 -> 538 -> 469 -> 442 · 누적 74.9% · 병목은 이사회 승인 87.2%
    """
    # 1. 완전중복 제거. nunique 로 세면 결과가 같아 보이지만, 안 지우면
    #    시도 수를 세는 계산에서 조용히 틀린다. 여기서 한 번 정리해 둔다.
    ev = fe.drop_duplicates()

    # 2. 도달 = 그 단계를 통과한 것. 반려·철회는 도달이 아니다.
    ok = ev[ev.result == "통과"]

    # 3. 단계 이름이 데이터와 맞는지 먼저 본다. 안 맞으면 그 단계가 0 이 되어
    #    틀린 결과가 정상처럼 보인다. 조용히 넘기지 않는다.
    have = set(ev.stage_name.astype(str).unique())
    missing = [s for s in C.FUNNEL_STEPS if s not in have]
    if missing:
        raise ValueError(
            f"config.FUNNEL_STEPS 중 데이터에 없는 단계가 있습니다: {missing}. "
            f"데이터의 단계 이름은 {sorted(have)} 입니다. "
            f"config.FUNNEL_STEPS 를 데이터 값과 글자까지 맞추십시오.")

    # 4. 단계 순서는 config 가 정한다.
    f = pd.DataFrame([
        {"step": s,
         "label": C.FUNNEL_LABELS.get(s, s),
         "n": int(ok.loc[ok.stage_name == s, "plan_id"].nunique())}
        for s in C.FUNNEL_STEPS
    ])

    first = f.n.iloc[0]
    prev = f.n.shift(1)
    f["step_rate"] = f.n / prev                      # 첫 단계는 NaN
    f["cum_rate"] = f.n / first if first else float("nan")
    # nullable 정수(Int64). 첫 행은 <NA> 로 두어 step_rate 와 처리를 맞춘다.
    # 0 으로 채우면 "빠진 게 없다"로 오독된다. float 로 두면 69.0 처럼 찍힌다.
    f["drop"] = (prev - f.n).astype("Int64")
    # NaN 은 min 에서 빠지므로 첫 단계가 병목으로 잡히는 일은 없다.
    f["is_bottleneck"] = f.step_rate == f.step_rate.min()
    return f[["step", "label", "n", "step_rate", "cum_rate",
              "drop", "is_bottleneck"]]


@st.cache_data(show_spinner=False)
def funnel_by(t: dict, dim: str, step_from: str, step_to: str) -> pd.DataFrame:
    """차원별 특정 구간 전환율. 평균 하나로는 어디를 고칠지 모른다.

    dim 은 분해 축이다. **무엇으로 쪼갤지는 내가 정한다.**

    쪼개는 기준은 이것이다: 그 축으로 나눴을 때 **손을 쓸 수 있는가.**
    나눠서 격차가 보여도 우리가 못 바꾸는 것이면 분해할 이유가 적다.

    반환: DataFrame[<dim>, 도달, 전환, 전환율, 비중]

    ── 내 도메인에서 정한 것 ──────────────────────────────────────

    그레인은 계획안 1건(plan_id). 도달·전환 모두 고유 계획안 수다.

    **인자를 (fe, se, ...) 에서 t(dict) 로 바꿨다.** 축이 서로 다른 테이블에
    있어 함수가 직접 찾아야 한다 — cycle_year 는 plans 에, division_type 은
    departments 에 있어 plans.department_id 로 조인해야 붙는다.
    호출부(2_대시보드 · 3_리포트)도 같이 바꿨다.

    축은 셋이다. 명세에서 둘을 정하고, 세 번째(부서)는 2026-09-03 에 보류를 풀었다.

        department_name  부서 15개 — 어느 부서에서 막히는가 (기본 축)
        division_type    사업부 9 / 지원부서 6 — 조직 성격
        cycle_year       2022~2026 — 제출 사이클. 예산삭감연도(2023·2025) 비교용

    **셋 중 판정에 쓰는 것은 department_name 이다 — 격차가 커서가 아니라 부서 단위로
    개입할 수 있어서다.** division_type 은 조직 성격이라 바꿔서 좋아지게 할 수 없다
    (같은 구간 격차도 0.2%p 로 실제 안 갈린다). cycle_year 는 그 해 자체를 바꿀 수는
    없지만 예산삭감 여부는 정책 레버라 후보로 남겼다 — department_name 만큼 직접적인
    개입 대상은 아니다.

    부서 축은 표본이 가장 얇다. 병목 구간에서 부서당 도달이 27~45건이라
    MIN_CELL_SAMPLE(30) 에 못 미치는 칸이 생기고, 여기서 다시 연도로 쪼개면
    한 자리로 떨어진다 — 75개 조합 중 73개가 미달이다.

    cycle_year 로 쪼개면 **시작 시점별 코호트**가 된다. 그때 주의할 것:
    최근 코호트는 아직 다 갈 시간이 없을 수 있다. 낮은 값이 성과 문제인지
    중도절단인지는 **미결 건수와 단계별 소요 일수**를 봐야 갈린다.
    (제출 -> 확정 배포 중앙값 126일 · 90분위 165일)

    표본이 config.MIN_CELL_SAMPLE 미만인 칸은 **빼고 돌려준다.** 비율로 말할 수
    없는 크기이기 때문이다. (주지표 기준인 MIN_SAMPLE 과 다른 상수다)
    다만 비중은 **빼기 전 전체**를 분모로 계산하므로, 비중 합이 1 이 안 되면
    빠진 칸이 있다는 뜻이다.
    """
    pl = t["plans"]
    ev = t["plan_stage_events"].drop_duplicates()
    ok = ev[ev.result == "통과"]

    # 축 값을 계획안에 붙인다. plans 에 있으면 그대로, 없으면 마스터에서 조인.
    base = pl[["plan_id", "department_id"]].copy()
    base["plan_id"] = base.plan_id.astype(str)
    if dim in pl.columns:
        base[dim] = pl[dim].astype(str).to_numpy()
    else:
        src = next((n for n, d in t.items() if dim in d.columns and n != "plans"), None)
        if src is None:
            raise ValueError(
                f"분해 축 {dim!r} 을 어느 테이블에서도 찾을 수 없습니다. "
                f"쓸 수 있는 컬럼: "
                f"{sorted({c for d in t.values() for c in d.columns})}")
        m = t[src][["department_id", dim]].copy()
        m[dim] = m[dim].astype(str)
        base = base.merge(m, on="department_id", how="left")
        base[dim] = base[dim].fillna("(미상)")

    a = set(ok.loc[ok.stage_name == step_from, "plan_id"].astype(str))
    b = set(ok.loc[ok.stage_name == step_to, "plan_id"].astype(str))
    base["_a"] = base.plan_id.isin(a)
    base["_b"] = base.plan_id.isin(b)

    g = (base.groupby(dim, observed=True)
             .agg(도달=("_a", "sum"), 전환=("_b", "sum"))
             .reset_index())
    total = int(g.도달.sum())                      # 빼기 전 전체가 분모다
    g = g[g.도달 >= C.MIN_CELL_SAMPLE].copy()      # 칸 기준. MIN_SAMPLE 과 다르다
    g["전환율"] = g.전환 / g.도달
    g["비중"] = g.도달 / total if total else float("nan")
    return g[[dim, "도달", "전환", "전환율", "비중"]].sort_values(dim)


@st.cache_data(show_spinner=False)
def reviewer_pass_rate(t: dict, stage: str) -> pd.DataFrame:
    """그 단계 담당자별 통과율. 단계별 개별 통과 조건이 담당자마다 실제로
    다르게 적용되는지를 본다 — 격차가 크면 담당자 배분·교육으로 개입할 수 있다.

    ★ 2026-09-05 에 추가한 reviewer_id · review_score 를 쓴다(합성 추가 데이터,
    원래 명세엔 없었다). 통과 조건은 config.PASS_THRESHOLD 그대로 다시 적용한다
    (review_score >= PASS_THRESHOLD) — result 를 그대로 세지 않는 이유는, 이
    조건식 자체가 "단계별 개별 통과 조건"이 데이터에 있다는 것을 보여주는
    자리이기 때문이다.

    부서초안제출(자체 제출)·철회(심사 전 자진 철회) 행은 담당자가 없어 이
    분해를 만들 수 없다 — stage 는 config.FUNNEL_STEPS[1:] 중 하나여야 한다.

    반환: DataFrame[reviewer_id, n, pass_rate]
    표본이 config.MIN_CELL_SAMPLE 미만인 담당자는 빼고 돌려준다(funnel_by() 와 같은 기준).
    """
    if stage not in C.FUNNEL_STEPS[1:]:
        raise ValueError(
            f"stage={stage!r} 는 담당자 판정이 없는 단계입니다. "
            f"{C.FUNNEL_STEPS[1:]} 중 하나를 쓰십시오 — "
            f"부서초안제출은 자체 제출, 철회는 심사 전이라 담당자가 없습니다.")

    ev = t["plan_stage_events"].drop_duplicates()
    sub = ev[(ev.stage_name == stage) & ev.reviewer_id.notna()].copy()
    sub["_pass"] = sub.review_score >= C.PASS_THRESHOLD

    g = (sub.groupby("reviewer_id")
            .agg(n=("event_id", "size"), pass_rate=("_pass", "mean"))
            .reset_index())
    g["pass_rate"] *= 100
    return g[g.n >= C.MIN_CELL_SAMPLE].sort_values("pass_rate")


@st.cache_data(show_spinner=False)
def briefing_pass_rate(t: dict, stage: str = "이사회승인") -> pd.DataFrame:
    """그 단계 사전 설명회 실시 여부별 통과율. reviewer_pass_rate() 와 달리
    담당자 개인 격차가 아니라 **개입 가능한 프로세스 레버**를 본다 — 사전
    설명회를 의무화하면 통과율이 바뀔 수 있다는 가설을 검증하는 자리다.

    ★ 2026-09-05 에 추가한 pre_briefing 을 쓴다(합성 추가 데이터, 원래 명세엔
    없었다). 지금은 병목 구간(경영진검토→이사회승인)에만 값이 있다 — 원인을
    찾아야 할 구간이 거기뿐이라 거기만 채웠다(다른 구간은 이미 통과율이
    94~96% 라 조사할 문제가 없다). stage 를 인자로 받아 두는 이유는, 나중에
    병목이 다른 단계로 옮겨가 그 단계에도 pre_briefing 이 채워지면 이 함수를
    고치지 않고 그대로 재사용하기 위해서다 — 아직 값이 없는 단계를 넣으면
    표본이 비어 빈 결과가 돌아온다.

    reviewer_pass_rate() 는 review_score >= PASS_THRESHOLD 로 판정하지만
    (그게 "단계별 개별 통과 조건"이 있다는 것을 보여주는 자리라서), pre_briefing
    은 판정 조건이 아니라 원인 후보라 실제 result 를 그대로 쓴다.

    반환: DataFrame[pre_briefing, n, pass_rate]
    표본이 config.MIN_CELL_SAMPLE 미만이면 빼고 돌려준다(다른 분해와 같은 기준).
    """
    if stage not in C.FUNNEL_STEPS[1:]:
        raise ValueError(
            f"stage={stage!r} 는 사전 설명회 판정이 없는 단계입니다. "
            f"{C.FUNNEL_STEPS[1:]} 중 하나를 쓰십시오.")

    ev = t["plan_stage_events"].drop_duplicates()
    sub = ev[(ev.stage_name == stage) & ev.pre_briefing.notna()].copy()
    sub["_pass"] = sub.result == "통과"

    g = (sub.groupby("pre_briefing")
            .agg(n=("event_id", "size"), pass_rate=("_pass", "mean"))
            .reset_index())
    g["pass_rate"] *= 100
    return g[g.n >= C.MIN_CELL_SAMPLE].sort_values("pass_rate")


@st.cache_data(show_spinner=False)
def prep_days_by_outcome(t: dict, stage: str = "이사회승인") -> pd.DataFrame:
    """그 단계 최종 통과/반려 여부에 따른 준비기간(착수~제출 소요일) 평균.

    briefing_pass_rate() 는 그 단계 이벤트(재도전 포함 시도 하나하나)를 세지만,
    이건 **계획안 단위**다 — prep_days 가 plans 컬럼이라 계획안 하나에 값 하나뿐이고,
    재도전 여부와 무관하게 그 단계를 "최종" 통과했는지 반려로 끝났는지로 가른다.

    ★ 2026-09-05 에 추가한 prep_days 를 쓴다(합성 추가 데이터). is_new_business
    와 달리 이건 실제로 심어둔 신호다 — 준비기간이 짧을수록 반려로 끝나는
    비중이 높다. stage 를 인자로 받는 이유·아직 이 병목 구간에만 값이 있는
    이유는 briefing_pass_rate() 와 같다.

    그 단계에 도달조차 못 한 계획안(더 앞에서 반려·철회되었거나 확정배포대기로
    아직 도달 전인 것)은 뺀다 — 이 단계의 통과/반려를 비교하는 자리라
    "해당 없음"을 넣으면 비교 대상이 아닌 것이 섞인다.

    반환: DataFrame[outcome, n, prep_days]  (outcome: 통과/반려)
    표본이 config.MIN_CELL_SAMPLE 미만이면 빼고 돌려준다(다른 분해와 같은 기준).
    """
    if stage not in C.FUNNEL_STEPS[1:]:
        raise ValueError(
            f"stage={stage!r} 는 준비기간 판정이 없는 단계입니다. "
            f"{C.FUNNEL_STEPS[1:]} 중 하나를 쓰십시오.")

    ev = t["plan_stage_events"].drop_duplicates()
    stage_ev = ev[ev.stage_name == stage]
    passed = set(stage_ev.loc[stage_ev.result == "통과", "plan_id"].astype(str))
    reached = set(stage_ev["plan_id"].astype(str))

    pl = t["plans"]
    sub = pl[pl.plan_id.astype(str).isin(reached)].copy()
    sub["outcome"] = np.where(sub.plan_id.astype(str).isin(passed), "통과", "반려")

    g = (sub.groupby("outcome")
            .agg(n=("plan_id", "size"), prep_days=("prep_days", "mean"))
            .reset_index())
    return g[g.n >= C.MIN_CELL_SAMPLE].sort_values("outcome")


# ── 유지 퍼널 ─────────────────────────────────────────────────────
# 단계 이름 -> 그 단계에 해당하는 plan_id 를 돌려주는 판정식.
# **순서와 이름은 config.RETENTION_STEPS 가 정한다.** 여기는 판정식만 갖는다.
# 단계의 뜻을 바꿀 때는 두 곳을 같이 고쳐야 한다 — 이름만 바꾸면 예외가 난다.
_RETENTION_RULES = {
    "제출": lambda pl: pl.plan_id,
    "유지": lambda pl: pl.loc[pl.final_status.isin(["확정배포", "확정배포대기"]),
                              "plan_id"],
    "확정배포": lambda pl: pl.loc[pl.final_status == "확정배포", "plan_id"],
}


@st.cache_data(show_spinner=False)
def retention_funnel(t: dict) -> pd.DataFrame:
    """유지 퍼널. config.RETENTION_STEPS 의 단계대로 센다.

    ★ Day2 실습 D에서 채웁니다.

    획득 퍼널과 다른 점 셋:

        단계    주어지지 않는다. **내가 정의한다**
        방향    한 방향이 아니다. 오갈 수 있다
        시간    며칠이 아니라 몇 달~몇 년

    그래서 그레인이 다르다. 획득은 **대상 하나**지만 유지는 흔히 **대상 × 기간**이다.
    같은 오류의 두 얼굴이다 — 그레인을 잘못 잡으면 둘 다 틀린다.

    **퍼널이 아니면 퍼널이라고 부르지 않는다.** 세 가지를 물어라.

        이 단계는 앞 단계를 반드시 거치는가?  아니면 그냥 분류다
        그레인이 무엇인가?
        기간을 어떻게 자르는가?

    그리고 **관측 기간이 다른 대상을 누적값으로 비교하지 않는다.**
    비교하려면 비율(단위 기간당)로 바꾸거나, 같은 시점에 시작한 것끼리 묶는다.
    7주차 토요일에 겪은 생존 편향이 여기서 다시 나온다.

    반환: DataFrame[step, label, n, step_rate, cum_rate]

    ── 내 도메인에서 정한 것 ──────────────────────────────────────

    그레인   **계획안 1건** (plan_id). 획득 퍼널과 같다.
             유지 퍼널이 흔히 「대상 × 기간」인 것과 달리, 이 도메인은
             계획안 하나가 한 사이클에 한 번 결말을 맞아 기간 축이 없다.

    원천     plans. 세 단계 모두 final_status 하나로 갈린다.

    기간     **전체 한 덩어리** (2022~2026 누적).
             연도별로 확정률이 68.5%~81.2% 로 12.7%p 벌어지고,
             예산삭감연도(2023·2025) 평균 69.0% vs 그 외 79.2% 로 10.2%p
             차이가 있다. **전체 74.9% 는 그 사이 어디에도 실재하지 않는다.**
             반환 형식(3행)이 연도 축을 담지 못해 지금은 누적으로 둔다 —
             **Day3 분해에서 cycle_year 로 다시 쪼갠다.**

    이탈     철회 + 반려종결 145건은 **단계로 넣지 않았다.** 유지의 여집합이라
             앞 단계를 거친 부분집합이 아니다. 590 - 445 로 읽는다.

    단계 정의는 config.RETENTION_STEPS 가 순서와 이름을, 아래 _RETENTION_RULES
    가 판정식을 갖는다. **둘의 이름이 어긋나면 예외를 올린다** — 조용히 빠지면
    단계 하나가 사라진 채로 퍼널이 그려진다.
    """
    pl = t["plans"]

    unknown = [n for n, _ in C.RETENTION_STEPS if n not in _RETENTION_RULES]
    if unknown:
        raise ValueError(
            f"config.RETENTION_STEPS 의 단계 중 판정식이 없는 것: {unknown}. "
            f"metrics._RETENTION_RULES 에 추가하십시오. "
            f"현재 판정식이 있는 단계: {sorted(_RETENTION_RULES)}")

    rows = []
    for name, _desc in C.RETENTION_STEPS:
        ids = _RETENTION_RULES[name](pl)
        rows.append({"step": name, "label": name, "n": int(ids.nunique())})
    r = pd.DataFrame(rows)

    first = r.n.iloc[0]
    prev = r.n.shift(1)
    r["step_rate"] = r.n / prev                      # 첫 단계는 NA
    r["cum_rate"] = r.n / first if first else float("nan")
    return r[["step", "label", "n", "step_rate", "cum_rate"]]


# ── KPI ───────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def kpis(t: dict) -> dict:
    """지표 카드.

    ★ Day2 실습 E에서 채웁니다.

    ★ 아래 컬럼명은 전부 **통신사 것**이다. 내 데이터의 대응 컬럼으로 바꾼다.

        billing_amount  →  금액에 해당하는 컬럼
        is_churned      →  이탈 여부에 해당하는 컬럼

    없는 지표는 **빼면 된다.** 4개일 이유가 없다.

    반환: {"지표이름": {"value": float, "unit": str, "fmt": str}}
          fmt 은 화면 표시 형식이다. 예) "{:.2f}%"  "{:,.0f}원"

    ── 내 도메인에서 정한 것 ──────────────────────────────────────

    **3개다.** 카드 칸은 4개지만 넷째는 비운다. 화면이 zip 으로 물리므로
    5개를 만들면 마지막이 조용히 잘리고, 근거 없는 지표로 칸을 채우면
    임계값이 없어 **초록 "정상"으로 오독된다.**

        전체 통과율      주지표(명세 3행). final_status == "확정배포" 비율
        계획-실적 괴리율  가드레일(명세 3행). variance_pct 의 **평균**
        유지율           명세 5행. 확정배포 + 확정배포대기 비율

    지표 이름은 config.THRESHOLDS 의 키와 **글자까지 같아야** 색이 갈리고,
    monthly() 의 열 이름과도 같아야 스파크라인이 그려진다.

    **재도전율은 넣지 않았다.** 임계값 근거가 없고, THRESHOLDS 에 없는 지표는
    status_of() 가 "ok"(초록 정상)를 돌려준다 — 판정하지 않은 것을 통과했다고
    주장하는 화면이 된다. 재도전율의 격차(코호트별 46.5~72.7%)는 Day3 분해에서 본다.

    ── 괴리율을 평균으로 잡은 이유 ────────────────────────────────

        1. 위험선 16.76 이 「예산삭감연도 **평균**」에서 나왔다. 중앙값을 쓰면
           통계량이 다른 것을 기준선과 비교하게 된다
        2. 분포가 오른쪽으로 치우쳐 있다 (min 0.02 · 중앙 10.28 · 평균 13.30 ·
           max 64.32). 가드레일이 잡아야 하는 것이 그 꼬리다
        3. 코호트 12개 판정이 평균 ok 4/warn 6/block 2, 중앙값 ok 6/warn 4/block 2.
           놓치는 쪽이 위험한 지표라 민감한 편이 맞다

    **주의 — 전 기간 한 값으로는 판정에 정보가 없다.** 경고선 10.28 이 이 데이터의
    중앙값이라, 치우친 분포의 평균(13.30)은 구조적으로 그것을 넘는다. 카드는
    처음부터 경고로 뜬다. 이 임계값이 일하는 곳은 코호트·부서처럼 쪼갠 단위다.
    """
    pl, ac = t["plans"], t["plan_actuals"]
    keep = ["확정배포", "확정배포대기"]
    return {
        "전체 통과율": {
            "value": float(pl.final_status.eq("확정배포").mean() * 100),
            "unit": "%", "fmt": "{:.2f}%"},
        "계획-실적 괴리율": {
            "value": float(ac.variance_pct.mean()),
            "unit": "%p", "fmt": "{:.2f}%p"},
        "유지율": {
            "value": float(pl.final_status.isin(keep).mean() * 100),
            "unit": "%", "fmt": "{:.2f}%"},
    }


@st.cache_data(show_spinner=False)
def monthly(t: dict) -> pd.DataFrame:
    """기간별 추이. 지표 카드의 스파크라인과 아카이브 비교에 쓴다.

    ★ Day2 실습 E에서 채웁니다. (kpis 와 함께)

    kpis() 가 돌려주는 지표 이름과 **열 이름이 대응**되어야 스파크라인이 그려진다.
    기간이 짧아 월별로 나눌 수 없으면 주별로 해도 되고, 아예 빼도 된다.

    반환: 인덱스가 기간(예 "2025-01"), 열이 지표인 DataFrame

    ── 내 도메인에서 정한 것 ──────────────────────────────────────

    기간은 **제출월 코호트**(submitted_date)로 자른다. 이벤트 발생월이 아니다 —
    같은 계획안의 여러 단계 이벤트가 다른 달에 흩어져 코호트 해석이 안 된다.

    코호트는 **15개**다. 연도별 1~3월뿐이고 4~12월은 제출이 0건이다.
    **값이 0% 인 것이 아니라 표본이 없다** — 그래서 행 자체가 없다.
    코호트별 제출은 17~55건으로 최소 표본 12건을 전부 넘는다.

    ★ 괴리율은 2026 코호트 3개에서 **결측**이다. plan_actuals 에 2026년 건이
      0/117 이다 — 실적 대조 기간이 아직 안 지났다. **0 으로 채우지 않는다.**
      0 은 "괴리가 없었다"로 읽히는데 실제로는 "아직 알 수 없다"다.
      코호트별 괴리 표본은 12~42건이라 2024-03(12건)이 최소 표본에 딱 걸친다.
    """
    pl, ac = t["plans"], t["plan_actuals"]
    keep = ["확정배포", "확정배포대기"]

    # category dtype 끼리 조인하면 카테고리가 어긋날 수 있어 문자열로 맞춘다.
    d = pl.assign(
        기간=to_dt(pl.submitted_date).dt.strftime("%Y-%m"),
        _pid=pl.plan_id.astype(str),
        _status=pl.final_status.astype(str))
    v = ac.assign(_pid=ac.plan_id.astype(str))[["_pid", "variance_pct"]]
    d = d.merge(v, on="_pid", how="left")          # 실적 없는 건은 NaN 으로 남는다

    g = d.groupby("기간", sort=True)
    out = pd.DataFrame({
        "전체 통과율": g._status.apply(lambda x: (x == "확정배포").mean() * 100),
        "계획-실적 괴리율": g.variance_pct.mean(),   # NaN 만 있으면 NaN
        "유지율": g._status.apply(lambda x: x.isin(keep).mean() * 100),
    })
    return out


def status_of(name: str, value: float) -> str:
    """지표 값을 상태 색으로 판정한다. 임계값은 config.THRESHOLDS 에 있다.

    이 함수는 **그대로 쓴다.** 판정 규칙이지 도메인이 아니다.

    임계값이 없는 지표는 **"none"(회색 · 판정 없음)** 이다. "ok"(초록 정상)로
    두면 판정한 적 없는 것을 통과했다고 주장하는 화면이 된다 — 읽는 사람은
    초록을 보고 "괜찮은 수준"으로 받아들인다. 근거 없는 임계값을 지어내지
    않는 대신, 판정하지 않았다는 사실을 색으로 드러낸다.
    """
    th = C.THRESHOLDS.get(name)
    if not th:
        return "none"
    # 높을수록 나쁜 지표는 config.HIGHER_IS_WORSE 에 있다. 판정 규칙은
    # 도메인이 아니지만 **어느 지표가 그런지는 도메인**이라 값은 config 가 갖는다.
    if name in C.HIGHER_IS_WORSE:
        return ("block" if value > th["위험"]
                else "warn" if value > th["경고"] else "ok")
    return ("block" if value < th["위험"]
            else "warn" if value < th["경고"] else "ok")


# ── 전후 비교 (실험이 없는 도메인의 대체) ─────────────────────────
def _year_counts(t: dict) -> pd.DataFrame:
    """연도별 제출 수 · 전체 통과율.

    **가드레일 평균은 여기서 구하지 않는다.** 주지표는 판정 자체의 재료라
    항상 계산해야 하지만, 가드레일은 못 믿을 조건(표본 부족)에 걸릴 수
    있으므로 그 값을 여기서 미리 구해 두면 **판정이 계산 뒤로 밀린다.**
    가드레일 평균은 trust_check() 를 통과한 뒤 _guardrail_mean() 이 낸다.
    """
    pl = t["plans"]
    p = pl[["cycle_year", "final_status"]].copy()
    p["final_status"] = p.final_status.astype(str)
    g = p.groupby("cycle_year", observed=True)
    out = pd.DataFrame({
        "제출": g.size(),
        "전체 통과율": g.final_status.apply(lambda x: (x == "확정배포").mean() * 100),
    })
    out.index = out.index.astype(int)
    return out.sort_index()


def _guardrail_sample(t: dict, year: int) -> int:
    """그 연도 확정배포 건 중 실적 대조가 있는 건수만 센다.

    **평균은 계산하지 않는다.** trust_check() 가 이 건수만 보고 판정하고,
    통과했을 때만 _guardrail_mean() 이 실제 값을 구한다.
    """
    pl, ac = t["plans"], t["plan_actuals"]
    conf = pl[(pl.cycle_year == year) & (pl.final_status.astype(str) == "확정배포")]
    ids = set(ac.plan_id.astype(str))
    return int(conf.plan_id.astype(str).isin(ids).sum())


def _guardrail_mean(t: dict, year: int) -> float:
    """그 연도 계획-실적 괴리율 평균.

    **trust_check() 를 통과한 뒤에만 부른다.** 못 믿을 조건에 걸린 연도에는
    이 함수가 아예 호출되지 않는다 — 값을 구해 놓고 숨기는 것이 아니라
    구하는 계산 자체를 하지 않는다.
    """
    pl, ac = t["plans"], t["plan_actuals"]
    conf = pl[(pl.cycle_year == year) & (pl.final_status.astype(str) == "확정배포")]
    conf = conf[["plan_id"]].astype(str)
    a = ac[["plan_id", "variance_pct"]].copy()
    a["plan_id"] = a.plan_id.astype(str)
    return float(conf.merge(a, on="plan_id", how="left").variance_pct.mean())


def cohort_compare(t: dict, base_year: int, comp_year: int) -> dict:
    """두 연도 코호트를 전후로 비교하고 판정한다.

    **이 도메인에 A/B 실험이 없다.** 무작위 배정이 없으므로 이 카드는
    실험 결과가 아니라 **전후 비교**다. 시행 전후로 경기·조직개편·예산 정책
    같은 다른 요인도 같이 바뀌므로 **인과를 주장할 수 없다.**
    유의성·p값·신뢰구간은 계산하지 않는다 — 무작위 배정이 없으면 그 수치가
    답하는 질문 자체가 성립하지 않는다.

    **판정 순서를 코드로 박는다.** 좋은 결과를 먼저 보면 가드레일을 무시하고
    싶어지기 때문이다. 1번을 통과했다고 바로 성공으로 가지 않는다.

        1. 주지표가 config.MOVE_THRESHOLD 이상 움직였는가 (**절댓값**)
           아니면 -> "효과 없음"                       (COLORS["none"])
        2. 가드레일이 config.GUARDRAIL_MOVE 이상 나빠졌는가
           그러면 -> "주의 필요"                       (COLORS["warn"])
           계산할 수 없으면 -> "가드레일 없음"          (COLORS["warn"])
        3. 둘 다 통과 -> "성공"                        (COLORS["ok"])

    가드레일을 계산할 수 없는 코호트는 **성공으로 보내지 않는다.** 주지표가
    올랐는데 무엇을 희생했는지 확인되지 않은 상태이고, 그것을 성공이라 부르면
    가드레일을 둔 이유가 사라진다.

    나빠지는 방향은 config.HIGHER_IS_WORSE 가 정한다 — 괴리율은 높을수록
    나쁘므로 증가가 악화다.

    **1번은 방향을 보지 않는다.** "움직였는가"만 묻는다. 그래서 주지표가 크게
    나빠지고 가드레일이 괜찮으면 규칙상 "성공"이 된다 — 지금 데이터에서는
    주지표 하락이 늘 가드레일 악화와 같이 와서 그 경우가 나오지 않지만,
    규칙의 빈틈이다.

    **판정이 계산보다 먼저다.** 못 믿을 조건에 걸리면 그 값을 구하는 계산
    자체를 하지 않는다 — 계산해 놓고 화면에 안 그리는 것이 아니다.

    반환: dict(base, comp, primary, guardrail, verdict, color, reason, note)
    """
    y = _year_counts(t)
    for v in (base_year, comp_year):
        if v not in y.index:
            raise ValueError(f"cycle_year {v} 가 데이터에 없습니다. "
                             f"있는 연도: {list(y.index)}")
    a, b = y.loc[base_year], y.loc[comp_year]
    n_cmp = int(min(a.제출, b.제출))

    row = {
        "base": int(base_year), "comp": int(comp_year),
        "primary": None, "guardrail": None, "untrust": None,
        "note": "무작위 배정이 아닌 전후 비교입니다 — 인과를 주장할 수 없습니다.",
    }

    # 제도가 다른 구간끼리의 비교는 단서로 붙인다(판정은 아래 순서대로 한다).
    # 제출 건수(카운트)만 보고 판정하므로 주지표·가드레일 값은 아직 안 구했다.
    diff = trust_check(n_cmp, compare=({base_year}, {comp_year}))
    if diff:
        row["note"] = f"{diff}. " + row["note"]

    # ── 1. 주지표가 움직였는가 ────────────────────────────────────
    #   이건 못 믿을 조건이 아니라 판정 자체의 재료라, 항상 구해야 한다.
    P = "전체 통과율"
    d_primary = float(b[P] - a[P])
    row["primary"] = {"name": P, "base": float(a[P]), "comp": float(b[P]),
                      "delta": d_primary, "n_base": int(a.제출), "n_comp": int(b.제출)}

    if abs(d_primary) < C.MOVE_THRESHOLD:
        row.update(verdict="효과 없음", color="none",
                   reason=f"주지표 {d_primary:+.2f}%p 움직임 — 기준 "
                          f"{C.MOVE_THRESHOLD}%p 미만")
        return row

    # ── 2. 가드레일을 볼 수 있는가, 나빠지지 않았는가 ─────────────
    #   1번을 통과했다고 여기서 바로 성공으로 가지 않는다.
    #   표본(건수)만으로 먼저 판정한다 — 평균은 아직 구하지 않았다.
    n_guard = _guardrail_sample(t, comp_year)
    blocked = trust_check(n_guard, {comp_year}, guardrail=True, t=t)
    if blocked:
        # "왜 감췄나" 화면이 쓰는 원재료. blocked 문자열을 파싱하지 않고
        # trust_check() 가 실제로 본 값을 그대로 담는다.
        #   대조 미도래가 근본 원인이면 그것을 조건으로 보인다 — 표본 0건은
        #   결과이지 원인이 아니다. 그 해가 ACTUALS_LAST_YEAR 를 안 넘었는데도
        #   표본이 모자라면 그때는 표본 부족이 진짜 원인이다.
        cut_base = int(base_year) in C.BUDGET_CUT_YEARS
        cut_comp = int(comp_year) in C.BUDGET_CUT_YEARS
        condition = ("대조 미도래" if int(comp_year) > C.ACTUALS_LAST_YEAR
                     else "표본 부족")
        row["untrust"] = {
            "condition": condition,
            "n_guard": n_guard, "min_cell": C.MIN_CELL_SAMPLE,
            "cycle_year": int(comp_year),
            "actuals_last_year": C.ACTUALS_LAST_YEAR,
            "base_year": int(base_year), "comp_year": int(comp_year),
            "cut_base": cut_base, "cut_comp": cut_comp,
        }
        row.update(verdict="가드레일 없음", color="warn",
                   reason=f"무엇을 희생했는지 확인되지 않음 — {blocked}")
        return row              # 계획-실적 괴리율 평균은 계산되지 않았다

    # 판정을 통과했을 때만 실제 값을 구한다.
    G = "계획-실적 괴리율"
    g_base = _guardrail_mean(t, base_year)
    g_comp = _guardrail_mean(t, comp_year)
    n_base = _guardrail_sample(t, base_year)
    d_guard = g_comp - g_base
    worse = d_guard if G in C.HIGHER_IS_WORSE else -d_guard
    row["guardrail"] = {"name": G, "base": g_base, "comp": g_comp,
                        "delta": d_guard, "worse": worse,
                        "n_base": n_base, "n_comp": n_guard}
    if worse >= C.GUARDRAIL_MOVE:
        row.update(verdict="주의 필요", color="warn",
                   reason=f"주지표 {d_primary:+.2f}%p 움직였고, 가드레일이 "
                          f"{worse:+.2f}%p 나빠졌습니다 (기준 {C.GUARDRAIL_MOVE}%p)")
        return row

    # ── 3. 둘 다 통과 ────────────────────────────────────────────
    row.update(verdict="성공", color="ok",
               reason=f"주지표 {d_primary:+.2f}%p 움직였고, 가드레일은 "
                      f"{worse:+.2f}%p로 기준 {C.GUARDRAIL_MOVE}%p 미만입니다")
    return row


def cohort_cards(t: dict) -> list[dict]:
    """연도 코호트를 앞뒤로 이어 비교한 카드 목록. 대시보드가 쓴다."""
    ys = list(_year_counts(t).index)
    return [cohort_compare(t, a, b) for a, b in zip(ys, ys[1:])]


# ── 실험 ──────────────────────────────────────────────────────────
# ★ 실험별로 어느 구간을 보는지. 도메인이 바뀌면 이 표를 갈아끼운다.
#   실험이 없는 도메인이면 비워 둔다.
EXP_STEPS: dict[str, tuple[str, str]] = {
    "EXP-001": ("랜딩방문", "요금제조회"),
    "EXP-002": ("요금제조회", "신청시작"),
    "EXP-003": ("신청시작", "신청완료"),
    "EXP-004": ("요금제조회", "신청시작"),
    "EXP-005": ("요금제조회", "신청시작"),
}


def _two_prop(sc, nc, stt, nt):
    """두 비율 비교. 차이·신뢰구간·p값을 함께 돌려준다.

    **그대로 쓴다.** 통계 계산은 도메인이 바뀌어도 같다.

    p값만 보면 '유의하지만 실질 효과가 없는' 경우를 놓친다.
    그래서 신뢰구간을 항상 함께 계산해 화면에 그린다.
    """
    rc, rt = sc / nc, stt / nt
    se = np.sqrt(rc * (1 - rc) / nc + rt * (1 - rt) / nt)
    if se == 0:
        return dict(rc=rc, rt=rt, nc=nc, nt=nt, diff=0, lo=0, hi=0, p=1.0, lift=0)
    z = (rt - rc) / se
    return dict(rc=rc, rt=rt, nc=nc, nt=nt, diff=rt - rc,
                lo=(rt - rc) - 1.96 * se, hi=(rt - rc) + 1.96 * se,
                p=2 * (1 - stats.norm.cdf(abs(z))),
                lift=(rt / rc - 1) if rc else 0)


def srm_check(asg: pd.DataFrame, exp_id: str) -> dict:
    """SRM(Sample Ratio Mismatch). 배정이 50:50인지 검정한다.

    **그대로 쓴다.** 7주차에 손으로 해본 그 계산이다.

    배정이 50:50이 아니면 배정 로직에 버그가 있다는 뜻이고,
    그 경우 어떤 효과가 나오든 해석할 수 없다.
    """
    a = asg[asg.experiment_id == exp_id]
    c = int((a.variant == "control").sum())
    t = int((a.variant == "treatment").sum())
    if c + t == 0:
        return {"ok": False, "c": 0, "t": 0, "p": 1.0, "ratio": (0.0, 0.0)}
    p = stats.chisquare([c, t]).pvalue
    return {"ok": p >= 0.001, "c": c, "t": t, "p": float(p),
            "ratio": (c / (c + t), t / (c + t))}


def trust_check(n_cell: int,
                years: set | None = None,
                compare: tuple[set, set] | None = None,
                *, guardrail: bool = False,
                t: dict | None = None) -> str | None:
    """이 숫자를 믿을 수 있는가. **계산하기 전에** 묻는다.

    ────────────────────────────────────────────────────────────
    어려운 일은 계산이 아니다.
    **계산은 이미 할 수 있는데, 화면에 안 그리는 코드를 쓰는 것**이다.
    ────────────────────────────────────────────────────────────

    못 믿을 조건은 셋인데 **분기는 하나**다. 하나라도 걸리면 사유 문자열을
    돌려주고, 부르는 쪽은 거기서 멈춰 **지표를 계산하지 않는다.**
    다 통과하면 None 을 돌려준다.

        1. 칸 표본이 얇다   n_cell < config.MIN_CELL_SAMPLE
                            -> 비율로 말할 수 없는 크기다
        2. 기간이 안 지났다  years 에 config.ACTUALS_LAST_YEAR 뒤가 있다
                            -> **가드레일에만 적용**(guardrail=True). 실적
                               대조가 없으니 괴리를 계산할 재료가 없다
        3. 제도가 다르다     compare 두 구간의 예산삭감연도 포함 여부가 다르다
                            -> 차이가 개입 때문인지 제도 때문인지 못 가른다

    **배정 검사(SRM)는 뺐다.** 이 도메인에 무작위 배정이 없다 — A/B 실험이
    없어 전후 비교로 대체하며, 그 경우 인과 주장 자체가 불가하다.
    (실험 데이터가 붙으면 srm_check() 를 부르는 쪽에서 따로 본다)

    인자
        n_cell    이 칸의 표본 수 (분해해서 만든 칸 하나)
        years     이 칸이 포함하는 cycle_year 집합. 조건 2 에 쓴다
        compare   비교하는 두 구간의 cycle_year 집합 쌍. 조건 3 에 쓴다
        guardrail 가드레일 지표인가. 조건 2 는 이때만 본다
        t         테이블 dict(선택). 주면 조건 2 사유에 실제 건수를 넣는다

    "그래도 회색으로라도 보여주면 안 되나요?"

        안 됩니다. **사람은 본 숫자를 기억합니다.**
        옆에 아무리 경고를 붙여도 회의실에서 인용되는 것은 숫자입니다.

    반환: 못 믿을 이유(str) 또는 None
    """
    # 1. 칸 표본
    if n_cell < C.MIN_CELL_SAMPLE:
        return f"표본 {n_cell:,}건 (최소 {C.MIN_CELL_SAMPLE})"

    # 2. 실적 대조 기간 — 가드레일에만 적용한다
    if guardrail and years:
        late = sorted(y for y in years if int(y) > C.ACTUALS_LAST_YEAR)
        if late:
            detail = ""
            if t is not None and "plans" in t and "plan_actuals" in t:
                pl, ac = t["plans"], t["plan_actuals"]
                ids = set(ac.plan_id.astype(str))
                m = pl[pl.cycle_year.isin(late) & pl.final_status.eq("확정배포")]
                n_conf = len(m)
                n_act = int(m.plan_id.astype(str).isin(ids).sum())
                detail = f" — 확정배포 {n_conf:,}건 중 실적 대조 {n_act:,}건"
            ys = "·".join(f"{y}년" for y in late)
            return (f"{ys}은 실적 대조 기간이 안 지났습니다"
                    f"{detail} (실적이 있는 마지막 연도 {C.ACTUALS_LAST_YEAR})")

    # 3. 제도가 다른 구간끼리 비교 — 차이를 개입 효과로 읽을 수 없다
    if compare:
        a, b = compare
        cut_a = bool({int(y) for y in a} & C.BUDGET_CUT_YEARS)
        cut_b = bool({int(y) for y in b} & C.BUDGET_CUT_YEARS)
        if cut_a != cut_b:
            def lab(ys, cut):
                return (f"{'·'.join(str(y) for y in sorted(int(x) for x in ys))}"
                        f"({'예산삭감연도' if cut else '평년'})")
            return (f"{lab(a, cut_a)} vs {lab(b, cut_b)} — 제도가 다름")

    return None


@st.cache_data(show_spinner=False)
def experiment_results(t: dict) -> list[dict]:
    """실험 결과와 판정.

    **판정 순서가 이 함수의 전부다.** 믿을 수 있는지 먼저 묻고,
    믿을 수 있을 때만 계산한다.

    좋은 결과를 먼저 보면 경고를 무시하고 싶어진다. 그래서 사람의 규율에
    맡기지 않고 **코드로 순서를 박는다.**

    실험이 없는 도메인이면 이 함수는 빈 목록을 돌려준다. 대신 전후 비교
    카드를 만들되 **"인과 주장 불가"를 카드에 박아 둔다.** → DESIGN.md §4-4
    """
    if "experiments" not in t or "experiment_assignments" not in t:
        return []
    ex, asg, fe = t["experiments"], t["experiment_assignments"], t["funnel_events"]
    reach = {s: set(fe.loc[fe.funnel_step == s, "visitor_id"]) for s in C.FUNNEL_STEPS}
    out = []
    for _, e in ex.iterrows():
        eid = e.experiment_id
        srm = srm_check(asg, eid)
        n_total = int((asg.experiment_id == eid).sum())
        row = {
            "id": eid, "name": e.experiment_name, "hypothesis": e.hypothesis,
            "primary": e.primary_metric, "guardrail": e.guardrail_metric,
            "start": e.start_date, "end": e.end_date, "srm": srm,
        }

        # ★ 판정이 계산보다 먼저다. 못 믿으면 여기서 끝난다.
        #   배정 검사는 trust_check 에서 뺐다(이 도메인에 무작위 배정이 없다).
        #   실험 데이터가 붙는 경로를 위해 여기서 따로 본다.
        reason = None
        if not srm.get("ok", True):
            reason = (f"배정 불균형 — control {srm['c']:,} : "
                      f"treatment {srm['t']:,} (p={srm['p']:.4f})")
        if reason is None:
            reason = trust_check(n_total)
        if reason:
            row["verdict"] = "무효"
            row["color"] = "block"
            row["reason"] = reason
            out.append(row)
            continue        # 지표를 계산하지 않는다. 숨기는 것이 아니다.

        # ── 여기부터 계산 ─────────────────────────────────────────
        if eid not in EXP_STEPS:
            row.update(verdict="데이터 없음", color="none",
                       reason="EXP_STEPS 에 이 실험의 구간이 없습니다.")
            out.append(row)
            continue
        sf, stp = EXP_STEPS[eid]
        a = asg[asg.experiment_id == eid][["visitor_id", "variant", "assigned_at"]]
        a = a[a.visitor_id.isin(reach[sf])]
        a = a.assign(conv=a.visitor_id.isin(reach[stp]).astype(int))
        g = a.groupby("variant", observed=True).conv.agg(["sum", "count"])
        if len(g) < 2:
            row.update(verdict="데이터 없음", color="none")
            out.append(row)
            continue
        r = _two_prop(g.loc["control", "sum"], g.loc["control", "count"],
                      g.loc["treatment", "sum"], g.loc["treatment", "count"])
        row.update(r, step_from=sf, step_to=stp, assignments=a)

        # 가드레일 — 주지표를 올리려 할 때 희생될 수 있는 것
        # ★ 아래는 통신사 컬럼(is_churned)이다. 내 가드레일 지표로 바꾼다.
        row["guard"] = None
        if "유지율" in str(e.guardrail_metric) and "customers" in t:
            cu = t["customers"]
            m = cu.merge(a[["visitor_id", "variant"]], on="visitor_id", how="inner")
            if len(m) and m.variant.nunique() == 2:
                ret = m.groupby("variant", observed=True).is_churned.mean()
                row["guard"] = {
                    "name": e.guardrail_metric,
                    "control": float(1 - ret["control"]),
                    "treatment": float(1 - ret["treatment"]),
                    "delta": float((1 - ret["treatment"]) - (1 - ret["control"])),
                }

        # 판정 — ★ 3%p 는 예시다. 내 가드레일 기준으로 바꾼다.
        sig = r["p"] < 0.05
        guard_bad = row["guard"] is not None and row["guard"]["delta"] < -0.03
        if guard_bad:
            # 주지표가 좋아져도 가드레일이 무너지면 성공이 아니다
            row.update(verdict="주의 필요", color="warn",
                       reason="주지표는 개선됐으나 가드레일이 악화됐습니다.")
        elif sig and r["lift"] > 0:
            row.update(verdict="성공", color="ok", reason="")
        elif sig:
            row.update(verdict="악화", color="block", reason="")
        else:
            row.update(verdict="효과 없음", color="none",
                       reason="통계적으로 유의한 차이가 없습니다.")
        out.append(row)
    return out


def peeking_curve(res: dict, start: str, cuts=(7, 14, 30, 60, 92)) -> pd.DataFrame:
    """관측 시점별 누적 결과. '그때 멈췄다면 무엇을 봤을까'를 재현한다.

    **그대로 쓴다.** 7주차에 겪은 조기 중단이다.
    """
    a = res.get("assignments")
    if a is None:
        return pd.DataFrame()
    a = a.copy()
    a["d"] = (to_dt(a.assigned_at) - pd.Timestamp(start)).dt.days
    rows = []
    for c in cuts:
        s = a[a.d <= c].groupby("variant", observed=True).conv.agg(["sum", "count"])
        if len(s) < 2 or s["count"].min() < 30:
            continue
        r = _two_prop(s.loc["control", "sum"], s.loc["control", "count"],
                      s.loc["treatment", "sum"], s.loc["treatment", "count"])
        rows.append({"cut": c, "lift": r["lift"], "p": r["p"], "sig": r["p"] < 0.05})
    return pd.DataFrame(rows)


def weekly_effect(res: dict, start: str, bucket_days: int = 14) -> pd.DataFrame:
    """기간을 쪼개 효과 추이를 본다. 신규성 효과는 전체 평균에 가려진다.

    **그대로 쓴다.** 7주차에 겪은 그것이다.
    """
    a = res.get("assignments")
    if a is None:
        return pd.DataFrame()
    a = a.copy()
    a["b"] = (to_dt(a.assigned_at) - pd.Timestamp(start)).dt.days // bucket_days
    g = (a[a.b >= 0].groupby(["b", "variant"], observed=True).conv
         .mean().unstack().dropna())
    if g.empty:
        return pd.DataFrame()
    g["lift"] = g.treatment / g.control - 1
    g = g.reset_index()
    g["label"] = g.b.apply(lambda i: f"{int(i)*2+1}~{int(i)*2+2}주")
    return g


# ── 채널 효율 (선택 과제) ─────────────────────────────────────────
@st.cache_data(show_spinner=False)
def channel_efficiency(t: dict) -> pd.DataFrame:
    """비용만 보면 순위가 뒤집힌다. 유지율까지 반영한 유효 비용을 함께 낸다.

    ★ Day3 선택 과제입니다. 안 만들어도 나머지가 돕니다.

    획득 비용이 싼 경로가 실제로 싼 것이 아니다 —
    데려온 대상이 남지 않으면 같은 자리를 다시 채워야 한다.

        유효 비용 = 획득 비용 / 유지율

    비용 개념이 없으면 **투입 공수(인시)**로 해도 된다.
    획득 경로 구분이 없으면 이 함수를 지운다.

    ★ 여기 쓰이는 CHANNEL_CAC 는 **가정값**이다. 광고비 실측 테이블에서
      유도하지 않는다 — 광고비는 개인 단위로 추적되지 않아 가입과 이을 수 없다.
      리포트에 이 값이 들어가면 "가정값 기반"을 문장에 남긴다. → DESIGN.md §4-3

    반환: DataFrame[채널, 방문, 가입, 전환율, CAC, 유지율, 유효CAC, 역전]
    """
    todo("Day3 선택 과제", "채널 효율",
         "내 도메인에 획득 경로 구분이 있습니까? 비용이 없으면 투입 공수로 바꾸십시오.",
         "core/metrics.py  channel_efficiency()")
