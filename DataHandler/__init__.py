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