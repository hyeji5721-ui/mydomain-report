# -*- coding: utf-8 -*-
"""PDF 생성 (fpdf2).

한글 폰트는 Noto Sans KR(OFL)을 쓴다. 맑은 고딕은 재배포가 불가능하므로
앱에 동봉할 수 없다 — 라이선스는 배포 단계에서 실제로 문제가 된다.

fpdf2는 상태 저장형이다. set_font / set_text_color를 바꾸면 이후 계속 유지되므로
블록마다 명시적으로 지정한다.
"""
from __future__ import annotations

import io
from datetime import datetime

from fpdf import FPDF

from core import config as C

FONT_DIR = C.ROOT / "fonts"
INK = (15, 23, 42)
MUTED = (100, 116, 139)
LINE = (226, 232, 240)

# 표의 숫자 열 중 %로 찍을 것. 여기 없는 float 열(예: 준비기간의 "일")은
# 그냥 소수 한 자리로만 찍는다 — %를 붙이면 단위가 아닌데 % 처럼 보인다.
PERCENT_HEADERS = {"전환율", "직전 단계 대비", "1단계 대비 누적"}


def _hex(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _kpi_cards(pdf, cards: list[dict]) -> None:
    """1장 지표를 색 있는 박스 3개로 그린다. 화면의 st.metric+badge와 같은 역할이다."""
    gap = 6
    total_w = pdf.w - pdf.l_margin - pdf.r_margin
    card_w = (total_w - gap * (len(cards) - 1)) / len(cards)
    h = 26
    y0 = pdf.get_y()
    if y0 + h > pdf.h - pdf.b_margin:
        pdf.add_page()
        y0 = pdf.get_y()
    for i, c in enumerate(cards):
        x = pdf.l_margin + i * (card_w + gap)
        color = _hex(C.COLORS.get(c["status"], C.COLORS["none"]))
        pdf.set_draw_color(*LINE)
        pdf.set_line_width(0.3)
        pdf.rect(x, y0, card_w, h)
        pdf.set_xy(x + 4, y0 + 4)
        pdf.set_font(pdf.base, "B", 15)
        pdf.set_text_color(*color)
        pdf.cell(card_w - 8, 8, c["value"], align="L")
        pdf.set_xy(x + 4, y0 + 13)
        pdf.set_font(pdf.base, "", 9)
        pdf.set_text_color(*MUTED)
        pdf.multi_cell(card_w - 8, 4.5, c["name"])
    pdf.set_xy(pdf.l_margin, y0 + h + 6)


class Report(FPDF):
    def __init__(self):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.set_auto_page_break(True, margin=20)
        self.has_kr = False
        reg, bold = FONT_DIR / "NotoSansKR-Regular.ttf", FONT_DIR / "NotoSansKR-Bold.ttf"
        if reg.exists():
            self.add_font("Noto", "", str(reg))
            self.add_font("Noto", "B", str(bold) if bold.exists() else str(reg))
            self.has_kr = True
        self.base = "Noto" if self.has_kr else "Helvetica"

    def header(self):
        if self.page_no() == 1:
            return
        self.set_font(self.base, "", 8)
        self.set_text_color(*MUTED)
        self.cell(0, 6, f"{C.DATASET}  ·  {C.PERIOD[0]} ~ {C.PERIOD[1]}",
                  align="L")
        self.ln(8)

    def footer(self):
        if self.page_no() == 1:
            return
        self.set_y(-15)
        self.set_font(self.base, "", 8)
        self.set_text_color(*MUTED)
        self.cell(0, 8, str(self.page_no()), align="C")


def build_pdf(sections: list[dict], charts: dict[str, bytes],
              title: str = "성장 성과 분석") -> bytes:
    pdf = Report()

    # ── 표지 + 목차 (한 페이지) ──────────────────────────────────────
    # 2026-09-05: 전엔 표지·목차가 각각 페이지 하나씩(둘 다 절반 이상 빈 공간)
    # 이었다 — 합쳐서 첫 페이지 낭비를 줄인다.
    pdf.add_page()
    pdf.ln(40)
    pdf.set_font(pdf.base, "B", 26)
    pdf.set_text_color(*INK)
    pdf.multi_cell(0, 12, title, align="L")
    pdf.ln(3)
    pdf.set_font(pdf.base, "", 12)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 8, f"{C.PERIOD[0]} ~ {C.PERIOD[1]}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, f"데이터셋 {C.DATASET}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)
    pdf.set_draw_color(*_hex(C.BRAND["primary"]))
    pdf.set_line_width(1.2)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + 40, pdf.get_y())
    pdf.ln(10)
    pdf.set_font(pdf.base, "", 10)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 6, f"생성 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
             new_x="LMARGIN", new_y="NEXT")

    pdf.ln(20)
    pdf.set_font(pdf.base, "B", 15)
    pdf.set_text_color(*INK)
    pdf.cell(0, 10, "목차", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    for s in sections:
        pdf.set_font(pdf.base, "", 11)
        pdf.set_text_color(*INK)
        mark = "" if s["kind"] == "auto" else "  (사람 작성)"
        pdf.cell(0, 8, s["title"] + mark, new_x="LMARGIN", new_y="NEXT")

    # ── 본문 ──────────────────────────────────────────────────────
    # 장마다 무조건 새 페이지로 넘기지 않는다 — 짧은 장(6·8장 등)이 페이지를
    # 통째로 낭비했다. 첫 장만 새 페이지로 시작하고, 그 다음부터는 남은 공간이
    # 부족할 때만(제목+구분선이 겨우 들어갈 정도) 페이지를 넘긴다. 중간에
    # 표·차트가 넘치는 것은 set_auto_page_break 가 알아서 처리한다.
    for i, s in enumerate(sections):
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

        body = (s.get("body") or "").strip()
        if not body:
            pdf.set_font(pdf.base, "", 10)
            pdf.set_text_color(*MUTED)
            pdf.multi_cell(0, 6, f"[작성되지 않음] {s.get('placeholder','')}")
            continue

        pdf.set_font(pdf.base, "", 10.5)
        pdf.set_text_color(*INK)
        for para in body.split("\n\n"):
            pdf.multi_cell(0, 6.2, para.strip())
            pdf.ln(3)

        if s.get("kpi_cards"):
            _kpi_cards(pdf, s["kpi_cards"])

        for tbl in s.get("tables", []):
            rows = tbl.get("rows") or []
            if not rows:
                continue
            if pdf.get_y() > 210:
                pdf.add_page()
            if tbl.get("caption"):
                pdf.set_font(pdf.base, "B", 9.5)
                pdf.set_text_color(*MUTED)
                pdf.cell(0, 6, tbl["caption"], new_x="LMARGIN", new_y="NEXT")
                pdf.ln(1)
            headers = list(rows[0].keys())
            pdf.set_font(pdf.base, "", 9.5)
            pdf.set_text_color(*INK)
            with pdf.table(line_height=6,
                          borders_layout="SINGLE_TOP_LINE") as pdf_table:
                head_row = pdf_table.row()
                for h in headers:
                    head_row.cell(h, align="LEFT" if h == headers[0] else "RIGHT")
                for r in rows:
                    row = pdf_table.row()
                    for h in headers:
                        v = r[h]
                        if h == headers[0] or isinstance(v, str):
                            text = str(v)
                        elif v is None:
                            text = "-"
                        elif isinstance(v, int):
                            text = f"{v:,}건"
                        elif h in PERCENT_HEADERS:
                            text = f"{v:.2f}%"
                        else:
                            text = f"{v:.1f}"
                        row.cell(text, align="LEFT" if h == headers[0] else "RIGHT")
            pdf.ln(4)

        for key in s.get("charts", []):
            png = charts.get(key)
            if not png:
                continue
            if pdf.get_y() > 200:
                pdf.add_page()
            pdf.ln(2)
            pdf.image(io.BytesIO(png), w=pdf.w - pdf.l_margin - pdf.r_margin)
            pdf.ln(4)

    out = pdf.output()
    return bytes(out)
