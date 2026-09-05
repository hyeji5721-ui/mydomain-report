# -*- coding: utf-8 -*-
"""대시보드 — 여기서 발견이 일어난다.

반복해서 보는 화면이므로 실행 절차를 지나치지 않고 바로 지표에 닿게 한다.

이 화면은 Day2~3에 걸쳐 살아난다.
  Day2  지표 카드 · 획득 퍼널 · 유지 퍼널
  Day3  분해 · 실험 카드
"""
import streamlit as st

from core import config as C, load, metrics as M
from viz import charts, ui

st.set_page_config(page_title="대시보드", page_icon="📊", layout="wide",
                   initial_sidebar_state="expanded")
ui.css()
ui.sidebar_nav("dash")

if "run" not in st.session_state:
    st.session_state.run = None
ui.context_bar(st.session_state.run)

t = ui.guard(load.load_all)
if t is None:
    st.stop()

@st.dialog("이 값을 왜 보여주지 않나")
def why_hidden(u: dict) -> None:
    """감춰진 카드의 근거만 보여준다. 지표 값·증감·p값은 넣지 않는다."""
    st.markdown(f"**걸린 조건** — {u['condition']}")
    cut = (f"{u['base_year']}년({'예산삭감연도' if u['cut_base'] else '평년'}) vs "
           f"{u['comp_year']}년({'예산삭감연도' if u['cut_comp'] else '평년'})")
    st.markdown(
        "| 항목 | 값 |\n|---|---|\n"
        f"| 표본 수 (실적 대조 건수) | {u['n_guard']:,}건 (최소 {u['min_cell']}건) |\n"
        f"| cycle_year | {u['cycle_year']} |\n"
        f"| 비교 구간의 예산삭감연도 여부 | {cut} |")

    if u["condition"] == "표본 부족":
        advice = "표본이 최소 기준(30건) 이상 쌓이면 판정 가능"
    elif u["condition"] == "대조 미도래":
        advice = (f"{u['comp_year']}년 실적이 적재되면(대조 기간 경과 후) 판정 가능")
    else:
        advice = "같은 성격의 연도끼리(평년 또는 예산삭감연도끼리만) 비교하면 판정 가능"
    st.markdown(f"**무엇을 하면 믿을 수 있는가** — {advice}")


st.markdown('<div style="font-size:24px;font-weight:800;margin-bottom:16px">'
            '대시보드</div>', unsafe_allow_html=True)

# ── 지표 카드 ─────────────────────────────────────────────────────
# 지표 이름 옆 "정의" — 계산식과 임계값 근거. 값·증감은 넣지 않는다.
KPI_DEFS = {
    "전체 통과율": (
        "final_status = '확정배포' 인 계획안 수 / plans 전체 행 수 × 100",
        "경고 70.0 · 위험 65.0 — 임의 지정, 통계적 산출 근거 없음"),
    "계획-실적 괴리율": (
        "plan_actuals.variance_pct 의 평균",
        "경고 10.28 (347건 전체 중앙값) · 위험 16.76 (예산삭감연도 평균, n=169) · "
        "표본 347/442건 (2026년 확정배포 95건은 실적 대조 기간이 아직 안 지나 결측)"),
    "유지율": (
        "final_status 가 확정배포 또는 확정배포대기 / plans 전체 행 수 × 100",
        "임계값 없음 — 판정 기준을 정하지 않아 회색(판정 없음)으로 뜬다"),
}

k = ui.guard(M.kpis, t)

# ── 한눈에 요약 배너 ─────────────────────────────────────────────
# 아래 섹션들이 각자 다시 계산하는 값을 여기서 한 번 더 구해 한 줄로 모은다 —
# funnel()·cohort_cards() 모두 @st.cache_data 라 이중 호출 비용은 사실상 없다.
if k and "전체 통과율" in k:
    _v = k["전체 통과율"]
    _bits = [f"전체 통과율 {_v['fmt'].format(_v['value'])}"
             f"({ui.STATUS_TEXT[M.status_of('전체 통과율', _v['value'])]})"]

    _f = ui.guard(M.funnel, t["plan_stage_events"])
    if _f is not None and _f.is_bottleneck.any():
        _bn = _f[_f.is_bottleneck].iloc[0]
        _bi = max(int(_f.index[_f.label == _bn.label][0]), 1)
        _prev = _f.iloc[_bi - 1]
        _bits.append(f"병목 {_prev.label} → {_bn.label}")

    _cards = ui.guard(M.cohort_cards, t) or []
    if _cards:
        _last = _cards[-1]
        _bits.append(f"최근 코호트({_last['base']}→{_last['comp']}) 판정 {_last['verdict']}")

    ui.callout(" · ".join(_bits), "info")

ui.section("핵심 지표", "카드 3개 — 임계값 근거 없는 지표는 판정 없음(회색)으로 둔다")
if k:
    m = ui.guard(M.monthly, t)
    cols = st.columns(len(k))
    for col, (name, v) in zip(cols, k.items()):
        with col:
            lv = M.status_of(name, v["value"])
            # delta 는 일부러 안 넣는다 — kpis() 는 2022~2026 전체 누적 한
            # 값이고 monthly() 는 코호트별 시계열이라, 최근 코호트 증감을
            # 델타로 넣으면 헤드라인(누적값)과 다른 걸 비교하는 셈이 된다.
            st.metric(name, v["fmt"].format(v["value"]), border=True)
            st.markdown(ui.badge(lv), unsafe_allow_html=True)
            if name in KPI_DEFS:
                calc, basis = KPI_DEFS[name]
                with st.popover("정의", use_container_width=False):
                    st.markdown(f"**계산식**  \n{calc}")
                    st.markdown(f"**임계값 근거**  \n{basis}")
            # 추이가 있으면 스파크라인. 지표 이름과 열 이름이 같아야 그려진다.
            if m is not None and name in getattr(m, "columns", []):
                st.plotly_chart(
                    charts.spark(m[name], C.COLORS[lv] if lv != "ok" else None),
                    width="stretch", config={"displayModeBar": False},
                    key=f"sp_{name}")
    if not C.THRESHOLDS:
        st.caption("config.THRESHOLDS 가 비어 있어 전부 정상으로 표시됩니다. "
                   "임계값을 채우면 색이 갈립니다.")

st.divider()

# ── 획득 · 유지 퍼널 (탭 + fragment) ────────────────────────────────
# 필터(축·구간)를 바꾸면 각 탭 안쪽만 다시 그려진다 — 전후비교·채널효율은 안 건드림.
# ⚠ query_params 갱신이 fragment 안에서 일어나, 맨 아래 "현재 화면 링크"(fragment
# 밖)는 필터를 바꾼 직후 다음 전체 재실행 때까지 한 박자 늦게 따라온다.
@st.fragment
def _acq_tab() -> None:
    ui.section("획득 퍼널", "그레인을 먼저 확인한다")
    f = ui.guard(M.funnel, t["plan_stage_events"])
    if f is None:
        return
    left, right = st.columns([1.15, 1])
    with left:
        st.plotly_chart(charts.funnel_bars(f), width="stretch",
                        config={"displayModeBar": False})
        bn = f[f.is_bottleneck].iloc[0]
        bi = max(int(f.index[f.label == bn.label][0]), 1)
        prev = f.iloc[bi - 1]
        ui.callout(
            f"<b>병목은 {prev.label} → {bn.label}</b> 구간입니다. "
            f"{prev.n:,} 중 {bn.n:,}만 넘어가 "
            f"<b>{(1-bn.step_rate)*100:.1f}%가 이탈</b>합니다.")

    with right:
        # 분해 축. 맨 앞이 기본으로 선택된다.
        #   department_name  부서 15개  (departments 에 있음) — 기본 축. 화면 표시는 "팀명"
        #   cycle_year       2022~2026, 예산삭감연도 2023·2025 여부. 화면 표시는 "연도"
        #   담당자           reviewer_id — 2026-09-05 추가. "구간"의 도착 단계 담당자별
        #   사전설명회       pre_briefing — 2026-09-05 추가. 병목 구간(경영진검토→
        #                    이사회승인) 원인 후보. 담당자와 달리 이건 개인이 아니라
        #                    "사전 설명회를 의무화한다"처럼 바로 개입할 수 있는 축이다.
        #                    지금은 그 병목 구간에만 값이 있다 — 다른 구간(94~96%
        #                    통과)은 조사할 문제가 없어 채우지 않았다.
        # division_type(사업부/지원부서)은 2026-09-05 에 화면에서 뺐다 — 판정 축이
        # 아니었고(개입 불가능해서, CLAUDE.md 참고) 같은 구간 격차도 0.2%p라 화면
        # 후보 가치도 낮다고 다시 판단함. funnel_by() 자체는 그대로 둔다(호출부만 뺌).
        DIMS = ["department_name", "cycle_year", "담당자", "사전설명회"]
        DIM_LABELS = {"department_name": "팀명", "cycle_year": "연도",
                      "담당자": "담당자", "사전설명회": "사전 설명회"}
        DIM_DEFAULT = DIMS[0]

        # query_params 에서 초기값을 읽는다. 없거나 이상한 값이면 기본값.
        # 에러를 내면 안 되므로 in 검사로만 판정한다 — KeyError 를 안 낸다.
        _qp_dim = st.query_params.get("dim", DIM_DEFAULT)
        if _qp_dim not in DIMS:
            _qp_dim = DIM_DEFAULT

        dim = st.segmented_control("분해 축", DIMS, default=_qp_dim,
                                   format_func=lambda d: DIM_LABELS[d],
                                   label_visibility="collapsed")
        if dim not in DIMS:      # 다시 눌러 선택을 해제하면 None 이 온다
            dim = DIM_DEFAULT
        if st.query_params.get("dim") != dim:
            st.query_params["dim"] = dim
        i = st.selectbox(
            "구간", range(len(f) - 1),
            format_func=lambda i: f"{f.label.iloc[i]} → {f.label.iloc[i+1]}",
            index=min(bi - 1, len(f) - 2))

        if dim == "담당자":
            # reviewer_pass_rate() 는 도착 단계 하나만 본다. "구간"의 도착
            # 단계는 늘 담당자가 있는 단계(FUNNEL_STEPS[1:])라 그대로 쓴다.
            rp = ui.guard(M.reviewer_pass_rate, t, f.step.iloc[i + 1])
            g = None
            if rp is not None and len(rp):
                g = rp.rename(columns={"reviewer_id": "담당자", "n": "도달"})
                g["전환율"] = g.pass_rate / 100
                g["전환"] = (g.도달 * g.전환율).round().astype(int)
                g["비중"] = g.도달 / g.도달.sum() if g.도달.sum() else float("nan")
                g = g[["담당자", "도달", "전환", "전환율", "비중"]]
        elif dim == "사전설명회":
            # briefing_pass_rate() 는 지금 병목 구간(이사회승인)에만 값이 있다.
            # 다른 구간을 고르면 표본 자체가 없어 빈 결과가 온다 — 조용히 안
            # 그리면 "축이 고장났나" 오해할 수 있어 이유를 알려준다.
            bp = ui.guard(M.briefing_pass_rate, t, f.step.iloc[i + 1])
            g = None
            if bp is not None and len(bp):
                g = bp.rename(columns={"pre_briefing": "사전설명회", "n": "도달"})
                g["전환율"] = g.pass_rate / 100
                g["전환"] = (g.도달 * g.전환율).round().astype(int)
                g["비중"] = g.도달 / g.도달.sum() if g.도달.sum() else float("nan")
                g = g[["사전설명회", "도달", "전환", "전환율", "비중"]]
            elif bp is not None:
                ui.callout(
                    "이 구간에는 사전 설명회 기록이 없습니다 — 지금은 병목 구간"
                    "(경영진검토 → 이사회승인)에만 있습니다.", "info")
        else:
            # funnel_by() 는 t 전체를 받는다 — 축이 plans / departments 로
            # 나뉘어 있어 함수가 직접 찾는다.
            g = ui.guard(M.funnel_by, t, dim, f.step.iloc[i], f.step.iloc[i + 1])

        if g is not None and len(g):
            st.plotly_chart(charts.device_compare(g), width="stretch",
                            config={"displayModeBar": False})
            hi = g.loc[g.전환율.idxmax()]
            lo = g.loc[g.전환율.idxmin()]
            if hi[g.columns[0]] != lo[g.columns[0]]:
                ui.callout(
                    f"<b>{lo[g.columns[0]]}</b>이(가) 전체의 "
                    f"<b>{lo.비중*100:.1f}%</b>인데 전환율은 "
                    f"<b>{lo.전환율*100:.1f}%</b>로 "
                    f"{hi[g.columns[0]]}({hi.전환율*100:.1f}%)보다 "
                    f"<b>{(hi.전환율-lo.전환율)*100:.1f}%p 낮습니다.</b>")


@st.fragment
def _retention_tab() -> None:
    ui.section("유지 퍼널", "데려온 대상이 남는가")
    if not C.RETENTION_STEPS:
        st.caption("config.RETENTION_STEPS 가 비어 있습니다. "
                   "7주차에 정한 유지·이탈의 정의를 옮기면 여기에 그려집니다.")
    rf = ui.guard(M.retention_funnel, t)
    if rf is not None and len(rf):
        if "is_bottleneck" not in rf.columns:
            rf = rf.assign(is_bottleneck=False)
        c1, c2 = st.columns([1.15, 1])
        with c1:
            st.plotly_chart(charts.funnel_bars(rf), width="stretch",
                            config={"displayModeBar": False})
        with c2:
            ui.callout(
                "유지는 <b>관측 기간이 대상마다 다릅니다.</b> "
                "먼저 들어온 대상은 오래 관측됐고 나중에 들어온 대상은 짧게 관측됐습니다. "
                "<b>누적값으로 비교하면 기간의 그림자를 효과로 착각합니다.</b> "
                "비율(단위 기간당)로 바꾸거나 같은 시점에 시작한 것끼리 묶으십시오.",
                "info")


_ftab1, _ftab2 = st.tabs(["획득 퍼널", "유지 퍼널"])
with _ftab1:
    _acq_tab()
with _ftab2:
    _retention_tab()

st.divider()

# ── 전후 비교 (실험이 없는 도메인) ──────────────────────────────────
ui.section("전후 비교", "믿을 수 있는지 먼저 보고, 그 다음에 지표를 본다")
res = ui.guard(M.experiment_results, t)
if res is not None and not res:
    st.caption("실험이 없어 전후 비교로 대신합니다. **인과를 주장할 수 없습니다.**")
    cards = ui.guard(M.cohort_cards, t) or []

    # 연도 필터 — 그 연도까지의 전후 비교만 본다. 지표 카드(전체 통과율 등)
    # 는 전체 기간 정의(위 "정의" 팝오버 참고)라 이 필터로 값이 바뀌지 않는다.
    YEARS = sorted({r["base"] for r in cards} | {r["comp"] for r in cards})
    if YEARS:
        _year_default = YEARS[-1]
        _qp_year_raw = st.query_params.get("year")
        try:
            _qp_year = int(_qp_year_raw)
        except (TypeError, ValueError):
            _qp_year = _year_default
        if _qp_year not in YEARS:
            _qp_year = _year_default

        year = st.select_slider("연도까지 보기", options=YEARS, value=_qp_year)
        if st.query_params.get("year") != str(year):
            st.query_params["year"] = str(year)
        cards = [r for r in cards if r["comp"] <= year]

    for r in cards:
        p, g = r["primary"], r["guardrail"]
        body = (
            f'<div class="exp {r["color"]}">'
            f'<div style="display:flex;align-items:flex-start;gap:12px">'
            f'<div style="flex:1"><div class="id">{r["base"]} → {r["comp"]}</div>'
            f'<div class="nm">{p["name"]}</div></div>'
            f'<div>{ui.badge(r["color"], r["verdict"])}</div></div>'
            f'<div style="margin-top:14px;display:flex;gap:28px;'
            f'align-items:baseline;flex-wrap:wrap">'
            f'<div><div style="font-size:11px;color:#64748b">{p["name"]}</div>'
            f'<div class="mv">{p["base"]:.2f}% → {p["comp"]:.2f}% '
            f'({p["delta"]:+.2f}%p)</div></div>')
        if g:
            body += (f'<div><div style="font-size:11px;color:#64748b">'
                     f'{g["name"]}</div>'
                     f'<div class="mv">{g["base"]:.2f}%p → {g["comp"]:.2f}%p '
                     f'({g["delta"]:+.2f}%p)</div></div>')
        body += (f'<div><div style="font-size:11px;color:#64748b">표본</div>'
                 f'<div style="font-size:13px;color:#475569" class="num">'
                 f'{p["n_base"]:,} / {p["n_comp"]:,}</div></div></div>'
                 f'<div style="margin-top:12px;font-size:13px;color:#475569">'
                 f'{r["reason"]}</div>'
                 f'<div style="margin-top:6px;font-size:12px;color:#94a3b8">'
                 f'{r["note"]}</div></div>')
        st.markdown(body, unsafe_allow_html=True)

        # 판정 과정 — 카드 하나당 상태 위젯 하나. 다시 st.status() 를 불러
        # update 하면 위젯이 하나 더 생긴다. with 이 돌려준 box 만 잡아 쓴다.
        with st.status("판정 과정", expanded=False) as box:
            if r["verdict"] == "가드레일 없음":
                st.write(f"1) 못 믿을 조건 확인 — 걸림 ({r['reason']})")
            else:
                st.write("1) 못 믿을 조건 확인 — 통과")

            if p is None:
                st.write("2) 주지표(전체 통과율) — 계산하지 않음")
            else:
                st.write(f"2) 주지표(전체 통과율) — {p['base']:.2f}% → "
                         f"{p['comp']:.2f}% ({p['delta']:+.2f}%p)")

            if g is None:
                st.write("3) 가드레일(계획-실적 괴리율) — 계산하지 않음")
            else:
                judge = ("나빠짐 (기준 " + f"{C.GUARDRAIL_MOVE}%p 초과)"
                          if g["worse"] >= C.GUARDRAIL_MOVE else "양호 (기준 이내)")
                st.write(f"3) 가드레일(계획-실적 괴리율) — {g['base']:.2f}%p → "
                         f"{g['comp']:.2f}%p ({g['delta']:+.2f}%p) · {judge}")

            # 안 닫으면 state 가 "running" 으로 남아 스피너가 계속 돈다.
            box.update(label=r["verdict"],
                       state="error" if r["verdict"] == "무효" else "complete")

        if r.get("untrust"):
            if st.button("왜 감췄나", key=f"why_{r['base']}_{r['comp']}"):
                why_hidden(r["untrust"])
# 개별 실험 카드(forest plot·조기중단 시뮬레이터 포함)를 그리는 코드는 뺐다 —
# 이 도메인엔 experiments/experiment_assignments 테이블 자체가 없어
# M.experiment_results(t) 가 항상 빈 리스트를 돌려주므로, 그 카드는 실행될 일이
# 없는 죽은 코드였다(위 "실험이 없어 전후 비교로 대신합니다" 분기만 실제로 탄다).
# 2026-09-05 결정. metrics.py 의 experiment_results()·forest()/peeking()/
# effect_decay() 는 그대로 둔다 — 화면 호출부만 뺐다(채널 효율 제거와 같은 방식).

# 채널 효율(Day3 선택 과제)은 뺐다 — 이 도메인엔 "유입 채널" 개념이 없다
# (부서×과제 단위 데이터라 획득 경로 구분이 존재하지 않는다). 2026-09-05 결정.
# metrics.channel_efficiency() 는 여전히 스텁으로 남아 있다 — 화면에서만 뺐다.

# ── 현재 화면 링크 ────────────────────────────────────────────────
# 위에서 정리한 두 필터(dim · year)가 이미 st.query_params 에 반영된 뒤라,
# 이 시점의 쿼리스트링이 지금 화면 상태와 어긋나지 않는다.
st.divider()
st.caption("현재 화면 링크 — 복사해서 그대로 공유하면 같은 상태로 열립니다")
_qs = "&".join(f"{k}={v}" for k, v in st.query_params.items())
_raw = getattr(st.context, "url", None) or ""
if _raw:
    from urllib.parse import urlsplit, urlunsplit, unquote
    _parts = urlsplit(_raw)
    _segs = [seg for seg in _parts.path.split("/") if seg]
    # 한글 페이지 이름에서 st.context.url 이 마지막 경로 조각을
    # 인코딩된 것과 원문으로 두 번 겹쳐 돌려줄 때가 있다. 디코딩해서
    # 같으면 하나만 남긴다 — 실제로 겹치지 않으면 아무 일도 하지 않는다.
    if len(_segs) >= 2 and unquote(_segs[-1]) == unquote(_segs[-2]):
        _segs = _segs[:-1]
    _path = "/" + "/".join(_segs)
    _base = urlunsplit((_parts.scheme, _parts.netloc, _path, "", ""))
else:
    _base = ""
st.code(f"{_base}?{_qs}" if _qs else (_base or "(주소는 브라우저 주소창에서 확인하십시오)"),
        language=None)
