import json
import os


class DataHandler:
    def __init__(self):
        self.DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "habit_data.json")

    def load_data(self):
        try:
            with open(self.DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {"habits": []}

    def save_data(self, data):
        with open(self.DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

# ================= Инвестиционный портфель =================

INVESTMENTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "investments.json")


def load_portfolio():
    """Загрузить портфель: {"positions": [{ticker, qty, buy_price, buy_date}]}."""
    if not os.path.exists(INVESTMENTS_FILE):
        return {"positions": []}
    try:
        with open(INVESTMENTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        data = {"positions": []}
    data.setdefault("positions", [])
    return data


def save_portfolio(data):
    """Сохранить портфель в investments.json (в папке DataHandler)."""
    with open(INVESTMENTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ================= Кэш среднегодовой доходности активов =================
# Файл returns_cache.json лежит рядом с investments.json и хранит
# уже посчитанные доходности инструментов, чтобы не пересчитывать
# их с нуля при каждом открытии окна. Новые активы добавляются
# в файл автоматически после первого расчёта.

RETURNS_CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "returns_cache.json")


def load_returns_cache():
    """Кэш доходностей: {ticker: {"cagr": %, "updated": "ГГГГ-ММ-ДД", "years": N}}."""
    if not os.path.exists(RETURNS_CACHE_FILE):
        return {}
    try:
        with open(RETURNS_CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def save_returns_cache(cache):
    """Сохранить кэш доходностей в returns_cache.json (в папке DataHandler)."""
    with open(RETURNS_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)