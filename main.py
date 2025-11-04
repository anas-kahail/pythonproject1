"""Study Organizer (simple edition)

Core features only: subjects, tasks, spaced-repetition reviews, logging,
report, today summary, and clear. Plain-text storage, stdlib only.
"""

from __future__ import annotations

import os
import sys
from datetime import date, datetime, timedelta


# Data files
SUBJECTS_FILE = "subjects.txt"
TASKS_FILE = "tasks.txt"
REVIEWS_FILE = "reviews.txt"
SESSIONS_FILE = "sessions.txt"

STATUS_TODO = "todo"
STATUS_DOING = "doing"
STATUS_DONE = "done"


def _ensure_files() -> None:
    for p in (SUBJECTS_FILE, TASKS_FILE, REVIEWS_FILE, SESSIONS_FILE):
        if not os.path.exists(p):
            open(p, "a", encoding="utf-8").close()


def _read(path: str) -> list[str]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return [ln.rstrip("\n") for ln in f]
    except FileNotFoundError:
        return []


def _write(path: str, lines: list[str]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + ("\n" if lines else ""))


def _append(path: str, line: str) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")


# --------------------- Subjects ---------------------

def subjects_list() -> list[str]:
    return [s.strip() for s in _read(SUBJECTS_FILE) if s.strip()]


def cmd_add_subject(name: str) -> None:
    name = name.strip()
    if not name:
        print("Subject name cannot be empty.")
        return
    if name.lower() in {s.lower() for s in subjects_list()}:
        print(f"Subject already exists: {name}")
        return
    _append(SUBJECTS_FILE, name)
    print(f"Added subject: {name}")


def cmd_list_subjects() -> None:
    subs = subjects_list()
    if not subs:
        print("No subjects. Use: add-subject <name>")
        return
    tasks = tasks_list()
    stats: dict[str, tuple[int, int]] = {}
    for t in tasks:
        total, done = stats.get(t["subject"], (0, 0))
        total += 1
        if t["status"] == STATUS_DONE:
            done += 1
        stats[t["subject"]] = (total, done)
    for i, s in enumerate(subs, 1):
        total, done = stats.get(s, (0, 0))
        pct = int(round((done / total) * 100)) if total else 0
        print(f"{i}. {s} — {done}/{total} done ({pct}%)")


# --------------------- Tasks ---------------------

def _parse_task(line: str) -> dict[str, str] | None:
    parts = [p.strip() for p in line.split("|")]
    if len(parts) != 4:
        return None
    return {"id": parts[0], "subject": parts[1], "title": parts[2], "status": parts[3]}


def tasks_list() -> list[dict[str, str]]:
    tasks: list[dict[str, str]] = []
    for ln in _read(TASKS_FILE):
        t = _parse_task(ln)
        if t:
            tasks.append(t)
    return tasks


def _save_tasks(tasks: list[dict[str, str]]) -> None:
    _write(TASKS_FILE, ["|".join([t["id"], t["subject"], t["title"], t["status"]]) for t in tasks])


def cmd_add_task(subject: str, title: str) -> None:
    subject = subject.strip()
    title = title.strip()
    if not subject or not title:
        print("Usage: add-task <subject> <title>")
        return
    if subject.lower() not in {s.lower() for s in subjects_list()}:
        _append(SUBJECTS_FILE, subject)
    tasks = tasks_list()
    next_id = (max([int(t["id"]) for t in tasks]) + 1) if tasks else 1
    task = {"id": str(next_id), "subject": subject, "title": title, "status": STATUS_TODO}
    tasks.append(task)
    _save_tasks(tasks)
    upsert_review(next_id, 1, date.today(), 2.5)
    print(f"Added task #{next_id}: [{subject}] {title}")


def cmd_list_tasks(subject: str | None, status: str | None) -> None:
    tasks = tasks_list()
    if subject:
        tasks = [t for t in tasks if t["subject"].lower() == subject.lower()]
    if status:
        tasks = [t for t in tasks if t["status"].lower() == status.lower()]
    if not tasks:
        print("No matching tasks.")
        return
    due_map = {tid: d.isoformat() for tid, _i, d, _e in load_reviews()}
    _table(
        ("ID", "Status", "Subject", "Title", "Due", "Flag"),
        [
            (
                t["id"],
                t["status"],
                t["subject"],
                t["title"],
                due_map.get(int(t["id"]), "-"),
                _overdue_flag(due_map.get(int(t["id"])) if t["status"] != STATUS_DONE else None),
            )
            for t in tasks
        ],
    )


def cmd_update_status(task_id: int, new_status: str) -> None:
    tasks = tasks_list()
    for t in tasks:
        if int(t["id"]) == task_id:
            t["status"] = new_status
            _save_tasks(tasks)
            print(f"Task #{task_id} [{t['subject']}] '{t['title']}' -> {new_status}")
            return
    print(f"Task not found: {task_id}")


# --------------------- Reviews ---------------------

def _parse_review(line: str):
    p = [x.strip() for x in line.split("|")]
    if len(p) != 4:
        return None
    try:
        return int(p[0]), int(p[1]), datetime.strptime(p[2], "%Y-%m-%d").date(), float(p[3])
    except Exception:
        return None


def load_reviews() -> list[tuple[int, int, date, float]]:
    out: list[tuple[int, int, date, float]] = []
    for ln in _read(REVIEWS_FILE):
        r = _parse_review(ln)
        if r:
            out.append(r)
    return out


def _save_reviews(reviews: list[tuple[int, int, date, float]]) -> None:
    _write(REVIEWS_FILE, [f"{tid}|{i}|{d.isoformat()}|{e:.2f}" for tid, i, d, e in reviews])


def upsert_review(task_id: int, interval_days: int, due: date, ease: float) -> None:
    reviews = load_reviews()
    for i, r in enumerate(reviews):
        if r[0] == task_id:
            reviews[i] = (task_id, interval_days, due, ease)
            _save_reviews(reviews)
            return
    reviews.append((task_id, interval_days, due, ease))
    _save_reviews(reviews)


def _update_ease(ease: float, quality: int) -> float:
    delta = 0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)
    return max(1.3, ease + delta)


def cmd_review(task_id: int, quality: int) -> None:
    reviews = load_reviews()
    today = date.today()
    existing = next((r for r in reviews if r[0] == task_id), None)
    interval, ease = (1, 2.5) if existing is None else (existing[1], existing[3])
    ease = _update_ease(ease, quality)
    if quality < 3:
        interval = 1
    else:
        interval = 6 if interval in (0, 1) else max(1, int(round(interval * ease)))
    due = today + timedelta(days=interval)
    upsert_review(task_id, interval, due, ease)
    print(f"Next review for #{task_id} in {interval} day(s), due {due.isoformat()}")


def _overdue_flag(due_str: str | None) -> str:
    if not due_str:
        return ""
    try:
        return "OVERDUE" if datetime.strptime(due_str, "%Y-%m-%d").date() < date.today() else ""
    except ValueError:
        return ""


def cmd_review_due(on: date | None) -> None:
    on = on or date.today()
    items = [r for r in load_reviews() if r[2] <= on]
    if not items:
        all_r = load_reviews()
        if all_r:
            nxt = min(all_r, key=lambda r: r[2])[2]
            print(f"No reviews due. Next due on {nxt.isoformat()}.")
        else:
            print("No reviews scheduled yet.")
        return
    tasks = {int(t["id"]): t for t in tasks_list()}
    _table(
        ("ID", "Due", "Int", "Ease", "Subject", "Title", "Flag"),
        [
            (
                str(tid), d.isoformat(), str(i), f"{e:.2f}",
                (tasks.get(tid) or {}).get("subject", "?"),
                (tasks.get(tid) or {}).get("title", "<missing>"),
                "OVERDUE" if d < date.today() else "DUE",
            )
            for tid, i, d, e in sorted(items, key=lambda r: (r[2], r[0]))
        ],
    )


# --------------------- Logging & Reports ---------------------

def cmd_log(subject: str, task_id: int, minutes: int, notes: str) -> None:
    today = date.today().isoformat()
    _append(SESSIONS_FILE, f"{today}|{subject}|{task_id}|{minutes}|{notes}")
    total = 0
    for ln in _read(SESSIONS_FILE):
        p = ln.split("|")
        if len(p) >= 4 and p[0] == today and p[1] == subject:
            try:
                total += int(p[3])
            except ValueError:
                pass
    print(f"Logged {minutes} min for task #{task_id} [{subject}]. Today total for {subject}: {total} min.")


def cmd_report(days: int | None) -> None:
    cutoff = date.today() - timedelta(days=days) if days and days > 0 else None
    totals: dict[str, int] = {}
    for ln in _read(SESSIONS_FILE):
        p = ln.split("|")
        if len(p) < 4:
            continue
        try:
            d = datetime.strptime(p[0], "%Y-%m-%d").date()
            if cutoff and d < cutoff:
                continue
            totals[p[1]] = totals.get(p[1], 0) + int(p[3])
        except Exception:
            continue
    if not totals:
        print("No study sessions logged.")
        return
    _table(("Subject", "Minutes"), [(s, str(m)) for s, m in sorted(totals.items(), key=lambda kv: (-kv[1], kv[0]))])
    print(f"Total: {sum(totals.values())} min")


def cmd_today() -> None:
    today_dt = date.today()
    print("Reviews due today:")
    reviews = [r for r in load_reviews() if r[2] == today_dt]
    if reviews:
        tasks = {int(t["id"]): t for t in tasks_list()}
        _table(
            ("ID", "Subject", "Title", "Due"),
            [
                (str(tid), tasks.get(tid, {}).get("subject", "?"), tasks.get(tid, {}).get("title", "<missing>"), d.isoformat())
                for tid, _i, d, _e in sorted(reviews, key=lambda r: r[0])
            ],
        )
    else:
        print("  None due today.")

    print("\nMinutes studied today:")
    totals: dict[str, int] = {}
    for ln in _read(SESSIONS_FILE):
        p = ln.split("|")
        if len(p) < 4:
            continue
        try:
            if datetime.strptime(p[0], "%Y-%m-%d").date() != today_dt:
                continue
            totals[p[1]] = totals.get(p[1], 0) + int(p[3])
        except Exception:
            continue
    if totals:
        _table(("Subject", "Minutes"), [(s, str(m)) for s, m in sorted(totals.items(), key=lambda kv: (-kv[1], kv[0]))])
        print(f"Total today: {sum(totals.values())} min")
    else:
        print("  No study logged today.")


# --------------------- Utilities ---------------------

def _table(headers: tuple[str, ...], rows: list[tuple[str, ...]]) -> None:
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    line = " | ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    sep = "-+-".join("-" * w for w in widths)
    print(line)
    print(sep)
    for row in rows:
        print(" | ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)))


def cmd_clear(target: str) -> None:
    mapping = {
        "subjects": SUBJECTS_FILE,
        "tasks": TASKS_FILE,
        "reviews": REVIEWS_FILE,
        "sessions": SESSIONS_FILE,
    }
    if target == "all":
        for p in mapping.values():
            _write(p, [])
        print("Cleared all data files.")
        return
    path = mapping.get(target)
    if not path:
        print("Usage: clear <all|sessions|tasks|reviews|subjects>")
        return
    _write(path, [])
    print(f"Cleared {target}.")


# --------------------- CLI ---------------------

def _usage() -> None:
    for c in (
        "add-subject <name>",
        "list-subjects",
        "add-task <subject> <title>",
        "list-tasks [--subject <name>] [--status <todo|doing|done>]",
        "start <task_id>",
        "done <task_id>",
        "review-due [--on YYYY-MM-DD]",
        "review <task_id> <quality 0-5>",
        "log <subject> <task_id> <minutes> [notes...]",
        "report [--days N]",
        "today",
        "clear <all|sessions|tasks|reviews|subjects>",
    ):
        print(c)


def main(argv: list[str]) -> int:
    _ensure_files()
    if not argv:
        _usage()
        return 0
    cmd = argv[0]

    if cmd == "add-subject" and len(argv) >= 2:
        cmd_add_subject(" ".join(argv[1:]))
        return 0
    if cmd == "list-subjects":
        cmd_list_subjects()
        return 0
    if cmd == "add-task" and len(argv) >= 3:
        cmd_add_task(argv[1], " ".join(argv[2:]))
        return 0
    if cmd == "list-tasks":
        subj = None
        status = None
        it = iter(argv[1:])
        for t in it:
            if t == "--subject":
                subj = next(it, None)
            elif t == "--status":
                status = next(it, None)
        cmd_list_tasks(subj, status)
        return 0
    if cmd == "start" and len(argv) == 2:
        cmd_update_status(int(argv[1]), STATUS_DOING)
        return 0
    if cmd == "done" and len(argv) == 2:
        tid = int(argv[1])
        cmd_update_status(tid, STATUS_DONE)
        cmd_review(tid, 4)
        return 0
    if cmd == "review-due":
        on = None
        if len(argv) >= 3 and argv[1] == "--on":
            try:
                on = datetime.strptime(argv[2], "%Y-%m-%d").date()
            except ValueError:
                print("Invalid date. Use YYYY-MM-DD.")
                return 1
        cmd_review_due(on)
        return 0
    if cmd == "review" and len(argv) == 3:
        try:
            cmd_review(int(argv[1]), int(argv[2]))
        except ValueError:
            print("Usage: review <task_id> <quality 0-5>")
            return 1
        return 0
    if cmd == "log" and len(argv) >= 5:
        try:
            cmd_log(argv[1], int(argv[2]), int(argv[3]), " ".join(argv[4:]))
        except ValueError:
            print("Usage: log <subject> <task_id> <minutes> [notes...]")
            return 1
        return 0
    if cmd == "report":
        d = None
        if len(argv) == 3 and argv[1] == "--days":
            try:
                d = int(argv[2])
            except ValueError:
                print("--days must be an integer.")
                return 1
        cmd_report(d)
        return 0
    if cmd == "today":
        cmd_today()
        return 0
    if cmd == "clear" and len(argv) == 2:
        cmd_clear(argv[1])
        return 0

    _usage()
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))


