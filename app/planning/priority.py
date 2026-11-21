"""PriorityEngine (UC-06, FR-11, FR-12).

Priority score = grade weight x difficulty x 1 / (days remaining + 1)
(Phase 2, Specification 1). Days remaining is 0 when a task is due today or overdue.
"""
import datetime as dt


def days_until(deadline, today):
    if isinstance(deadline, dt.datetime):
        deadline = deadline.date()
    if isinstance(today, dt.datetime):
        today = today.date()
    return max((deadline - today).days, 0)


def priority_score(weight, difficulty, deadline, today):
    if not 0 <= weight <= 100:
        raise ValueError("weight must be between 0 and 100")
    if not 1 <= difficulty <= 5:
        raise ValueError("difficulty must be between 1 and 5")
    urgency = 1 / (days_until(deadline, today) + 1)
    return round(weight * difficulty * urgency, 2)


def rank_tasks(tasks, today):
    """Sort task dicts (grade_weight, difficulty, deadline) from highest to lowest priority.
    Ties are broken by the earlier deadline."""
    return sorted(
        tasks,
        key=lambda t: (-priority_score(t["grade_weight"], t["difficulty"], t["deadline"], today), t["deadline"]),
    )


def explain_priority(task, today):
    """Short reason shown next to each ranked task (FR-12)."""
    days = days_until(task["deadline"], today)
    if task["deadline"] < today:
        when = "overdue"
    else:
        when = "due today" if days == 0 else ("due tomorrow" if days == 1 else f"due in {days} days")
    weight = task["grade_weight"]
    weight_txt = f"{weight:g}% of grade"
    hard = " · hard" if task["difficulty"] >= 4 else ""
    return f"{when} · {weight_txt}{hard}"
