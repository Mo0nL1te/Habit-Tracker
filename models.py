# models.py — чистая логика: серии, условия, автозакраска дней

import datetime as dt


def longest_streak(dates):
    """Самая длинная серия подряд идущих отмеченных дней."""
    days = sorted(dt.date.fromisoformat(d) for d in dates)
    best = cur = 0
    prev = None
    for d in days:
        cur = cur + 1 if prev is not None and (d - prev).days == 1 else 1
        best = max(best, cur)
        prev = d
    return best


def get_condition(habit):
    """Вернуть условие привычки; старый строковый формат конвертируется."""
    cond = habit.get("condition")
    if cond is None:
        cond = {"type": "text", "text": "", "items": [], "cells": []}
    elif isinstance(cond, str):  # миграция со старой версии (просто текст)
        cond = {"type": "text", "text": cond, "items": [], "cells": []}
    cond.setdefault("type", "text")
    cond.setdefault("text", "")
    cond.setdefault("items", [])
    cond.setdefault("cells", [])
    cond.setdefault("goal", 0)  # целевой вес за сутки для таблицы
    return cond


def get_created_date(habit):
    """Дата создания карточки; для старых привычек — самая ранняя отметка."""
    created_iso = habit.get("created")
    if created_iso:
        return dt.date.fromisoformat(created_iso)
    if habit["dates"]:
        return dt.date.fromisoformat(min(habit["dates"]))
    return None


def compute_auto_green_days(habit, year, month, save):
    """Дни месяца (year, month), выполненные по таблице квадратиков.

    Правила:
    - любой день с накопленным весом >= цели закрашивается сам;
    - излишек сверх цели (для любого дня) переносится назад:
      вес >= цель*2 — закрашивается ещё и ближайший незаполненный
      предыдущий день, >= цель*3 — два предыдущих, и т.д.

    Прошедшие сутки «фиксируются»: автозакрытые дни переносятся в
    habit["dates"] (как ручная отметка), квадратики получают locked=True.
    save — колбэк, который записывает данные на диск после фиксации.
    """
    cond = habit.get("condition")
    if not isinstance(cond, dict) or cond.get("type") != "table":
        return set()
    goal = cond.get("goal", 0)
    if goal <= 0:
        return set()

    per_day = {}  # "YYYY-MM-DD" -> суммарный вес
    for cell in cond.get("cells", []):
        if cell.get("done") and cell.get("date") and not cell.get("locked"):
            per_day[cell["date"]] = per_day.get(cell["date"], 0) + cell.get("weight", 1)

    green = set()  # строки "YYYY-MM-DD"

    # 1) каждый день, набравший цель, закрашивается сам
    for day, weight in per_day.items():
        if weight >= goal:
            green.add(day)

    # 2) перенос излишка на предыдущие сутки — для каждого дня, набравшего цель
    manual = set(habit["dates"])  # вручную заполненные не трогаем
    # граница переноса: дата создания привычки, а если её нет —
    # самая ранняя отметка или 30 дней назад
    floor_iso = habit.get("created") or (
        min(habit["dates"]) if habit["dates"]
        else (dt.date.today() - dt.timedelta(days=30)).isoformat()
    )
    # обрабатываем дни от свежих к старым, чтобы излишек более
    # позднего дня не «перепрыгивал» через закрытые более старые
    for day in sorted(per_day, reverse=True):
        if per_day[day] < goal:
            continue
        extra_days = (per_day[day] - goal) // goal  # сколько суток ещё закрыто
        cur = dt.date.fromisoformat(day)
        prev = cur - dt.timedelta(days=1)
        while extra_days > 0 and prev.isoformat() >= floor_iso:
            prev_iso = prev.isoformat()
            if prev_iso not in manual and prev_iso not in green:
                green.add(prev_iso)
                extra_days -= 1
            prev -= dt.timedelta(days=1)

    # 3) фиксация прошедших суток: автозакрытые дни до вчерашнего включительно
    #    переносятся в dates — больше не пересчитываются и выглядят как ручная отметка
    yesterday_iso = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    to_fix = [d for d in green if d <= yesterday_iso and d not in manual]
    if to_fix:
        habit["dates"].extend(to_fix)
        # выполненные квадратики прошедших дней фиксируются: их вес
        # больше не влияет на расчёт (защита от переделки)
        for cell in cond["cells"]:
            if cell.get("done") and cell.get("date") in to_fix:
                cell["locked"] = True
        save()

    # фильтруем по отображаемому месяцу
    return {
        dt.date.fromisoformat(d)
        for d in green
        if dt.date.fromisoformat(d).month == month
        and dt.date.fromisoformat(d).year == year
    }