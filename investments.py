import datetime as dt
import html
import json
import re
import urllib.parse
import urllib.request
from DataHandler import (load_portfolio, save_portfolio,
                         load_returns_cache, save_returns_cache)
BOND_LIST_CACHE = None   # кэш списка облигаций (запасной путь поиска)
# дивиденды smart-lab: кэш на текущий день,
# {"date": date, "divs": {тикер: [(дата отсечки, сумма), ...]}}
SMARTLAB_CACHE = None
# площадки БПИФ/ETF: TQTF — фонды, TQIF — иностранные, TQFD — прочие;
# фонды также распознаём по словам «ФОНД», «ETF», «БПИФ» в названии
FUND_BOARDS = ("TQTF", "TQIF", "TQFD")
FUND_NAME_HINTS = ("ФОНД", "ETF", "БПИФ")
FUND_LIST_CACHE = None   # кэш списка всех инструментов этих площадок


def _record_history(data, ticker, action, qty, price, pl):
    """Записать сделку в историю портфеля (data["history"])."""
    data.setdefault("history", []).append({
        "ticker": ticker, "action": action, "qty": qty,
        "price": price, "pl": pl,
        "date": dt.date.today().isoformat()})


def asset_history(data, ticker):
    """История сделок по активу (покупки и продажи), по возрастанию даты.
    Покупки берутся из data["history"]; продажи — из истории, а для
    старых сделок (сделанных до появления истории) — из data["realized"],
    чтобы прошлые продажи тоже были видны."""
    records = [h for h in data.get("history", [])
               if h.get("ticker") == ticker]
    for r in data.get("realized", []):
        if r.get("ticker") != ticker:
            continue
        duplicate = any(h.get("date") == r.get("date")
                        and h.get("qty") == r.get("qty")
                        and h.get("action") == "sell"
                        for h in records)
        if not duplicate:
            records.append({"ticker": ticker, "action": "sell",
                            "qty": r.get("qty"),
                            "price": r.get("sell_price"),
                            "pl": r.get("pl"),
                            "date": r.get("date")})
    records.sort(key=lambda h: h.get("date", ""))
    return records


def add_position(data, ticker, qty, buy_price):
    """Добавить покупку; если тикер уже есть — усредняем цену
    и складываем количество. Сделка записывается в историю."""
    for pos in data["positions"]:
        if pos["ticker"] == ticker:
            total_qty = pos["qty"] + qty
            pos["buy_price"] = round(
                (pos["buy_price"] * pos["qty"] + buy_price * qty) / total_qty, 4)
            pos["qty"] = total_qty
            _record_history(data, ticker, "buy", qty, buy_price, None)
            return pos
    pos = {"ticker": ticker, "qty": qty, "buy_price": buy_price,
           "buy_date": dt.date.today().isoformat()}
    data["positions"].append(pos)
    _record_history(data, ticker, "buy", qty, buy_price, None)
    return pos


def delete_position(data, ticker):
    data["positions"] = [p for p in data["positions"] if p["ticker"] != ticker]


def sell_position(data, ticker, qty, sell_price=None, kind=None, facevalue=None):
    """Продать часть позиции (или всё).
    Количество уменьшается на qty; усреднённая цена покупки не
    меняется; при продаже всего количества позиция удаляется.
    Если указана цена продажи, фиксируется реализованная прибыль:
    в data["realized"] добавляется запись о сделке
    {ticker, qty, buy_price, sell_price, pl, date}.
    Возвращает остаток количества (0, если продано всё)
    или None, если позиции нет.
    """
    for pos in data["positions"]:
        if pos["ticker"] == ticker:
            qty = min(qty, pos["qty"])
            if sell_price is not None:
                if kind == "Облигации":
                    face = facevalue or 1000
                    pl = qty * face * (sell_price - pos["buy_price"]) / 100
                else:
                    pl = qty * (sell_price - pos["buy_price"])
                data.setdefault("realized", []).append({
                    "ticker": ticker, "qty": qty,
                    "buy_price": pos["buy_price"], "sell_price": sell_price,
                    "pl": round(pl, 2),
                    "date": dt.date.today().isoformat()})
                _record_history(data, ticker, "sell", qty, sell_price,
                                round(pl, 2))
            if qty >= pos["qty"]:
                delete_position(data, ticker)
                return 0
            pos["qty"] -= qty
            return pos["qty"]
    return None


def realized_pl_total(data):
    """Суммарная реализованная прибыль по всем сделкам продажи, ₽."""
    return round(sum(r.get("pl", 0) for r in data.get("realized", [])), 2)


def passive_income(data, quotes=None):
    """Ожидаемый пассивный доход портфеля за 12 месяцев, ₽ (до налогов).
    Для акций — дивидендная доходность (средняя за 3 года) от текущей
    стоимости позиции, для облигаций — купонная доходность. Фонды
    и активы без регулярных выплат не учитываются.
    quotes — уже полученные котировки (не запрашивать заново);
    если не переданы, запрашиваются свежие.
    Возвращает (nominal, details): nominal — сумма, details —
    {ticker: (доход ₽ за год, доходность %)}; позиции с нулевой
    доходностью тоже попадают в details — для диагностики.
    """
    if quotes is None:
        quotes = refresh_positions(data)
    nominal = 0.0
    details = {}
    for pos in data["positions"]:
        price, _, kind, facevalue = quotes.get(
            pos["ticker"], (None, None, None, None))
        if not kind:
            kind = pos.get("kind")
        if kind not in ("Акции", "Облигации"):
            continue
        st = position_stats(pos, price, kind, facevalue)
        if not st["value"]:
            continue
        _, y = income_yield(pos["ticker"])
        inc = st["value"] * (y or 0) / 100
        details[pos["ticker"]] = (round(inc, 2), y or 0.0)
        nominal += inc
    return round(nominal, 2), details


def net_passive_income(nominal, capital, tax_pct=13, inflation_pct=8):
    """Пассивный доход с учётом налога и инфляции.
    Возвращает (net_tax, real): net_tax — после НДФЛ (tax_pct),
    real — покупательная способность этого дохода в ценах
    прошлого года: net_tax / (1 + инфляция) — стандартная
    формула (эффект Фишера) для дефлирования потока дохода.
    """
    net_tax = nominal * (1 - tax_pct / 100)
    real = net_tax / (1 + inflation_pct / 100)
    return round(net_tax, 2), round(real, 2)


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
    try:
        if _find_board(text) is not None:
            return text
    except Exception:
        pass
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
    for sec in candidates:
        name = (sec.get("name") or "").upper()
        if num in name or num in (sec.get("secid") or "").upper():
            if "ОФЗ" in name:
                return sec["secid"]
    for sec in candidates:
        name = (sec.get("name") or "").upper()
        secid = (sec.get("secid") or "").upper()
        if num in name or num in secid:
            return sec["secid"]
    try:
        # запасной путь: полный список облигаций (медленный, кэшируется)
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


def _cell_text(cell):
    """Текст ячейки HTML: убрать теги, сущности и лишние пробелы."""
    text = re.sub(r"<[^>]+>", " ", cell)
    text = html.unescape(text)
    return text.replace("\xa0", " ").replace(" ", " ").strip()


def _to_float(text):
    """Число из ячейки ('33,30' -> 33.3); None, если не число."""
    try:
        return float(text.replace(" ", "").replace(",", "."))
    except (ValueError, TypeError):
        return None


def _to_date(text):
    """Дата из ячейки ('14.06.2024' -> date); None при ошибке."""
    try:
        d, m, y = text.split(".")
        return dt.date(int(y), int(m), int(d))
    except (ValueError, AttributeError):
        return None


def _smartlab_fetch(url):
    """Скачать страницу smart-lab.ru (HTML) с браузерным заголовком."""
    req = urllib.request.Request(
        url, headers={"User-Agent":
                      "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode("utf-8", errors="replace")


def _smartlab_parse(page):
    """Разобрать таблицу дивидендов smart-lab: (тикер, сумма, дата
    отсечки, название, дивдоходность %). Колонки таблицы: название,
    тикер, период, дивиденд, дивдоходность, ..., дата отсечки,
    дата выплаты (см. макет страницы smart-lab.ru/dividends)."""
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S | re.I):
        cells = [_cell_text(c) for c in
                 re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S | re.I)]
        if len(cells) < 9:
            continue                       # служебные/чужие таблицы
        ticker, amount, cutoff = (cells[1].strip().upper(),
                                  _to_float(cells[3]), _to_date(cells[7]))
        # ячейка дивдоходности выглядит как «4,4%» — убираем знак %
        dy = _to_float((cells[4] or "").replace("%", "")) \
            if len(cells) > 4 else None
        if not ticker or amount is None or cutoff is None:
            continue
        rows.append((ticker, amount, cutoff, cells[0], dy))
    return rows


def _smartlab_dividends():
    """Все дивиденды с smart-lab (будущие + прошедшие), кэш на день.
    Возвращает {тикер: [(дата отсечки, сумма), ...]}. При сетевой
    ошибке кэш не обновляется — на следующем вызове повторим."""
    global SMARTLAB_CACHE
    today = dt.date.today()
    if SMARTLAB_CACHE and SMARTLAB_CACHE["date"] == today:
        return SMARTLAB_CACHE["divs"]
    divs = {}
    all_rows = []
    for url in ("https://smart-lab.ru/dividends/",
                "https://smart-lab.ru/dividends/history/"):
        try:
            page = _smartlab_fetch(url)
            found = _smartlab_parse(page)
            for ticker, amount, cutoff, name, dy in found:
                divs.setdefault(ticker, []).append((cutoff, amount))
                if url.endswith("/dividends/") and dy:
                    all_rows.append((ticker, name, dy, cutoff))
        except Exception:
            pass                    # сетевая ошибка — попробуем другой URL
    if divs:
        SMARTLAB_CACHE = {"date": today, "divs": divs, "rows": all_rows}
    return divs


def _dividend_yield(secid, price):
    """Средняя годовая дивидендная доходность акции, %.
    MOEX ISS отдаёт дивиденды по бумаге только платным подписчикам
    (Corporate Information Service), открытого эндпоинта больше нет —
    запрос /securities/{secid}/dividends.json возвращает лишь справку
    (description/boards). Поэтому суммы выплат и даты отсечек берём
    с открытой таблицы smart-lab.ru: складываем выплаты за последние
    ~3 года плюс объявленные будущие, делим на число лет, которые
    эти выплаты покрывают, и на текущую цену. Нет данных — 0.
    """
    if not price:
        return 0.0
    divs = _smartlab_dividends()
    payments = divs.get(secid.upper())
    if not payments:
        return 0.0
    cutoff = dt.date.today() - dt.timedelta(days=int(365.25 * 3) + 30)
    used = [(d, a) for d, a in payments if d >= cutoff]
    if not used:
        return 0.0                 # последние 3 года выплат не было
    # среднее в год: выплаты покрывают span календарных лет
    years = max(1, max(d for d, _ in used).year
                - min(d for d, _ in used).year + 1)
    paid = sum(a for _, a in used)
    return round(paid / min(years, 3) / float(price) * 100, 2)


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


def income_yield(ticker):
    """Дивидендная (акции) или купонная (облигации) доходность, % годовых.
    Фонды и прочие активы без регулярных выплат — 0.
    Возвращает (kind, yield_pct).
    """
    secid = resolve_ticker(ticker)
    if secid is None:
        return None, 0.0
    try:
        boards = _all_boards(secid)
        if not boards:
            return None, 0.0
        board = next((b for b in boards if b.get("is_primary")), boards[0])
        kind = _classify(boards, secid)
        url = (f"https://iss.moex.com/iss/engines/{board['engine']}"
               f"/markets/{board['market']}/boards/{board['boardid']}"
               f"/securities/{secid}.json"
               f"?iss.meta=off&iss.only=marketdata,securities")
        data = _iss_json(url)
        sec_row = dict(zip(data["securities"]["columns"],
                           data["securities"]["data"][0])) \
            if data["securities"]["data"] else {}
        price = None
        if data["marketdata"]["data"]:
            md = dict(zip(data["marketdata"]["columns"],
                          data["marketdata"]["data"][0]))
            price = (md.get("LAST") or md.get("MARKETPRICE")
                     or md.get("LASTTOPREVPRICE"))
        if price is None:
            price = sec_row.get("PREVPRICE")
        if kind == "Облигации":
            return kind, _coupon_yield(sec_row, price)
        if kind == "Акции":
            return kind, _dividend_yield(secid, price)
        return kind, 0.0
    except Exception:
        return None, 0.0


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


def consensus_rating(annual_return):
    """Консенсус-маркер актива (аналог рейтинга «Покупать/Держать/
    Продавать» в брокерских приложениях) по ожидаемой доходности:
    - >= 12% годовых — Покупать;
    - 5–12% — Держать;
    - < 5% — Продавать.
    None, если доходность неизвестна.
    """
    if annual_return is None:
        return None
    if annual_return >= 12:
        return "Покупать"
    if annual_return >= 5:
        return "Держать"
    return "Продавать"


def portfolio_expected_return(data, years=10):
    """Ожидаемая доходность портфеля по историческим данным.
    Возвращает (by_assets, by_index, per_ticker):
    - by_assets — среднегодовая доходность отдельных бумаг
      (рост цены за `years` лет + дивиденды/купоны), взвешенная
      по доле позиции в портфеле (по текущей стоимости);
    - by_index — справочная оценка по индексам: IMOEX для акций
      и фондов, RGBI для облигаций, в пропорции видов портфеля
      (ближе к логике «60/40»);
    - per_ticker — {ticker: среднегодовая доходность} для колонки
      консенсус-маркера.
    by_assets/by_index могут быть None (нет данных).
    """
    quotes = refresh_positions(data)
    total = 0.0
    weighted = 0.0
    kind_totals = {}   # вид актива -> стоимость в портфеле
    per_ticker = {}
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
            per_ticker[pos["ticker"]] = r
            weighted += value * r
            total += value
        if kind:
            kind_totals[kind] = kind_totals.get(kind, 0) + value
    by_assets = round(weighted / total, 2) if total > 0 else None
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
    return by_assets, by_index, per_ticker


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


# --- Тактика «трёх столбов» (50 / 25 / 25) ---
# Целевые доли: рублёвый столб 50% (40% акции четырёх секторов
# по 10% + 10% денежный рынок AKMM), валютный 25% (замещающие или
# юаневые облигации), золотой 25% (золото на Мосбирже).
PILLAR_TARGETS = {"ruble": 50, "currency": 25, "gold": 25}
PILLAR_NAMES = {"ruble": "Рублёвый", "currency": "Валютный",
                "gold": "Золотой"}

# золото на Мосбирже: фонды и тикеры
GOLD_TICKERS = {"TGLD", "GLD", "GOLD", "GOLDU", "GLDRUB", "GOLDRUB"}
# денежный рынок (фонды ликвидности) — часть рублёвого столба
MONEY_TICKERS = {"AKMM", "AKME", "LQDT", "SBMM", "AKMEC"}
# секторы рублёвого столба (4 сектора по 10% + денежный рынок 10%)
SECTOR_TARGET_PCT = 10
_STOCK_SECTORS = {
    "SBER": "Финансы", "SBERP": "Финансы", "VTBR": "Финансы",
    "TCSG": "Финансы", "AFKS": "Финансы", "MOEX": "Финансы",
    "GAZP": "Нефтегаз", "LKOH": "Нефтегаз", "ROSN": "Нефтегаз",
    "NVTK": "Нефтегаз", "TATN": "Нефтегаз", "TATNP": "Нефтегаз",
    "SNGS": "Нефтегаз", "SNGSP": "Нефтегаз", "UPRO": "Нефтегаз",
    "YDEX": "Технологии", "MTSS": "Технологии", "T": "Технологии",
    "RTKM": "Технологии", "SMLT": "Технологии", "OZON": "Технологии",
    "GMKN": "Металлургия и ритейл", "CHMF": "Металлургия и ритейл",
    "NLMK": "Металлургия и ритейл", "MAGN": "Металлургия и ритейл",
    "IRA0": "Металлургия и ритейл",
    "MGNT": "Металлургия и ритейл", "LENT": "Металлургия и ритейл",
}
# облигации: юаневые выпуски ОФЗ идут сериями 292xx
_YUAN_BOND_PREFIXES = ("SU292",)


def auto_pillar(ticker, kind=None):
    """Автоопределение столба по тикеру/виду. Акции и фонды по
    умолчанию — рублёвый столб (это топовые российские бумаги);
    облигации без признаков юаня определить нельзя (замещающие
    или обычные?) — их столб задаётся вручную полем "pillar"."""
    t = (ticker or "").upper()
    if t in GOLD_TICKERS:
        return "gold"
    if t in MONEY_TICKERS:
        return "ruble"
    # юаневые ОФЗ (серии 292xx) — валютный столб
    if t.startswith(_YUAN_BOND_PREFIXES):
        return "currency"
    if kind != "Облигации":
        return "ruble"
    return None


def position_pillar(pos, kind=None):
    """Столб позиции: ручной выбор "pillar" приоритетнее авто."""
    manual = pos.get("pillar")
    if manual in PILLAR_TARGETS:
        return manual
    return auto_pillar(pos.get("ticker"), kind or pos.get("kind"))


def sector_of(pos, pillar, kind=None):
    """Сектор внутри рублевого столба (для разбивки 4+1 по 10%)."""
    t = (pos.get("ticker") or "").upper()
    if t in MONEY_TICKERS:
        return "Денежный рынок"
    if pillar == "ruble":
        return _STOCK_SECTORS.get(t, "Прочее")
    return None


def pillar_allocation(data, quotes=None):
    """Доли трёх столбов и секторов рублёвого по текущей стоимости.
    quotes — как в refresh_positions; если цены ещё не загружены,
    стоимость позиции берётся по цене покупки. Возвращает словарь:
    {"total": ₽, "pillars": {ключ: {"value": ₽, "pct": %}},
     "sectors": {сектор: {"value": ₽, "pct": %}},
     "unclassified": [(тикер, ₽, вид)]}"""
    total = 0.0
    pillars = {k: 0.0 for k in PILLAR_TARGETS}
    sectors = {}
    unclassified = []
    for pos in data["positions"]:
        price, _upd, kind, face = (quotes or {}).get(
            pos["ticker"], (None, None, None, None))
        if not kind:
            kind = pos.get("kind")
        st = position_stats(pos, price, kind, face)
        value = st["value"] if st["value"] else (st["invested"] or 0)
        if not value:
            continue
        total += value
        pillar = position_pillar(pos, kind)
        if pillar is None:
            unclassified.append((pos["ticker"], value, kind or "—"))
            continue
        pillars[pillar] += value
        if pillar == "ruble":
            sec = sector_of(pos, pillar, kind) or "Прочее"
            sectors[sec] = sectors.get(sec, 0.0) + value
    out = {"total": total, "pillars": {}, "sectors": {},
           "unclassified": unclassified}
    for k, v in pillars.items():
        out["pillars"][k] = {"value": v,
                             "pct": (v / total * 100) if total else 0}
    for s, v in sectors.items():
        out["sectors"][s] = {"value": v,
                             "pct": (v / total * 100) if total else 0}
    return out


def deposit_plan(alloc, deposit):
    """Распределить пополнение по столбам: сначала закрываем
    недобор до цели пропорционально отклонению, так чтобы после
    пополнения доли максимально приблизились к 50/25/25.
    Возвращает {столб: ₽ к докупке}."""
    total = alloc["total"]
    if deposit <= 0 or total <= 0:
        return {k: 0.0 for k in PILLAR_TARGETS}
    need = {}
    for k, target in PILLAR_TARGETS.items():
        # сколько ₽ должно быть в столбе после пополнения
        want = (total + deposit) * target / 100
        need[k] = max(0.0, want - alloc["pillars"][k]["value"])
    shortage = sum(need.values())
    if shortage <= 0:
        # все цели достигнуты — докупаем пропорционально целям
        return {k: deposit * PILLAR_TARGETS[k] / sum(PILLAR_TARGETS.values())
                for k in PILLAR_TARGETS}
    # если недобор больше суммы пополнения — делим пропорционально недобору
    if shortage > deposit:
        return {k: deposit * v / shortage for k, v in need.items()}
    # недобор покрывается целиком, остаток — пропорционально целям
    rest = deposit - shortage
    plan = dict(need)
    for k in PILLAR_TARGETS:
        plan[k] += rest * PILLAR_TARGETS[k] / sum(PILLAR_TARGETS.values())
    return plan