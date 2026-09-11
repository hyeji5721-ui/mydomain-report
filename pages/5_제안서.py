# -*- coding: utf-8 -*-
"""제안서 — 남에게 보내는 결재 문서 (9W Day3, 독립 메뉴).

리포트와 다른 문서다. 읽는 사람은 결정 권한을 가진 사람이고, 원하는 것은
"뭘 해야 하나 · 얼마짜리인가 · 틀리면 어쩌나"다. 그래서 계산 과정·함수
이름은 여기(화면·다운로드 문서 모두)에 안 넣는다 — 궁금하면 다른 화면을
보면 된다.

거르는 자리는 여기 한 곳뿐이다 — 주제를 고르면 report.proposal.build() 가
조립하고, 화면은 그 결과를 그대로 보여준다(화면에서 또 거르지 않는다).
"""
import streamlit as st

from core import config as C, load, metrics as M
from report import proposal as Pr
from viz import ui

st.set_page_config(page_title="제안서", page_icon="📋", layout="wide",
                   initial_sidebar_state="expanded")
ui.css()
ui.sidebar_nav("proposal")

if "run" not in st.session_state:
    st.session_state.run = None
if "proposal_human" not in st.session_state:
    st.session_state.proposal_human = {}
ui.context_bar(st.session_state.run)

t = ui.guard(load.load_all)
if t is None:
    st.stop()

st.markdown('<div style="font-size:24px;font-weight:800;margin-bottom:4px">'
            '제안서</div>', unsafe_allow_html=True)
st.caption("제안카드.md 를 읽어 조립합니다. 여기서는 카드 파일을 고치지 않습니다.")

cards = Pr.load_cards()
topics = M.proposal_topics(t)

# ① 주제 선택 — 맨 위 기본값은 "전체"(=아직 안 고름). 기각된 후보도
# "(차이 없음)" 을 붙여 목록에 남긴다 — 지우면 "안 봤다"와 "보고 아니었다"가
# 구분되지 않는다(9W Day3 판단 기준 ④).
options = ["전체"] + [
    f"{c['제목']} — 연 {c['규모_연간건수']}건" + (" (차이 없음)" if c["기각사유"] else "")
    for c in topics
]
picked = st.selectbox("주제", options, label_visibility="collapsed")
topic = None if picked == "전체" else topics[options.index(picked) - 1]

if topic is None:
    st.info("주제를 고르면 근거와 절 미리보기가 나옵니다.")
    st.stop()

if topic.get("기각사유"):
    st.warning(f"이 주제는 격차가 작아 기각됐습니다 — {topic['기각사유']}. "
              "그래도 문서는 만들 수 있습니다.")

evidence = M.topic_evidence(t, topic)

# ② 근거 요약 한 줄
st.markdown(f'<div class="card" style="margin:10px 0 18px;font-size:13.5px">'
           f'{topic["한줄"]}</div>', unsafe_allow_html=True)

# ③ 절별 미리보기 — 제목과 "답하는 질문"만. 계산 과정은 안 보여준다.
secs = Pr.build(topic, evidence, cards, st.session_state.proposal_human)
for s in secs:
    with st.expander(f'{s["제목"]}  ·  {"자동" if s["kind"]=="auto" else "사람 작성"}'):
        st.caption(s["질문"])
        if s["kind"] == "human":
            draft = st.text_area(
                s["제목"], value=s.get("문장", ""), height=140,
                placeholder=s.get("placeholder", ""),
                key=f"proposal_form_{s['제목']}", label_visibility="collapsed")
            if st.button("저장", key=f"proposal_save_{s['제목']}"):
                st.session_state.proposal_human[s["제목"]] = draft
                st.rerun()
        else:
            st.markdown(f'<div style="font-size:13.5px;line-height:1.7">'
                       f'{s.get("문장", "")}</div>', unsafe_allow_html=True)

# ④ HTML 내려받기
st.divider()
html = Pr.to_html(secs, topic)
st.download_button("제안서.html 다운로드", html, file_name="제안서.html",
                  mime="text/html", type="primary")
