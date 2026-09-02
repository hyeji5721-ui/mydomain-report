"""
경영계획(사업계획) 수립 퍼널 — 합성 데이터 생성 스크립트

퍼널: 부서 초안 제출 → 예산실 1차 조정 → 경영진 검토 → 이사회 승인 → 확정 배포
그레인: 계획안(부서×과제) 1건

실물 데이터가 없어(2026-08-29 확인) 명세부터 합성한다(경로 c).
난수 시드 고정 — 재실행해도 같은 데이터가 나온다.
"""
import numpy as np
import pandas as pd
from datetime import date, timedelta

rng = np.random.default_rng(42)

TODAY = date(2026, 8, 29)
STAGES = ["부서초안제출", "예산실1차조정", "경영진검토", "이사회승인", "확정배포"]
CYCLE_YEARS = [2022, 2023, 2024, 2025, 2026]
BUDGET_CUT_YEARS = {2023, 2025}  # 예산 삭감 연도 — 이사회승인 병목 심화

# ---------- 1. departments ----------
departments = [
    ("D01", "영업1팀", "사업부"),
    ("D02", "영업2팀", "사업부"),
    ("D03", "마케팅기획팀", "사업부"),
    ("D04", "해외사업팀", "사업부"),
    ("D05", "신사업개발팀", "사업부"),
    ("D06", "생산1공장", "사업부"),
    ("D07", "생산2공장", "사업부"),
    ("D08", "R&D1팀", "사업부"),
    ("D09", "R&D2팀", "사업부"),
    ("D10", "재무팀", "지원부서"),
    ("D11", "인사팀", "지원부서"),
    ("D12", "총무팀", "지원부서"),
    ("D13", "IT팀", "지원부서"),
    ("D14", "구매팀", "지원부서"),
    ("D15", "품질보증팀", "지원부서"),
]
df_dept = pd.DataFrame(departments, columns=["department_id", "department_name", "division_type"])

# ---------- 2 & 3. plans + plan_stage_events ----------
plan_rows = []
event_rows = []
plan_seq = 1
event_seq = 1

def stage_pass_prob(stage_idx, division_type, cycle_year):
    """stage_idx: 이 단계를 통과해 다음 단계로 넘어갈 확률(재도전 전 1차 시도 기준)"""
    base = [None, 0.78, 0.82, 0.65, 0.95]  # index 1~4 = 1->2, 2->3, 3->4, 4->5 전환
    p = base[stage_idx]
    if division_type == "지원부서" and stage_idx == 1:
        p += 0.07  # 지원부서는 추정치가 보수적이라 1차 조정 통과율이 더 높음
    if division_type == "사업부" and stage_idx == 1:
        p -= 0.06
    if stage_idx == 3 and cycle_year in BUDGET_CUT_YEARS:
        p -= 0.15  # 예산 삭감 연도엔 이사회승인 병목 심화
    return min(max(p, 0.05), 0.98)

for _, drow in df_dept.iterrows():
    dept_id, dept_name, div_type = drow["department_id"], drow["department_name"], drow["division_type"]
    for year in CYCLE_YEARS:
        n_tasks = rng.integers(4, 13)  # 연도별 4~12개 과제
        for t in range(n_tasks):
            plan_id = f"P{plan_seq:05d}"
            plan_seq += 1
            task_name = f"{dept_name} {year} 과제{t+1}"
            submitted = date(year, 1, 1) + timedelta(days=int(rng.integers(0, 75)))  # 1~3월 제출
            planned_amount = int(rng.lognormal(mean=17.5, sigma=0.9))  # 원 단위, 넓게 분포

            if submitted > TODAY:
                continue  # 아직 도래하지 않은 미래 제출은 생성하지 않음

            cur_date = submitted
            final_status = None
            # stage 1(부서초안제출)은 제출 자체 = 통과
            event_rows.append([f"E{event_seq:06d}", plan_id, 1, STAGES[0], cur_date.isoformat(), "통과", 1])
            event_seq += 1

            reached_stage = 1
            for stage_idx in range(1, 5):  # 1->2, 2->3, 3->4, 4->5
                if cur_date > TODAY:
                    final_status = "확정배포대기"
                    break
                # 자진 철회 확률(단계 진입 전)
                if rng.random() < 0.035:
                    cur_date = cur_date + timedelta(days=int(rng.integers(5, 30)))
                    event_rows.append([f"E{event_seq:06d}", plan_id, stage_idx + 1, STAGES[stage_idx], cur_date.isoformat(), "철회", 1])
                    event_seq += 1
                    final_status = "철회"
                    break

                p_pass = stage_pass_prob(stage_idx, div_type, year)
                attempt = 1
                passed = False
                while attempt <= 2:
                    cur_date = cur_date + timedelta(days=int(rng.integers(10, 45)))
                    if cur_date > TODAY:
                        final_status = "확정배포대기"
                        break
                    p_try = p_pass if attempt == 1 else min(p_pass + 0.20, 0.97)
                    if rng.random() < p_try:
                        event_rows.append([f"E{event_seq:06d}", plan_id, stage_idx + 1, STAGES[stage_idx], cur_date.isoformat(), "통과", attempt])
                        event_seq += 1
                        passed = True
                        reached_stage = stage_idx + 1
                        break
                    else:
                        event_rows.append([f"E{event_seq:06d}", plan_id, stage_idx + 1, STAGES[stage_idx], cur_date.isoformat(), "반려", attempt])
                        event_seq += 1
                        attempt += 1
                if final_status == "확정배포대기":
                    break
                if not passed:
                    final_status = "반려종결"
                    break

            if final_status is None:
                final_status = "확정배포" if reached_stage == 5 else "확정배포대기"

            plan_rows.append([plan_id, dept_id, year, task_name, submitted.isoformat(), planned_amount, final_status])

df_plans = pd.DataFrame(plan_rows, columns=[
    "plan_id", "department_id", "cycle_year", "task_name", "submitted_date", "planned_amount", "final_status"
])
df_events = pd.DataFrame(event_rows, columns=[
    "event_id", "plan_id", "stage_seq", "stage_name", "event_date", "result", "attempt_no"
])

# ---------- 결측·중복을 일부러 섞는다 ----------
# 2023년 이전 이벤트 중 3%는 event_date 결측(오래된 시스템 기록 누락)
old_mask = df_events["event_id"].isin(
    df_events.merge(df_plans[df_plans["cycle_year"] <= 2023][["plan_id"]], on="plan_id")["event_id"]
)
old_idx = df_events[old_mask].sample(frac=0.03, random_state=42).index
df_events.loc[old_idx, "event_date"] = None

# 이벤트의 2%는 중복 적재(시스템 이관 중복)
dup_rows = df_events.sample(frac=0.02, random_state=7)
df_events = pd.concat([df_events, dup_rows], ignore_index=True)

# ---------- 4. plan_actuals (확정배포 + 2025년 이전 사이클만 실적 확정) ----------
actual_rows = []
for _, prow in df_plans.iterrows():
    if prow["final_status"] != "확정배포" or prow["cycle_year"] > 2025:
        continue
    dept_type = df_dept.loc[df_dept["department_id"] == prow["department_id"], "division_type"].iloc[0]
    is_cut_year = prow["cycle_year"] in BUDGET_CUT_YEARS
    # 사업부가 변동성 크고, 예산 삭감 연도엔 오차가 더 커짐
    sigma = 0.10
    if dept_type == "사업부":
        sigma += 0.05
    if is_cut_year:
        sigma += 0.06
    variance_ratio = rng.normal(loc=0.0, scale=sigma)
    actual_amount = int(prow["planned_amount"] * (1 + variance_ratio))
    actual_rows.append([prow["plan_id"], prow["planned_amount"], actual_amount])

df_actuals = pd.DataFrame(actual_rows, columns=["plan_id", "planned_amount", "actual_amount"])
df_actuals["variance_pct"] = (
    (df_actuals["actual_amount"] - df_actuals["planned_amount"]).abs() / df_actuals["planned_amount"] * 100
).round(2)

# ---------- 저장 ----------
import os
out_dir = os.path.dirname(os.path.abspath(__file__))
df_dept.to_csv(os.path.join(out_dir, "departments.csv"), index=False, encoding="utf-8-sig")
df_plans.to_csv(os.path.join(out_dir, "plans.csv"), index=False, encoding="utf-8-sig")
df_events.to_csv(os.path.join(out_dir, "plan_stage_events.csv"), index=False, encoding="utf-8-sig")
df_actuals.to_csv(os.path.join(out_dir, "plan_actuals.csv"), index=False, encoding="utf-8-sig")

print(f"departments: {len(df_dept)} rows")
print(f"plans: {len(df_plans)} rows")
print(f"plan_stage_events: {len(df_events)} rows")
print(f"plan_actuals: {len(df_actuals)} rows")
