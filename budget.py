import datetime as dt
import json
import os

# budget.json лежит в папке DataHandler рядом с investments.json,
# поэтому путь строим от расположения самого budget.py
BUDGET_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "DataHandler", "budget.json")


def load_budget():
    """Загрузить модуль доходов/расходов.
    {"created": "YYYY-MM-DD",             # дата создания модуля
     "start": "YYYY-MM-DD",               # с какого месяца показывать
                                           # календарь (двигается назад
                                           # кнопкой «‹ добавить месяц»)
     "items": [{"name": str, "plan": ₽,  # статьи с планом на месяц;
                "optional": bool}],  # True — необязательные: не
                                     # влияют на закрытие месяца
     "months": {"YYYY-MM": {"income_10": ₽,    # аванс 10-го
                            "income_25": ₽,    # остаток зп 25-го
                            "expenses": [{"item": str, "amount": ₽,
                                          "date": "YYYY-MM-DD"}],
                            "oneoff": [{"name": str, "amount": ₽,
                                        "date": "YYYY-MM-DD"}]}}}"""
    data = {"created": dt.date.today().isoformat(),
            "items": [], "months": {}}
    if not os.path.exists(BUDGET_FILE):
        return data
    try:
        with open(BUDGET_FILE, "r", encoding="utf-8") as f:
            loaded = json.load(f)
    except (json.JSONDecodeError, OSError):
        return data
    data.update(loaded)
    data.setdefault("items", [])
    data.setdefault("months", {})
    if not data.get("created"):
        data["created"] = dt.date.today().isoformat()
    # блок «обязательные траты» удалён (статьи с планом и так
    # обязательные): переносим их в статьи, план = прежняя сумма,
    # а оплаченные в месяцах отметки — в траты по этим статьям
    required = data.pop("required", None)
    if required:
        for r in required:
            if not any(i["name"] == r["name"] for i in data["items"]):
                data["items"].append(
                    {"name": r["name"], "plan": r.get("amount") or 0})
        for key, m in data.get("months", {}).items():
            for name in m.pop("paid", None) or []:
                if not any(e["item"] == name
                           for e in m.get("expenses", [])):
                    m.setdefault("expenses", []).append(
                        {"item": name,
                         "amount": next((r["amount"] for r in required
                                         if r["name"] == name), 0),
                         "date": f"{key}-28"})
    return data


def save_budget(data):
    with open(BUDGET_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def month_key(year, month):
    return f"{year:04d}-{month:02d}"


def first_month(data):
    """Первый месяц календаря: "start", если расширяли назад
    (например, добавляли октябрь), иначе месяц создания модуля."""
    if data.get("start"):
        d = dt.date.fromisoformat(data["start"])
        return (d.year, d.month)
    created = dt.date.fromisoformat(data["created"])
    return (created.year, created.month)


def add_month_back(data):
    """Расширить календарь на месяц назад и вернуть ключ нового
    месяца (например, чтобы заполнить прошлый месяц)."""
    y, m = first_month(data)
    m -= 1
    if m < 1:
        y, m = y - 1, 12
    data["start"] = dt.date(y, m, 1).isoformat()
    return month_key(y, m)


def month_list(data):
    """Все месяцы от начала (start/created) до текущего включительно."""
    y, m = first_month(data)
    today = dt.date.today()
    out = []
    while (y, m) <= (today.year, today.month):
        out.append((y, m))
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


def month_data(data, key):
    """Данные месяца (создаётся пустой словарь при первом обращении).
    Старый формат с одним полем "income" переносим в "income_25":
    зп раньше приходила одной суммой, теперь делится на аванс 10-го
    и остаток 25-го (расчётный лист приходит 9-го)."""
    m = data["months"].setdefault(key, {})
    m.setdefault("income_10", 0)
    m.setdefault("income_25", 0)
    m.setdefault("expenses", [])
    m.setdefault("oneoff", [])
    if m.get("income") and not m.get("income_25"):
        m["income_25"] = m["income"]
    m.pop("income", None)
    return m


def income_total(mdata):
    """Весь доход месяца: аванс 10-го + остаток зп 25-го."""
    return (mdata.get("income_10") or 0) + (mdata.get("income_25") or 0)


def item_spent(mdata, item_name):
    """Сколько потрачено по статье с планом за месяц."""
    return sum(e["amount"] for e in mdata["expenses"]
               if e["item"] == item_name)


def item_done(mdata, item):
    """Статья закрыта: потрачено не меньше плана. Без плана (0 ₽)
    статья не может быть закрытой — план задаётся обязательно."""
    plan = item.get("plan") or 0
    return plan > 0 and item_spent(mdata, item["name"]) >= plan


def optional_plan(data, item, key):
    """Эффективный план необязательной статьи в месяце key с учётом
    переноса превышения: перерасход месяца вычитается из плана
    следующего. Идём цепочкой от начала календаря, потому что
    превышать (и переносить остаток) могут несколько месяцев
    подряд. Возвращает эффективный план в ₽."""
    plan = item.get("plan") or 0
    over = 0.0
    for y, m in month_list(data):
        k = month_key(y, m)
        eff = max(0.0, plan - over)
        if k == key:
            return eff
        md = data["months"].get(k)
        spent = item_spent(md, item["name"]) if md else 0.0
        over = max(0.0, spent - eff)
    return max(0.0, plan)


def optional_carry(data, item, key):
    """Сколько перенесено в месяц key с прошлого месяца (₽) —
    превышение прошлого месяца по этой же статье."""
    plan = item.get("plan") or 0
    y, m = int(key[:4]), int(key[5:])
    m -= 1
    if m < 1:
        y, m = y - 1, 12
    prev_key = month_key(y, m)
    prev = data["months"].get(prev_key)
    if not prev:
        return 0.0
    eff_prev = optional_plan(data, item, prev_key)
    return max(0.0, item_spent(prev, item["name"]) - eff_prev)


def oneoff_total(mdata):
    """Сумма разовых трат месяца (актуальны только в этом месяце)."""
    return sum(o["amount"] for o in mdata["oneoff"])


def month_spent(data, mdata):
    """Все траты месяца: по статьям с планом + разовые."""
    return (sum(e["amount"] for e in mdata["expenses"])
            + oneoff_total(mdata))


def free_money(data, mdata):
    """Остаток: весь доход месяца (аванс + зп) минус все траты."""
    return income_total(mdata) - month_spent(data, mdata)


def month_done(data, key):
    """Месяц выполнен полностью: есть обязательные статьи с планом
    и все они закрыты. Необязательные статьи (optional=True) на
    закрытие месяца не влияют — это траты по желанию."""
    mdata = data["months"].get(key)
    if not mdata:
        return False
    must = [i for i in data["items"] if not i.get("optional")]
    if not must:
        return False
    return all(item_done(mdata, i) for i in must)