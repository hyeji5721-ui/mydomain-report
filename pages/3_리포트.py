# -*- coding: utf-8 -*-
"""리포트 — 남에게 보내는 문서.

8장 중 5장은 자동으로 쓰고, **3장(배경·해석·제안)은 사람이 쓴다.**
자동 생성 문장은 인과를 단정하지 않는지 스스로 검사한다.
"""
from datetime import datetime

import pandas as pd
import streamlit as st

from core import config as C, gates, load, metrics as M
from report import sections as S, to_pdf
from viz import pdf_charts, ui

st.set_page_config(page_title="리포트", page_icon="📄", layout="wide",
                   initial_sidebar_state="expanded")
ui.css()
ui.sidebar_nav("report")

if "run" not in st.session_state:
    st.session_state.run = None
if "human" not in st.session_state:
    st.session_state.human = {}
ui.context_bar(st.session_state.run)

t = ui.guard(load.load_all)
if t is None:
    st.stop()
if "limits_rows" not in st.session_state:
    st.session_state.limits_rows = None   # None = 아직 편집 안 함 → 기본값 그대로
secs = S.build(t, st.session_state.human, limits_rows=st.session_state.limits_rows)

# 리포트 차트에 쓸 분해 축. department_name 이 판정 축이다(2026-09-03) —
# 격차가 커서가 아니라 부서 단위로 개입할 수 있어서다. 4장 본문도 이 축을 쓴다.
# (화면은 라디오로 고르지만 리포트는 문서라 축을 하나로 박는다)
DIM = "department_name"

st.markdown('<div style="font-size:24px;font-weight:800;margin-bottom:16px">'
            '리포트</div>', unsafe_allow_html=True)

nav, body = st.columns([1, 3.4])

with nav:
    titles = [s["title"] for s in secs]
    pick = st.radio("목차", titles, label_visibility="collapsed")
    st.divider()
    done = sum(1 for s in secs if s["kind"] == "human" and s["body"].strip())
    need = sum(1 for s in secs if s["kind"] == "human")
    left = sum(1 for s in secs if s["kind"] == "todo")
    st.caption(f"사람 작성 {done}/{need}장")
    st.progress(done / need if need else 0)
    if left:
        st.caption(f"아직 안 만든 장 {left}개")

sec = next(s for s in secs if s["title"] == pick)

with body:
    kind = {"auto": "자동 생성", "human": "사람 작성",
            "todo": "아직 안 만듦"}[sec["kind"]]
    lvl = {"auto": "ok", "todo": "none"}.get(
        sec["kind"], "ok" if sec["body"].strip() else "warn")
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:12px;margin-bottom:10px">'
        f'<div style="font-size:19px;font-weight:700">{sec["title"]}</div>'
        f'{ui.badge(lvl, kind)}</div>', unsafe_allow_html=True)

    if sec["kind"] == "todo":
        ui.todo_card(sec["todo"])
    elif sec["title"] == "7. 한계":
        for line in S.limits_always(t):
            st.markdown(f"- {line}")
        st.caption("아래 표는 검증 결과에서 자동으로 조립했습니다. "
                  "포함을 끄거나, 행을 지우거나, 새로 추가할 수 있습니다.")

        auto_rows = sec["rows"]
        if st.session_state.limits_rows is None:
            st.session_state.limits_rows = [dict(r, 포함=True) for r in auto_rows]

        df = pd.DataFrame(st.session_state.limits_rows,
                          columns=["출처", "내용", "포함"])
        edited = st.data_editor(
            df, key="limits_editor", num_rows="dynamic", width="stretch",
            column_config={
                "출처": st.column_config.SelectboxColumn(
                    "출처", options=S.LIMITS_SOURCES, required=True),
                "내용": st.column_config.TextColumn("내용", required=True),
                "포함": st.column_config.CheckboxColumn("포함", default=True),
            })
        st.session_state.limits_rows = edited.to_dict("records")

        # _s7_limits() 가 지금 데이터로 다시 조립하면 있어야 할 행(auto_rows)이
        # 편집 결과(포함 여부와 무관하게, 행 자체)에 없으면 "지웠다"고 남긴다.
        remaining = set(edited["내용"])
        for r in auto_rows:
            if r["내용"] not in remaining:
                ui.callout(f"검증 경고를 뺐습니다 — \"{r['내용']}\"")

        body = S.render_limits(t, st.session_state.limits_rows)
        bad = S.check_phrasing(body)
        if bad:
            ui.callout(f"인과를 단정하는 표현이 있습니다: <b>{', '.join(bad)}</b>. "
                       f"관측 데이터로는 인과를 주장할 수 없습니다.")
        else:
            st.caption("✓ 인과 단정 표현 검사 통과")
    elif sec["kind"] == "auto":
        st.markdown(
            f'<div class="card"><div style="white-space:pre-line;'
            f'font-size:14px;line-height:1.75">{sec["body"]}</div></div>',
            unsafe_allow_html=True)
        bad = S.check_phrasing(sec["body"])
        if bad:
            ui.callout(f"자동 생성 문장에 인과를 단정하는 표현이 있습니다: "
                       f"<b>{', '.join(bad)}</b>. 관측 데이터로는 인과를 "
                       f"주장할 수 없습니다.")
        else:
            st.caption("✓ 인과 단정 표현 검사 통과")

        if sec.get("kpi_cards"):
            cols = st.columns(len(sec["kpi_cards"]))
            for col, c in zip(cols, sec["kpi_cards"]):
                with col:
                    st.metric(c["name"], c["value"], border=True)
                    st.markdown(ui.badge(c["status"]), unsafe_allow_html=True)

        for tbl in sec.get("tables", []):
            if tbl.get("caption"):
                st.caption(tbl["caption"])
            st.dataframe(
                pd.DataFrame(tbl["rows"]), width="stretch", hide_index=True,
                column_config={
                    "도달": st.column_config.NumberColumn("도달", format="%d건"),
                    "전환": st.column_config.NumberColumn("전환", format="%d건"),
                    "전환율": st.column_config.NumberColumn("전환율", format="%.2f%%"),
                    "직전 단계 대비": st.column_config.NumberColumn(
                        "직전 단계 대비", format="%.2f%%"),
                    "1단계 대비 누적": st.column_config.NumberColumn(
                        "1단계 대비 누적", format="%.2f%%"),
                    "평균 준비기간(일)": st.column_config.NumberColumn(
                        "평균 준비기간(일)", format="%.1f일"),
                })

        if "funnel" in sec.get("charts", []):
            f = M.funnel(t["plan_stage_events"])
            st.image(pdf_charts.funnel_png(f), width="stretch")
        if "device" in sec.get("charts", []):
            f = M.funnel(t["plan_stage_events"])
            bi = max(int(f.index[f.is_bottleneck][0]), 1)
            g = M.funnel_by(t, DIM, f.step.iloc[bi - 1], f.step.iloc[bi])
            st.image(pdf_charts.device_png(g), width="stretch")
        if "experiments" in sec.get("charts", []):
            st.image(pdf_charts.experiments_png(M.experiment_results(t)),
                     width="stretch")
    else:
        # 세 장을 st.form 하나로 묶는다. 폼 밖의 개별 text_area 는 글자 하나
        # 칠 때마다 전체 화면을 다시 돌린다 — 폼 안에서는 "저장"을 눌러야만
        # 다시 돈다. 어느 사람 작성 장을 보고 있어도 셋을 한 번에 고친다.
        human_secs = {s["title"]: s for s in secs if s["kind"] == "human"}
        with st.form("사람이 쓰는 장"):
            drafts = {}
            for title in ["2. 배경", "6. 해석", "8. 제안"]:
                hs = human_secs[title]
                st.markdown(f"**{title}**")
                if hs.get("guide"):
                    ui.callout("<b>참고 가이드</b><br>" +
                               "<br>".join(f"· {line}" for line in hs["guide"]),
                               "info")
                if hs.get("guide_disclaimer"):
                    ui.callout(hs["guide_disclaimer"])
                # 예시 문장을 박스 초기값으로 넣는다(내용이 비어 있을 때만 —
                # 이미 쓴 내용을 덮어쓰지 않는다). [ ] 로 남겨둔 판단 부분은
                # 지우지 않고 그대로 제출하면 예시가 리포트에 그대로 실린다 —
                # 저장 전에 반드시 괄호를 채우거나 지워야 한다.
                drafts[title] = st.text_area(
                    title, value=hs["body"] or hs.get("example", ""), height=200,
                    placeholder=hs["placeholder"], key=f"form_{title}",
                    label_visibility="collapsed")
                st.divider()
            submitted = st.form_submit_button("저장", type="primary")

        if submitted:
            st.session_state.human.update(drafts)
            # 걸려도 저장은 한다 — 저장을 막는 검증이 아니라 사람이 쓴 뒤
            # 스스로 다시 보게 하는 경고다(check_phrasing() 과 같은 자리).
            flagged = {title: S.check_phrasing(text)
                      for title, text in drafts.items() if S.check_phrasing(text)}
            unresolved = {title: S.check_placeholders(text)
                         for title, text in drafts.items() if S.check_placeholders(text)}
            msgs = []
            if flagged:
                detail = " / ".join(f"{title}: {', '.join(words)}"
                                    for title, words in flagged.items())
                msgs.append(f"인과를 단정하는 표현이 있습니다 — {detail}. "
                           f"관측 데이터로는 인과를 주장할 수 없습니다.")
            if unresolved:
                detail = " / ".join(f"{title}: {len(items)}곳"
                                    for title, items in unresolved.items())
                msgs.append(f"예시 문장의 [ ] 자리가 안 채워졌습니다 — {detail}. "
                           f"그대로 두면 리포트에 대괄호가 그대로 실립니다.")
            if msgs:
                ui.callout("저장했습니다. 다만 " + " ".join(msgs))
            else:
                st.success("저장했습니다. 세 장 모두 검사 통과.")

# ── 내보내기 ──────────────────────────────────────────────────────
st.divider()
ui.section("내보내기")

c1, c2 = st.columns(2)
with c1:
    st.markdown("**PDF** — 표지 · 목차 · 차트 포함")
    if st.button("PDF 만들기", type="primary"):
        pdf = None
        with st.status("리포트를 만드는 중", expanded=True) as box:
            try:
                st.write("1) 장별 내용 모으는 중")
                # secs 는 위에서 이미 조립됨 — 사람 작성 폼·7장 한계 편집 결과가
                # 그대로 반영된 상태다. 여기서 다시 만들지 않는다.

                st.write("2) 퍼널·병목 분해 차트 이미지 만드는 중")
                f = M.funnel(t["plan_stage_events"])
                bi = max(int(f.index[f.is_bottleneck][0]), 1)
                g = M.funnel_by(t, DIM, f.step.iloc[bi - 1], f.step.iloc[bi])
                # 이 도메인엔 실험이 없다 — M.experiment_results(t) 는 항상 빈
                # 리스트라 "experiments" 차트를 만들어도 어느 장의 charts 에도
                # 안 걸려 안 쓰인다. (pdf_charts.experiments_png([]) 는 에러
                # 없이 빈 차트를 돌려주는 것만 확인했고, 안 쓰는 계산을 남겨
                # 둘 이유가 없어 뺐다)
                charts = {
                    "funnel": pdf_charts.funnel_png(f),
                    "device": pdf_charts.device_png(g),
                }

                st.write("3) PDF 조립하는 중")
                pdf = to_pdf.build_pdf(secs, charts)

                box.update(label="완성", state="complete", expanded=False)
            except Exception as e:
                st.write(f"실패: {e}")
                box.update(label="실패", state="error", expanded=True)

        if pdf is not None:
            st.session_state.pdf = pdf
            # ⚠ 파일 이름에만 쓰는 화면 표시용 시각이다. 지표·판정 계산에는
            # 현재 시각을 넣지 않는다 — 넣으면 같은 입력이 같은 결과를 내지
            # 않아 재현이 안 된다.
            st.session_state.pdf_made_at = datetime.now()
            st.toast("리포트가 만들어졌습니다", icon="📄")
    if st.session_state.get("pdf"):
        made_at = st.session_state.pdf_made_at
        st.download_button(
            "PDF 내려받기", st.session_state.pdf,
            file_name=(f"성장리포트_{C.PERIOD[0][:7]}_"
                      f"{made_at:%Y%m%d-%H%M%S}.pdf"),
            mime="application/pdf")

with c2:
    st.markdown("**이메일 초안** — 실제로 보내지 않습니다")
    draft = S.email_draft(t, secs)
    st.text_input("받는 사람", draft["to"], disabled=True)
    st.text_input("제목", draft["subject"], disabled=True)
    with st.expander("본문 미리보기"):
        st.markdown(draft["html"], unsafe_allow_html=True)

    run = st.session_state.run
    if run and gates.is_passed(run, 2):
        # 되돌릴 수 없는 조작은 화면이 그 무게를 보여줘야 한다 — 강조 색만으론
        # 부족해서, 확인 문구를 그대로 입력해야만 버튼이 풀리는 마찰을 뒀다.
        # 실수로 누르는 것과 실제로 마음먹고 누르는 것을 구별하는 장치다.
        st.markdown('<div class="gate final" style="margin-top:12px">'
                    '<div class="q">게이트 3 · 발송</div>'
                    '<div style="font-size:12.5px;color:#9f1239;margin-top:6px">'
                    '<b>되돌릴 수 없습니다.</b> 통과시키면 발송 기록이 남습니다.</div>'
                    '</div>', unsafe_allow_html=True)
        if gates.is_passed(run, 3):
            st.success("게이트 3 통과 기록됨 · 실제 발송은 하지 않았습니다.")
        else:
            ok = st.text_input('확인 문구로 "발송"을 입력하십시오', key="g3")
            if st.button("확정", disabled=(ok != "발송")):
                gates.pass_gate(run, 3, "초안 확정 (실제 발송 없음)")
                gates.save(run)
                st.rerun()
    else:
        st.caption("게이트 2를 통과해야 발송 확정 단계가 열립니다.")
