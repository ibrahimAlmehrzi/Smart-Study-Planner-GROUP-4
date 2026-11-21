"""ScheduleGenerator (UC-05, UC-07, FR-13 to FR-15).

Pure functions with no database access, so they can be unit tested directly.
Times are naive datetime objects in the student's local time.
"""
import datetime as dt

from .priority import rank_tasks

MIN_SESSION = 25          # minutes (FR-13)
REVIEW_OFFSETS = (7, 3, 1)  # days before an exam (FR-14)
HORIZON_DAYS = 28


def _t(value):
    if isinstance(value, dt.time):
        return value
    h, m, *s = [int(p) for p in str(value).split(":")]
    return dt.time(h, m, s[0] if s else 0)


def subtract(intervals, cut_start, cut_end):
    """Remove [cut_start, cut_end) from a list of (start, end) intervals."""
    out = []
    for s, e in intervals:
        if cut_end <= s or cut_start >= e:
            out.append((s, e))
            continue
        if s < cut_start:
            out.append((s, cut_start))
        if cut_end < e:
            out.append((cut_end, e))
    return out


def build_free_slots(start, end, blocks, busy=(), occupied=()):
    """Free time between start and end: weekly availability blocks minus busy events and existing sessions.

    blocks:   [{'day_of_week': 0..6 (Mon=0), 'start_time': 'HH:MM', 'end_time': 'HH:MM'}]
    busy, occupied: [(start, end)] datetime pairs
    """
    slots = []
    day = start.date()
    while day <= end.date():
        for b in blocks:
            if int(b["day_of_week"]) != day.weekday():
                continue
            s = dt.datetime.combine(day, _t(b["start_time"]))
            e = dt.datetime.combine(day, _t(b["end_time"]))
            s, e = max(s, start), min(e, end)
            if e > s:
                slots.append((s, e))
        day += dt.timedelta(days=1)
    for s, e in list(busy) + list(occupied):
        slots = subtract(slots, s, e)
    return sorted(x for x in slots if (x[1] - x[0]).total_seconds() >= 60)


def find_slot(slots, minutes, deadline, usage, daily_limit_min, on_day=None):
    """Earliest start time that fits `minutes` before the deadline without passing the daily limit."""
    need = dt.timedelta(minutes=minutes)
    for s, e in slots:
        if on_day is not None and s.date() != on_day:
            continue
        if s + need > e or s + need > deadline:
            continue
        if usage.get(s.date(), 0) + minutes > daily_limit_min:
            continue
        return s
    return None


def take(slots, start, minutes, usage):
    """Reserve a slot: remove it from the free list and add it to that day's usage."""
    end = start + dt.timedelta(minutes=minutes)
    slots[:] = sorted(subtract(slots, start, end))
    usage[start.date()] = usage.get(start.date(), 0) + minutes
    return end


def generate_plan(now, tasks, blocks, busy=(), kept=(), daily_limit_hours=4.0, session_length=50):
    """Build study and review sessions for all open tasks.

    tasks: [{'task_id', 'task_type', 'deadline' (datetime), 'grade_weight', 'difficulty',
             'remaining_minutes'}]  remaining_minutes already excludes completed and kept work.
    kept:  [(start, end)] sessions that must stay where they are (completed, locked, ...).
    Returns (sessions, at_risk) where sessions is a list of dicts and at_risk maps task_id -> shortfall hours.

    Steps: (1) reserve spaced review sessions before exams; (2) commit study time to tasks in priority
    order, accepting a task only while all accepted work still fits before each deadline; (3) lay the
    accepted work out earliest-deadline-first, which fits the most work before the deadlines.
    """
    start = now.replace(second=0, microsecond=0)
    start += dt.timedelta(minutes=(5 - start.minute % 5) % 5)  # round up to 5 minutes
    open_tasks = [t for t in tasks if t["deadline"] > start]
    if not open_tasks:
        return [], {}
    end = min(max(t["deadline"] for t in open_tasks), start + dt.timedelta(days=HORIZON_DAYS))

    # Spaced review sessions 7, 3 and 1 day(s) before each exam (FR-14) are reserved first, so that
    # study sessions cannot crowd them out. If the target day is full, the day before is tried.
    base_slots = build_free_slots(start, end, blocks, busy, kept)
    base_usage = {}
    for s, e in kept:
        base_usage[s.date()] = base_usage.get(s.date(), 0) + int((e - s).total_seconds() // 60)
    limit = int(daily_limit_hours * 60)
    reviews = []
    for task in sorted(open_tasks, key=lambda t: t["deadline"]):
        if task["task_type"] != "exam":
            continue
        for offset in REVIEW_OFFSETS:
            target = task["deadline"].date() - dt.timedelta(days=offset)
            for day in (target, target - dt.timedelta(days=1)):
                if day < start.date():
                    continue
                slot = find_slot(base_slots, session_length, task["deadline"], base_usage, limit, on_day=day)
                if slot:
                    reviews.append({"task_id": task["task_id"], "start": slot,
                                    "end": take(base_slots, slot, session_length, base_usage),
                                    "session_type": "review", "review_offset_days": offset})
                    break

    ranked = rank_tasks(open_tasks, now)
    order = {t["task_id"]: i for i, t in enumerate(ranked)}

    def place(amounts):
        """Lay out the given minutes per task, earliest deadline first (ties: higher priority).
        Returns (sessions, slots, usage, shortfall_by_task)."""
        slots, usage, out, short = list(base_slots), dict(base_usage), [], {}
        for task in sorted((t for t in ranked if amounts.get(t["task_id"], 0) > 0),
                           key=lambda t: (t["deadline"], order[t["task_id"]])):
            left = amounts[task["task_id"]]
            while left > 0:
                chunk = max(min(session_length, left), MIN_SESSION)
                slot = find_slot(slots, chunk, task["deadline"], usage, limit)
                if slot is None:
                    break
                out.append({"task_id": task["task_id"], "start": slot, "end": take(slots, slot, chunk, usage),
                            "session_type": "study", "review_offset_days": None})
                left -= chunk
            if left > 0:
                short[task["task_id"]] = left
        return out, slots, usage, short

    # Commit time to tasks in priority order (FR-13): a task is accepted only if every task accepted
    # before it still fits before its own deadline. If it does not fit in full, it gets as much time as
    # fits and the rest is reported as a shortfall (FR-15).
    accepted, at_risk = {}, {}
    for task in ranked:
        tid, need = task["task_id"], int(task.get("remaining_minutes", 0))
        if need <= 0:
            continue
        amount = need
        while amount > 0:
            if not place({**accepted, tid: amount})[3]:
                break
            amount = amount - MIN_SESSION if amount > MIN_SESSION else 0
        if amount > 0:
            accepted[tid] = amount
        if amount < need:
            at_risk[tid] = round((need - amount) / 60, 1)

    sessions = place(accepted)[0] + reviews

    sessions.sort(key=lambda x: x["start"])
    return sessions, at_risk
