"""RescheduleController logic (UC-09, FR-18 to FR-20). Pure functions, no database access."""
import datetime as dt

from .scheduler import MIN_SESSION, find_slot, take


def reschedule_missed(duration_min, slots, deadline, usage, daily_limit_min):
    """Decide what to do with a missed session.

    Returns one of:
      {'action': 'moved', 'start', 'end'}
      {'action': 'split', 'parts': [(start, end), (start, end)]}
      {'action': 'none'}   -> the student is told there is no free slot (FR-20)
    """
    slot = find_slot(slots, duration_min, deadline, usage, daily_limit_min)
    if slot:
        return {"action": "moved", "start": slot, "end": take(slots, slot, duration_min, usage)}

    first = (duration_min + 1) // 2
    second = duration_min - first
    if second >= MIN_SESSION:
        # Work on copies so nothing is reserved unless both parts fit.
        trial_slots, trial_usage = list(slots), dict(usage)
        s1 = find_slot(trial_slots, first, deadline, trial_usage, daily_limit_min)
        if s1:
            e1 = take(trial_slots, s1, first, trial_usage)
            s2 = find_slot(trial_slots, second, deadline, trial_usage, daily_limit_min)
            if s2:
                e2 = take(trial_slots, s2, second, trial_usage)
                slots[:] = trial_slots
                usage.clear()
                usage.update(trial_usage)
                return {"action": "split", "parts": [(s1, e1), (s2, e2)]}
    return {"action": "none"}


def is_unmarked(session, now, timeout_hours=2):
    """FR-18: a planned session with no status 2 hours after its planned end counts as missed."""
    return (session["status"] in ("planned", "rescheduled")
            and session["planned_end"] + dt.timedelta(hours=timeout_hours) <= now)
