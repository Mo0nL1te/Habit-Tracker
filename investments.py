# investments.py — данные портфеля, котировки MOEX (акции, ETF, облигации/ОФЗ)

import datetime as dt
import json
import re
import urllib.parse
import urllib.request

# Хранение портфеля (чтение/запись investments.json) перенесено
# в пакет DataHandler — файл данных лежит в папке с данными.
# Реэкспортируем, чтобы вызовы inv.load_portfolio()/inv.save_portfolio()
# в интерфейсе работали без изменений.
from DataHandler import (load_portfolio, save_portfolio,
                         load_returns_cache, save_returns_cache)

BOND_LIST_CACHE = None   # кэш списка облигаций (запасной путь поиска)

# площадки БПИФ/ETF на MOEX: TQTF — фонды, TQIF — иностранные, TQFD — прочие
FUND_BOARDS = ("TQTF", "TQIF", "TQFD")
# слова в названии бумаги, по которым распознаём фонды (SBSC, TGLD,
# AKMP, TMOS и другие БПИФ: «...ФОНД...», «... ETF», «БПИФ»)
FUND_NAME_HINTS = ("ФОНД", "ETF", "БПИФ")
FUND_LIST_CACHE = None   # кэш списка всех инструментов этих площадок


# ---- хранение ----
# load_portfolio / save_portfolio находятся в DataHandler/__init__.py;
# сюда они импортированы выше.


def add_position(data, ticker, qty, buy_price):
    """Добавить позицию; если тикер уже есть — усредняем цену и складываем количество."""
    for pos in data["positions"]:
        if pos["ticker"] == ticker:
            total_qty = pos["qty"] + qty
            pos["buy_price"] = round(
                (pos["buy_price"] * pos["qty"] + buy_price * qty) / total_qty, 4)
            pos["qty"] = total_qty
            return pos
    pos = {"ticker": ticker, "qty": qty, "buy_price": buy_price,
           "buy_date": dt.date.today().isoformat()}
    data["positions"].append(pos)
    return pos


def delete_position(data, ticker):
    data["positions"] = [p for p in data["positions"] if p["ticker"] != ticker]


# ---- запросы к MOEX ISS (без ключей и библиотек) ----
def _iss_json(url):
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (habit-tracker)"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def _search_securities(query):
    """Поиск инструментов MOEX по подстроке (коду или названию).

    Быстрый эндпоинт: https://iss.moex.com/iss/securities.json?q=...
    """
    url = ("https://iss.moex.com/iss/securities.json?q="
           + urllib.parse.quote(query)
           + "&iss.meta=off&iss.only=securities")
    data = _iss_json(url)
    cols = data["securities"]["columns"]
    return [dict(zip(cols, r)) for r in data["securities"]["data"]]


def _find_board(secid):
    """Найти торговую площадку инструмента (акции, ETF, облигации и пр.)."""
    url = (f"https://iss.moex.com/iss/securities/{urllib.parse.quote(secid)}.json"
           f"?iss.meta=off&iss.only=boards")
    data = _iss_json(url)
    columns = data["boards"]["columns"]
    best = None
    for row in data["boards"]["data"]:
        b = dict(zip(columns, row))
        if b.get("is_traded") and b.get("engine") == "stock":
            if best is None or (b.get("is_primary") and not best.get("is_primary")):
                best = b
    return best


def _bond_list():
    """Полный список облигаций MOEX (кэшируется; запасной путь поиска)."""
    global BOND_LIST_CACHE
    if BOND_LIST_CACHE is None:
        url = ("https://iss.moex.com/iss/engines/stock/markets/bonds/securities.json"
               "?iss.meta=off&iss.only=securities")
        data = _iss_json(url)
        cols = data["securities"]["columns"]
        BOND_LIST_CACHE = [dict(zip(cols, r)) for r in data["securities"]["data"]]
    return BOND_LIST_CACHE


def resolve_ticker(user_input):
    """Разобрать пользовательский ввод в код инструмента MOEX.

    Понимает:
    - прямой код: SBER, SU26245RMFS4;
    - облигации по номеру выпуска: «OFZ-PD 26245», «ОФЗ 26245», «26245»;
      поиск идёт через быстрый search-эндпоинт ISS, при неудаче —
      по полному списку облигаций.
    Возвращает secid или None.
    """
    text = user_input.strip().upper()
    if not text:
        return None
    # 1) пробуем как прямой код инструмента
    try:
        if _find_board(text) is not None:
            return text
    except Exception:
        pass
    # 2) облигация по номеру выпуска
    m = re.search(r'(\d{4,6})', text)
    if not m:
        return None
    num = m.group(1)
    candidates = []
    for query in (num, "SU" + num):   # поиск по номеру и по префиксу кода ОФЗ
        try:
            candidates = _search_securities(query)
        except Exception:
            candidates = []
        if candidates:
            break
    # сначала ищем точное совпадение по ОФЗ
    for sec in candidates:
        name = (sec.get("name") or "").upper()
        if num in name or num in (sec.get("secid") or "").upper():
            if "ОФЗ" in name:
                return sec["secid"]
    # затем — любую облигацию с этим номером (корпоративные и пр.)
    for sec in candidates:
        name = (sec.get("name") or "").upper()
        secid = (sec.get("secid") or "").upper()
        if num in name or num in secid:
            return sec["secid"]
    # 3) запасной путь: полный список облигаций (медленный, кэшируется)
    try:
        for bond in _bond_list():
            name = (bond.get("name") or "").upper()
            if num in name and "ОФЗ" in name:
                return bond["secid"]
            if num in (bond.get("secid") or "").upper() \
                    and (bond.get("secid") or "").upper().startswith("SU"):
                return bond["secid"]
    except Exception:
        pass
    return None


def _all_boards(secid):
    """Все активные площадки инструмента на фондовом рынке MOEX."""
    url = (f"https://iss.moex.com/iss/securities/{urllib.parse.quote(secid)}.json"
           f"?iss.meta=off&iss.only=boards")
    data = _iss_json(url)
    columns = data["boards"]["columns"]
    rows = [dict(zip(columns, r)) for r in data["boards"]["data"]]
    return [b for b in rows if b.get("is_traded") and b.get("engine") == "stock"]


def _fund_set():
    """Множество кодов всех инструментов на фондовых площадках MOEX.

    Самый надёжный признак БПИФ/ETF: бумага торгуется на борде
    TQTF/TQIF/TQFD. Списки кэшируются при первом обращении.
    """
    global FUND_LIST_CACHE
    if FUND_LIST_CACHE is None:
        found = set()
        for board in FUND_BOARDS:
            try:
                url = ("https://iss.moex.com/iss/engines/stock/markets/shares"
                       f"/boards/{board}/securities.json"
                       "?iss.meta=off&iss.only=securities")
                data = _iss_json(url)
                cols = data["securities"]["columns"]
                for row in data["securities"]["data"]:
                    d = dict(zip(cols, row))
                    if d.get("SECID"):
                        found.add(d["SECID"])
            except Exception:
                pass
        FUND_LIST_CACHE = found
    return FUND_LIST_CACHE


def _looks_like_fund(secid):
    """Проверка по названию бумаги: БПИФ/ETF обычно содержат
    «фонд», «ETF» или «БПИФ» в названии (SBSC, TGLD, AKMP, TMOS...)."""
    try:
        for sec in _search_securities(secid):
            nm = ((sec.get("name") or "") + " "
                  + (sec.get("shortname") or "")).upper()
            if any(h in nm for h in FUND_NAME_HINTS):
                return True
    except Exception:
        pass
    return False


def _classify(boards, secid):
    """Вид актива: Акции / ETF/фонды / Облигации / Прочее.

    Порядок проверки важен: сначала членство в списках фондовых
    площадок, затем фондовый борд в площадках самого инструмента,
    затем рынок bonds; и только потом — эвристика по названию
    (облигации могут содержать «фонд» в названии эмитента, поэтому
    bonds проверяем раньше названия).
    """
    if secid and secid in _fund_set():
        return "ETF/фонды"
    if any(b.get("boardid") in FUND_BOARDS for b in boards):
        return "ETF/фонды"
    markets = {b.get("market") for b in boards}
    if "bonds" in markets:
        return "Облигации"
    if "shares" in markets:
        if secid and _looks_like_fund(secid):
            return "ETF/фонды"
        return "Акции"
    return "Прочее"


def get_quote(ticker):
    """Последняя цена инструмента на MOEX.

    Возвращает (price, updated_text, kind, facevalue):
    - price — цена (для облигаций — в % от номинала, как на бирже);
    - updated_text — момент обновления;
    - kind — вид актива (определяется по площадкам, даже если цену
      получить не удалось);
    - facevalue — номинал облигации (для акций None).
    (None, None, None, None), если инструмент не найден.
    """
    secid = resolve_ticker(ticker)
    if secid is None:
        return None, None, None, None
    kind = None
    facevalue = None
    try:
        boards = _all_boards(secid)
        if not boards:
            return None, None, None, None
        kind = _classify(boards, secid)
        # основная площадка — для запроса цены
        board = next((b for b in boards if b.get("is_primary")), boards[0])
        url = (f"https://iss.moex.com/iss/engines/{board['engine']}"
               f"/markets/{board['market']}/boards/{board['boardid']}"
               f"/securities/{secid}.json"
               f"?iss.meta=off&iss.only=marketdata,securities")
        data = _iss_json(url)
        md_row = data["marketdata"]["data"]
        sec_row = dict(zip(data["securities"]["columns"],
                           data["securities"]["data"][0])) \
            if data["securities"]["data"] else {}
        price = None
        if md_row:
            md = dict(zip(data["marketdata"]["columns"], md_row[0]))
            price = md.get("LAST") or md.get("MARKETPRICE") or md.get("LASTTOPREVPRICE")
        if price is None:
            price = sec_row.get("PREVPRICE")
        facevalue = sec_row.get("FACEVALUE")
        if kind == "Облигации" and not facevalue:
            facevalue = 1000   # стандартный номинал ОФЗ
        updated = dt.datetime.now().strftime("%H:%M:%S")
        if price is None:
            return None, updated, kind, facevalue
        return float(price), updated, kind, facevalue
    except Exception:
        # вид всё равно возвращаем, чтобы колонка «Вид» не была пустой
        return None, None, kind, facevalue


def refresh_positions(data):
    """Обновить цены всех позиций.

    Возвращает {"ticker": (price, updated, kind, facevalue)}; ошибки по
    одному тикеру не ломают обновление остальных.
    Если у позиции вручную задан вид (поле "kind" в investments.json),
    он используется вместо автоматического определения с биржи.
    """
    quotes = {}
    for pos in data["positions"]:
        price, updated, kind, facevalue = get_quote(pos["ticker"])
        if pos.get("kind"):
            kind = pos["kind"]
        quotes[pos["ticker"]] = (price, updated, kind, facevalue)
    return quotes


# ---- расчёты ----
RETURNS_CACHE_MAX_AGE = 7   # дней: раз в неделю кэш доходностей обновляется


def historical_annual_return(ticker, years=10):
    """Среднегодовая доходность инструмента (рост цены + дивиденды/купоны).

    Результат кэшируется в DataHandler/returns_cache.json и считается
    годным RETURNS_CACHE_MAX_AGE дней; активы, которых нет в кэше
    (новые), пересчитываются с нуля и автоматически добавляются в файл.
    """
    cache = load_returns_cache()
    entry = cache.get(ticker)
    if entry:
        try:
            updated = dt.date.fromisoformat(str(entry.get("updated", "")))
            if (entry.get("years") == years
                    and (dt.date.today() - updated).days <= RETURNS_CACHE_MAX_AGE):
                return entry.get("cagr")
        except (ValueError, TypeError):
            pass
    pct = _compute_annual_return(ticker, years)
    if pct is not None:
        cache[ticker] = {"cagr": pct,
                         "updated": dt.date.today().isoformat(),
                         "years": years}
        save_returns_cache(cache)
    return pct


def _candles_cagr(board, secid, years):
    """CAGR по дневным свечам за последние `years` лет."""
    date_from = (dt.date.today()
                 - dt.timedelta(days=int(365.25 * years) + 7)).isoformat()
    url = (f"https://iss.moex.com/iss/engines/{board['engine']}"
           f"/markets/{board['market']}/boards/{board['boardid']}"
           f"/securities/{secid}/candles.json"
           f"?iss.meta=off&iss.only=candles&interval=24&from={date_from}")
    data = _iss_json(url)
    rows = data["candles"]["data"]
    if len(rows) < 2:
        return None
    # свеча: open(0), close(1), high(2), low(3), value(4), volume(5),
    #        begin(6), end(7) — даты приходят строками, парсим их
    first, last = rows[0][1], rows[-1][1]
    if not first or not last:
        return None
    try:
        d1 = dt.datetime.strptime(str(rows[0][6])[:10], "%Y-%m-%d")
        d2 = dt.datetime.strptime(str(rows[-1][7])[:10], "%Y-%m-%d")
        days = (d2 - d1).days
    except (ValueError, TypeError):
        days = int(365.25 * years)   # запасной вариант
    if days < 30:
        return None
    return ((last / first) ** (365.25 / days) - 1) * 100


def _dividend_yield(secid, price):
    """Средняя годовая дивидендная доходность акции за 3 года, %.

    Сумма выплаченных дивидендов за последние ~3 года делится на 3
    и на текущую цену. Если данные ISS о дивидендах недоступны — 0.
    """
    if not price:
        return 0.0
    try:
        url = (f"https://iss.moex.com/iss/securities/{urllib.parse.quote(secid)}"
               f"/dividends.json?iss.meta=off&iss.only=dividends")
        data = _iss_json(url)
        cols = data["dividends"]["columns"]
        rows = [dict(zip(cols, r)) for r in data["dividends"]["data"]]
        cutoff = dt.date.today() - dt.timedelta(days=int(365.25 * 3) + 30)
        paid = 0.0
        for row in rows:
            try:
                d = dt.date.fromisoformat(
                    str(row.get("registryclosedate", ""))[:10])
            except ValueError:
                continue
            if d >= cutoff:
                paid += float(row.get("dividend") or 0)
        return round(paid / 3 / float(price) * 100, 2)
    except Exception:
        return 0.0


def _coupon_yield(sec_row, price):
    """Текущая купонная доходность облигации, % годовых.

    Годовой купон (COUPONVALUE × 365 / COUPONPERIOD) делим на цену
    облигации в деньгах (номинал × цена% / 100).
    """
    try:
        face = float(sec_row.get("FACEVALUE") or 1000)
        coupon = float(sec_row.get("COUPONVALUE") or 0)
        period = float(sec_row.get("COUPONPERIOD") or 182)
        if not coupon or not period:
            return 0.0
        money_price = face * float(price or 100.0) / 100
        annual_coupon = coupon * 365.0 / period
        return round(annual_coupon / money_price * 100, 2)
    except (TypeError, ValueError, ZeroDivisionError):
        return 0.0


def _compute_annual_return(ticker, years):
    """Полная среднегодовая доходность: рост цены + дивиденды/купоны."""
    secid = resolve_ticker(ticker)
    if secid is None:
        return None
    try:
        boards = _all_boards(secid)
        if not boards:
            return None
        board = next((b for b in boards if b.get("is_primary")), boards[0])
        kind = _classify(boards, secid)
        # текущие данные инструмента (цена + купонные параметры)
        price = None
        sec_row = {}
        try:
            url = (f"https://iss.moex.com/iss/engines/{board['engine']}"
                   f"/markets/{board['market']}/boards/{board['boardid']}"
                   f"/securities/{secid}.json"
                   f"?iss.meta=off&iss.only=marketdata,securities")
            data = _iss_json(url)
            if data["securities"]["data"]:
                sec_row = dict(zip(data["securities"]["columns"],
                                   data["securities"]["data"][0]))
            if data["marketdata"]["data"]:
                md = dict(zip(data["marketdata"]["columns"],
                              data["marketdata"]["data"][0]))
                price = (md.get("LAST") or md.get("MARKETPRICE")
                         or md.get("LASTTOPREVPRICE"))
            if price is None:
                price = sec_row.get("PREVPRICE")
        except Exception:
            pass
        cagr = _candles_cagr(board, secid, years)
        supplement = 0.0
        if kind == "Облигации":
            supplement = _coupon_yield(sec_row, price)
        elif kind == "Акции":
            supplement = _dividend_yield(secid, price)
        if cagr is None:
            # истории нет (молодой инструмент) — только дивиденды/купон
            return round(supplement, 2) if supplement else None
        return round(cagr + supplement, 2)
    except Exception:
        return None


def index_returns(years=10):
    """Справочная среднегодовая доходность индексов MOEX за years лет.

    IMOEX — индекс акций МосБиржи, RGBI — индекс государственных
    облигаций. Возвращает {"stocks": %|None, "bonds": %|None};
    недоступный индекс даёт None и просто не участвует в расчёте.
    """
    result = {"stocks": None, "bonds": None}
    date_from = (dt.date.today()
                 - dt.timedelta(days=int(365.25 * years) + 7)).isoformat()
    for key, secid in (("stocks", "IMOEX"), ("bonds", "RGBI")):
        try:
            url = ("https://iss.moex.com/iss/statistics/engines/stock"
                   f"/markets/index/boards/SNDX/securities/{secid}/candles.json"
                   f"?iss.meta=off&iss.only=candles&interval=24&from={date_from}")
            data = _iss_json(url)
            rows = data["candles"]["data"]
            if len(rows) < 2:
                continue
            first, last = rows[0][1], rows[-1][1]
            if not first or not last:
                continue
            try:
                d1 = dt.datetime.strptime(str(rows[0][6])[:10], "%Y-%m-%d")
                d2 = dt.datetime.strptime(str(rows[-1][7])[:10], "%Y-%m-%d")
                days = (d2 - d1).days
            except (ValueError, TypeError):
                days = int(365.25 * years)
            if days < 30:
                continue
            result[key] = round(((last / first) ** (365.25 / days) - 1) * 100, 2)
        except Exception:
            continue
    return result


def portfolio_expected_return(data, years=10):
    """Ожидаемая доходность портфеля по историческим данным.

    Возвращает (by_assets, by_index):
    - by_assets — среднегодовая доходность отдельных бумаг
      (рост цены за `years` лет + дивиденды/купоны), взвешенная
      по доле позиции в портфеле (по текущей стоимости);
    - by_index — справочная оценка по индексам: IMOEX для акций
      и фондов, RGBI для облигаций, в пропорции видов портфеля
      (ближе к логике «60/40»).
    Любое из значений может быть None (нет данных).
    """
    quotes = refresh_positions(data)
    total = 0.0
    weighted = 0.0
    kind_totals = {}   # вид актива -> стоимость в портфеле
    for pos in data["positions"]:
        price, _, kind, facevalue = quotes.get(
            pos["ticker"], (None, None, None, None))
        if not kind:
            kind = pos.get("kind")
        st = position_stats(pos, price, kind, facevalue)
        value = st["value"] or st["invested"]
        if not value:
            continue
        r = historical_annual_return(pos["ticker"], years)
        if r is not None:
            weighted += value * r
            total += value
        if kind:
            kind_totals[kind] = kind_totals.get(kind, 0) + value
    by_assets = round(weighted / total, 2) if total > 0 else None

    # индексная оценка по структуре портфеля
    by_index = None
    if kind_totals:
        idx = index_returns(years)
        t = w = 0.0
        for kind, value in kind_totals.items():
            if kind in ("Акции", "ETF/фонды"):
                ref = idx["stocks"]
            elif kind == "Облигации":
                ref = idx["bonds"]
            else:
                ref = None
            if ref is None:
                continue
            w += value * ref
            t += value
        if t > 0:
            by_index = round(w / t, 2)
    return by_assets, by_index


def position_stats(pos, price, kind=None, facevalue=None):
    """Статистика позиции: стоимость, вложено, прибыль/убыток в ₽ и %.

    Для облигаций обе цены — в % от номинала (как на MOEX):
    стоимость = кол-во × номинал × цена / 100.
    Цена покупки позиции тоже должна быть в % от номинала
    (например, 86.50 при номинале 1000 ₽).
    """
    if kind == "Облигации":
        face = facevalue or 1000
        invested = pos["qty"] * face * pos["buy_price"] / 100
        if price is None:
            return {"invested": invested, "value": None,
                    "pl": None, "pl_pct": None}
        value = pos["qty"] * face * price / 100
    else:
        invested = pos["qty"] * pos["buy_price"]
        if price is None:
            return {"invested": invested, "value": None,
                    "pl": None, "pl_pct": None}
        value = pos["qty"] * price
    pl = value - invested
    pl_pct = (pl / invested * 100) if invested else 0
    return {"invested": invested, "value": value, "pl": pl, "pl_pct": pl_pct}


def compound_interest(initial, monthly, annual_rate, years):
    """Сложный процент с ежемесячной капитализацией и пополнениями.

    initial     — стартовая сумма;
    monthly     — ежемесячное пополнение;
    annual_rate — годовая ставка, % (например, 12 = 12% годовых);
    years       — срок в годах.
    Возвращает (final, invested, earned).
    """
    r = annual_rate / 100 / 12          # месячная ставка
    n = int(years * 12)                 # месяцев
    if n <= 0:
        return initial, initial, 0.0
    if r == 0:
        final = initial + monthly * n
    else:
        growth = (1 + r) ** n
        final = initial * growth + monthly * (growth - 1) / r
    invested = initial + monthly * n
    return final, invested, final - invested