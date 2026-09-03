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
        "경고 10.28 (347건 전체 중앙값) · 위험 16.76 (예산삭감연도 평균, n=169)"),
    "유지율": (
        "final_status 가 확정배포 또는 확정배포대기 / plans 전체 행 수 × 100",
        "임계값 없음 — 판정 기준을 정하지 않아 회색(판정 없음)으로 뜬다"),
}

k = ui.guard(M.kpis, t)
if k:
    m = ui.guard(M.monthly, t)
    cols = st.columns(len(k))
    for col, (name, v) in zip(cols, k.items()):
        with col:
            lv = M.status_of(name, v["value"])
            st.markdown(ui.kpi_card(name, v["fmt"].format(v["value"]), "", lv),
                        unsafe_allow_html=True)
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

# ── 획득 퍼널 ─────────────────────────────────────────────────────
ui.section("획득 퍼널", "그레인을 먼저 확인한다")
f = ui.guard(M.funnel, t["plan_stage_events"])
if f is not None:
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
        # 분해 축 세 개. 맨 앞이 기본으로 선택된다.
        #   department_name  부서 15개  (departments 에 있음) — 기본 축
        #   division_type    사업부 9 / 지원부서 6  (departments 에 있음)
        #   cycle_year       2022~2026, 예산삭감연도 2023·2025 여부
        DIMS = ["department_name", "division_type", "cycle_year"]
        DIM_DEFAULT = DIMS[0]

        # query_params 에서 초기값을 읽는다. 없거나 이상한 값이면 기본값.
        # 에러를 내면 안 되므로 in 검사로만 판정한다 — KeyError 를 안 낸다.
        _qp_dim = st.query_params.get("dim", DIM_DEFAULT)
        if _qp_dim not in DIMS:
            _qp_dim = DIM_DEFAULT

        dim = st.segmented_control("분해 축", DIMS, default=_qp_dim,
                                   label_visibility="collapsed")
        if dim not in DIMS:      # 다시 눌러 선택을 해제하면 None 이 온다
            dim = DIM_DEFAULT
        if st.query_params.get("dim") != dim:
            st.query_params["dim"] = dim
        i = st.selectbox(
            "구간", range(len(f) - 1),
            format_func=lambda i: f"{f.label.iloc[i]} → {f.label.iloc[i+1]}",
            index=min(bi - 1, len(f) - 2))
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

# ── 유지 퍼널 ─────────────────────────────────────────────────────
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
for r in (res or []):
    cls = r["color"]
    head = (f'<div class="exp {cls}">'
            f'<div style="display:flex;align-items:flex-start;gap:12px">'
            f'<div style="flex:1"><div class="id">{r["id"]}</div>'
            f'<div class="nm">{r["name"]}</div>'
            f'<div class="hy">{r["hypothesis"]}</div></div>'
            f'<div>{ui.badge(cls, r["verdict"])}</div></div>')

    if r["verdict"] == "무효":
        # 못 믿을 실험의 숫자는 보여주지 않는다.
        # 계산해 놓고 숨기는 것이 아니라 계산 자체를 하지 않았다.
        head += (f'<div class="blocked"><b>✕ 지표를 표시하지 않습니다</b><br>'
                 f'{r["reason"]}</div>')
        st.markdown(head + "</div>", unsafe_allow_html=True)
        continue

    if "rc" not in r:
        head += (f'<div style="margin-top:12px;font-size:13px;color:#64748b">'
                 f'{r.get("reason", "")}</div>')
        st.markdown(head + "</div>", unsafe_allow_html=True)
        continue

    head += (f'<div style="margin-top:14px;display:flex;gap:28px;'
             f'align-items:baseline;flex-wrap:wrap">'
             f'<div><div style="font-size:11px;color:#64748b">{r["primary"]}</div>'
             f'<div class="mv">{r["rc"]*100:.2f}% → {r["rt"]*100:.2f}%</div></div>'
             f'<div><div style="font-size:11px;color:#64748b">상대 효과</div>'
             f'<div class="mv">{r["lift"]*100:+.1f}%</div></div>'
             f'<div><div style="font-size:11px;color:#64748b">p값</div>'
             f'<div class="mv">{r["p"]:.4f}</div></div>'
             f'<div><div style="font-size:11px;color:#64748b">표본</div>'
             f'<div style="font-size:13px;color:#475569" class="num">'
             f'{r["nc"]:,} / {r["nt"]:,}</div></div></div>')
    st.markdown(head + "</div>", unsafe_allow_html=True)

    c1, c2 = st.columns([1, 1.1])
    with c1:
        st.caption("효과 크기와 95% 신뢰구간 (0을 지나면 유의하지 않음)")
        st.plotly_chart(charts.forest(r), width="stretch",
                        config={"displayModeBar": False}, key=f"fr_{r['id']}")
    with c2:
        if r.get("guard"):
            gd = r["guard"]
            bad = gd["delta"] < -0.03
            st.markdown(
                f'<div class="card tight" style="border-color:'
                f'{C.COLORS["warn"] if bad else C.BRAND["line"]}">'
                f'<div style="font-size:11px;color:#64748b">가드레일 · {gd["name"]}</div>'
                f'<div style="font-size:20px;font-weight:700;margin-top:4px" class="num">'
                f'{gd["control"]*100:.1f}% → {gd["treatment"]*100:.1f}% '
                f'<span style="color:{C.COLORS["warn"] if bad else C.COLORS["ok"]}">'
                f'({gd["delta"]*100:+.1f}%p)</span></div>'
                + ('<div class="note">주지표는 개선됐지만 가드레일이 무너졌습니다.</div>'
                   if bad else
                   '<div style="font-size:12px;color:#64748b;margin-top:6px">'
                   '이상 없음</div>')
                + '</div>', unsafe_allow_html=True)
        elif r.get("reason"):
            st.markdown(f'<div class="card tight">'
                        f'<div style="font-size:13px;color:#64748b">{r["reason"]}</div>'
                        f'</div>', unsafe_allow_html=True)

    # 기간을 쪼개야 드러나는 것 — 초기 효과가 남아 있는가
    w = M.weekly_effect(r, r["start"])
    if not w.empty and len(w) >= 3:
        with st.expander("기간을 쪼개서 보기 — 효과가 유지되는가"):
            st.plotly_chart(charts.effect_decay(w), width="stretch",
                            config={"displayModeBar": False})
            ui.callout(
                f"전체 평균은 <b>{r['lift']*100:+.1f}%</b>인데 "
                f"초반 <b>{w.lift.iloc[0]*100:+.0f}%</b>에서 "
                f"후반 <b>{w.lift.iloc[-1]*100:+.0f}%</b>로 갑니다. "
                f"기간 평균만 보면 안 보이는 것입니다.")

    # 그때 멈췄다면 무엇을 봤을까
    pc = M.peeking_curve(r, r["start"])
    if not pc.empty and len(pc) >= 3:
        with st.expander("만약 여기서 멈췄다면? — 조기 중단 시뮬레이터"):
            cuts = list(pc.cut.astype(int))
            sel = st.select_slider("실험 종료일", options=cuts, value=cuts[0],
                                   key=f"peek_{r['id']}")
            row = pc[pc.cut == sel].iloc[0]
            a, b = st.columns([1, 1.4])
            with a:
                lv = "warn" if row.sig else "none"
                st.markdown(
                    ui.kpi_card(f"{sel}일차에 종료했다면", f"{row.lift*100:+.1f}%",
                                "유의 — 성공으로 보고" if row.sig
                                else "유의하지 않음", lv),
                    unsafe_allow_html=True)
                st.caption(f"p = {row.p:.3f}")
            with b:
                st.plotly_chart(charts.peeking(pc, r["lift"]), width="stretch",
                                config={"displayModeBar": False})
            ui.callout("종료 시점은 실험을 **시작하기 전에** 정해야 합니다.")

# ── 채널 효율 (선택 과제) ─────────────────────────────────────────
ui.section("획득 경로 효율", "비용만 보면 순위가 뒤집힌다")
ce = ui.guard(M.channel_efficiency, t)
if ce is not None and len(ce):
    c1, c2 = st.columns([1.3, 1])
    with c1:
        st.plotly_chart(charts.cac_compare(ce), width="stretch",
                        config={"displayModeBar": False})
    with c2:
        naive = list(ce.sort_values("CAC").channel)
        real = list(ce.sort_values("유효CAC").channel)
        st.markdown(
            f'<div class="card tight">'
            f'<div style="font-size:12px;color:#64748b">단순 비용 순위</div>'
            f'<div style="font-size:14px;margin:4px 0 12px">{" < ".join(naive)}</div>'
            f'<div style="font-size:12px;color:#64748b">유지율 반영 순위</div>'
            f'<div style="font-size:14px;font-weight:700;color:{C.COLORS["block"]}">'
            f'{" < ".join(real)}</div></div>', unsafe_allow_html=True)
        st.caption("비용은 가정값입니다. 리포트에 쓸 때 '가정값 기반'을 남기십시오.")

# ── 현재 화면 링크 ────────────────────────────────────────────────
# 위에서 정리한 두 필터(dim · year)가 이미 st.query_params 에 반영된 뒤라,
# 이 시점의 쿼리스트링이 지금 화면 상태와 어긋나지 않는다.
st.divider()
st.caption("현재 화면 링크 — 복사해서 그대로 공유하면 같은 상태로 열립니다")
_qs = "&".join(f"{k}={v}" for k, v in st.query_params.items())
_base = (st.context.url.split("?")[0] if getattr(st.context, "url", None) else "")
st.code(f"{_base}?{_qs}" if _qs else (_base or "(주소는 브라우저 주소창에서 확인하십시오)"),
        language=None)
