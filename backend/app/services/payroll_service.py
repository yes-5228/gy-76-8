from datetime import date

from .validation import require_fields
from ..storage import mutate, read_data


def _deduplicate_settlements(settlements_list):
    seen = {}
    for item in settlements_list:
        key = (item["teacher_id"], item["month"])
        if key not in seen:
            seen[key] = item
    return list(seen.values())


def calculate_payroll(month=None):
    target_month = month or date.today().strftime("%Y-%m")
    data = read_data()
    deduped_settlements = _deduplicate_settlements(data["payroll_settlements"])
    if len(deduped_settlements) != len(data["payroll_settlements"]):
        def cleanup(data_inner):
            data_inner["payroll_settlements"] = _deduplicate_settlements(data_inner["payroll_settlements"])
            return data_inner
        mutate(cleanup)
        data = read_data()
        deduped_settlements = data["payroll_settlements"]

    settlements = {(item["teacher_id"], item["month"]): item for item in deduped_settlements}

    rows = []
    for teacher in data["teachers"]:
        records = [
            item
            for item in data["attendance"]
            if item["teacher_id"] == teacher["id"] and item["checked_at"].startswith(target_month)
        ]
        total_hours = round(sum(float(item["hours"]) for item in records), 2)
        amount = round(total_hours * float(teacher["hourly_rate"]), 2)
        settlement = settlements.get((teacher["id"], target_month))
        rows.append(
            {
                "teacher_id": teacher["id"],
                "teacher_name": teacher["name"],
                "subject": teacher["subject"],
                "month": target_month,
                "total_hours": total_hours,
                "hourly_rate": teacher["hourly_rate"],
                "amount": amount,
                "status": settlement["status"] if settlement else "pending",
                "settled_at": settlement.get("settled_at") if settlement else None,
            }
        )
    return rows


def settle_payroll(payload):
    require_fields(payload, ["teacher_id", "month"])
    teacher_id = payload["teacher_id"]
    month = payload["month"]

    pre_check_data = read_data()
    existing_settled = next(
        (
            item
            for item in pre_check_data["payroll_settlements"]
            if item["teacher_id"] == teacher_id and item["month"] == month and item["status"] == "settled"
        ),
        None,
    )
    if existing_settled:
        raise ValueError(f"该教师{month}月份课酬已结算，请勿重复操作")

    settlement = {
        "teacher_id": teacher_id,
        "month": month,
        "status": "settled",
        "settled_at": date.today().isoformat(),
    }

    def upsert(data):
        data["payroll_settlements"] = [
            item
            for item in data["payroll_settlements"]
            if not (item["teacher_id"] == teacher_id and item["month"] == month)
        ]
        data["payroll_settlements"].append(settlement)
        return data

    mutate(upsert)
    return settlement
