"""Date and time helpers. All times in the prototype are stored as 'YYYY-MM-DD HH:MM:SS'."""
import datetime as dt

FMT = "%Y-%m-%d %H:%M:%S"


def parse(value):
    if value is None or isinstance(value, dt.datetime):
        return value
    value = str(value).replace("T", " ")
    if len(value) == 16:
        value += ":00"
    if len(value) == 10:
        value += " 00:00:00"
    return dt.datetime.strptime(value[:19], FMT)


def fmt(value):
    return value.strftime(FMT) if value else None


def parse_time(value):
    """'HH:MM' or 'HH:MM:SS' -> datetime.time"""
    parts = [int(p) for p in str(value).split(":")]
    while len(parts) < 3:
        parts.append(0)
    return dt.time(parts[0], parts[1], parts[2])


def week_start(day):
    """Monday of the week that contains day."""
    if isinstance(day, dt.datetime):
        day = day.date()
    return day - dt.timedelta(days=day.weekday())


def now():
    return dt.datetime.now().replace(microsecond=0)
