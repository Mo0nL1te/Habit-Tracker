import math
import tkinter as tk
from tkinter import messagebox
import investments as inv


class PieChart(tk.Canvas):
    """Круговая диаграмма долей активов (tk Canvas, без библиотек).
    При наведении мышью на сектор показывает подсказку: вид актива,
    его долю и состав (тикеры внутри сектора и их доли)."""
    COLORS = ["#4caf50", "#2196f3", "#ff9800", "#9c27b0",
              "#e91e63", "#00bcd4", "#795548", "#607d8b"]

    def __init__(self, master, width=200, height=200):
        super().__init__(master, width=width, height=height + 90, bg="#fafafa",
                         highlightthickness=0)
        self.w = width
        self.h = height
        self.slices = []    # [(вид, стоимость, начальный угол, сектор °)]
        self.details = {}   # вид -> [(тикер, стоимость)]
        self._tip = None
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", lambda _e: self._hide_tip())

    def draw(self, shares, details=None):
        """shares: список [(вид актива, стоимость ₽)] без нулевых.
        details: вид -> [(тикер, стоимость ₽)] — состав для подсказки."""
        self.delete("all")
        self._hide_tip()
        self.slices = []
        self.details = details or {}
        self.config(width=self.w, height=self.h + 90)
        total = sum(v for _, v in shares)
        if total <= 0:
            self.create_text(self.w // 2, self.h // 2, text="Нет данных.\n"
                             "Нажмите «Обновить статусы активов».",
                             font=("Arial", 9), fill="#999", justify="center")
            return
        cx, cy = self.w // 2, self.h // 2
        r = min(self.w, self.h) // 2 - 8
        start = 90
        for i, (label, value) in enumerate(shares):
            extent = 360 * value / total
            color = self.COLORS[i % len(self.COLORS)]
            self.create_arc(cx - r, cy - r, cx + r, cy + r,
                            start=start, extent=extent, fill=color,
                            outline="white", width=2, style="pieslice")
            self.slices.append((label, value, start, extent))
            start += extent
        y = self.h + 10
        for i, (label, value) in enumerate(shares):
            color = self.COLORS[i % len(self.COLORS)]
            pct = value / total * 100
            self.create_rectangle(6, y, 18, y + 12, fill=color, outline="")
            self.create_text(24, y + 6, anchor="w", font=("Arial", 8),
                             text=f"{label}: {pct:.1f}%"
                                  f" ({value:,.0f} ₽)".replace(",", " "))
            y += 16
        # холст подстраивается под содержимое: легенда может быть
        # шире и длиннее самой диаграммы — иначе она обрезается
        bbox = self.bbox("all")
        if bbox:
            self.config(width=max(self.w, bbox[2] + 8),
                        height=max(self.h + 90, bbox[3] + 8))

    def _on_motion(self, event):
        """Наведение на сектор: ищем, под каким углом курсор.
        Tk рисует дуги от 3 часов против часовой; y на холсте
        растёт вниз, поэтому угол = atan2(-dy, dx)."""
        if not self.slices:
            return
        cx, cy = self.w // 2, self.h // 2
        r = min(self.w, self.h) // 2 - 8
        dx, dy = event.x - cx, event.y - cy
        if dx * dx + dy * dy > r * r:
            self._hide_tip()
            return
        ang = math.degrees(math.atan2(-dy, dx)) % 360
        for label, value, s_start, extent in self.slices:
            if (ang - s_start) % 360 <= extent:
                self._show_tip(event, label, value)
                return
        self._hide_tip()

    def _show_tip(self, event, label, value):
        total = sum(v for _, v, _, _ in self.slices)
        pct = value / total * 100
        lines = [f"{label} — {pct:.1f}% ({value:,.0f} ₽)".replace(",", " ")]
        comps = self.details.get(label)
        if comps:
            lines.append("Состав:")
            for ticker, v in sorted(comps, key=lambda c: -c[1]):
                of_slice = v / value * 100
                lines.append(f"  {ticker}: {v / total * 100:.1f}% портфеля"
                             f" ({of_slice:.1f}% сектора,"
                             f" {v:,.0f} ₽)".replace(",", " "))
        self._hide_tip()
        tip = tk.Toplevel(self)
        tip.wm_overrideredirect(True)
        tip.configure(bg="#333", padx=8, pady=5)
        tk.Label(tip, text=lines[0], font=("Arial", 9, "bold"),
                 fg="white", bg="#333").pack(anchor="w")
        for line in lines[1:]:
            tk.Label(tip, text=line, font=("Arial", 8),
                     fg="#ddd", bg="#333").pack(anchor="w")
        tip.update_idletasks()
        x = self.winfo_rootx() + event.x + 14
        y = self.winfo_rooty() + event.y + 14
        if x + tip.winfo_reqwidth() > tip.winfo_screenwidth() - 8:
            x -= tip.winfo_reqwidth() + 28
        if y + tip.winfo_reqheight() > tip.winfo_screenheight() - 8:
            y -= tip.winfo_reqheight() + 28
        tip.wm_geometry(f"+{x}+{y}")
        self._tip = tip

    def _hide_tip(self):
        if self._tip is not None:
            self._tip.destroy()
            self._tip = None


class InvestmentsWindow(tk.Toplevel):
    """Отдельное окно: позиции, обновление котировок MOEX,
    круговая диаграмма структуры портфеля и калькулятор."""

    def __init__(self, master):
        super().__init__(master)
        self.title("Инвестиции")
        self.configure(bg="#fafafa")
        self.data = inv.load_portfolio()
        self.quotes = {}   # "TICKER" -> (price, updated, kind, facevalue)
        self.expected = {}  # "TICKER" -> среднегодовая доходность (для прогноза)
        self.tax_pct = 13
        self.inflation_pct = 8
        self._build_portfolio()
        self._build_calculator()
        self.render_positions()
        self._fit_window_size()
        self.after(100, self.refresh_quotes)

    def _build_portfolio(self):
        pf = tk.LabelFrame(self, text=" Портфель ", font=("Arial", 10, "bold"),
                           bg="#fafafa", fg="#444")
        pf.pack(fill="both", expand=True, padx=10, pady=(10, 5))
        add_row = tk.Frame(pf, bg="#fafafa")
        add_row.pack(fill="x", padx=8, pady=6)
        tk.Label(add_row, text="Тикер:", bg="#fafafa").pack(side="left")
        self.ticker_entry = tk.Entry(add_row, width=12)
        self.ticker_entry.pack(side="left", padx=(4, 10))
        tk.Label(add_row, text="Кол-во:", bg="#fafafa").pack(side="left")
        self.qty_entry = tk.Entry(add_row, width=8)
        self.qty_entry.pack(side="left", padx=(4, 10))
        tk.Label(add_row, text="Цена покупки:", bg="#fafafa").pack(side="left")
        self.price_entry = tk.Entry(add_row, width=10)
        self.price_entry.pack(side="left", padx=(4, 10))
        tk.Button(add_row, text="＋ добавить", font=("Arial", 9), relief="flat",
                  bg="#4caf50", fg="white", cursor="hand2",
                  command=self.add_position).pack(side="left")
        tk.Label(add_row, text="SBER, GAZP, LKOH или ОФЗ 26245", fg="#999",
                 font=("Arial", 8), bg="#fafafa").pack(side="left", padx=(8, 0))
        content = tk.Frame(pf, bg="#fafafa")
        content.pack(fill="both", expand=True, padx=8, pady=(0, 4))
        self.table = tk.Frame(content, bg="#fafafa")
        self.table.pack(side="left", fill="both", expand=True)
        pie_col = tk.Frame(content, bg="#fafafa")
        pie_col.pack(side="right", padx=(14, 4), anchor="n")
        tk.Label(pie_col, text="Структура портфеля", font=("Arial", 9, "bold"),
                 bg="#fafafa", fg="#555").pack()
        self.pie = PieChart(pie_col, width=220, height=220)
        self.pie.pack()
        # панель «три столба» — под диаграммой, в том же правом столбце
        self.pillars = PillarsPanel(pie_col, self)
        self.pillars.pack(fill="x", pady=(10, 0))
        btn_row = tk.Frame(pf, bg="#fafafa")
        btn_row.pack(fill="x", padx=8, pady=(4, 8))
        tk.Button(btn_row, text="⟳ Обновить статусы активов", font=("Arial", 10, "bold"),
                  relief="flat", bg="#2196f3", fg="white", padx=12, pady=4,
                  cursor="hand2", command=self.refresh_quotes).pack(side="left")
        tk.Button(btn_row, text="📈 Доходность портфеля", font=("Arial", 10, "bold"),
                  relief="flat", bg="#4caf50", fg="white", padx=12, pady=4,
                  cursor="hand2", command=self.calc_portfolio_return).pack(side="left",
                                                                          padx=(6, 0))
        self.status_label = tk.Label(btn_row, text="", fg="#666", bg="#fafafa",
                                     font=("Arial", 9))
        self.status_label.pack(side="left", padx=10)
        self.selected_ticker = None
        bottom = tk.Frame(pf, bg="#fafafa")
        bottom.pack(fill="x", padx=8, pady=(2, 6))
        self.info_frame = tk.LabelFrame(bottom, text=" Актив ",
                                        font=("Arial", 9, "bold"),
                                        bg="#fafafa", fg="#444")
        self.info_frame.pack(side="left", fill="both", expand=True)
        self.info_title = tk.Label(self.info_frame, text="", font=("Arial", 9, "bold"),
                                   bg="#fafafa")
        self.info_title.pack(anchor="w", padx=8, pady=(2, 0))
        self.info_history = tk.Frame(self.info_frame, bg="#fafafa")
        self.info_history.pack(fill="x", padx=8, pady=2)
        trade_row = tk.Frame(self.info_frame, bg="#fafafa")
        trade_row.pack(fill="x", padx=8, pady=(0, 6))
        tk.Label(trade_row, text="Кол-во:", font=("Arial", 8),
                 bg="#fafafa").pack(side="left")
        self.trade_qty = tk.Entry(trade_row, width=7)
        self.trade_qty.pack(side="left", padx=(3, 10))
        tk.Label(trade_row, text="Цена:", font=("Arial", 8),
                 bg="#fafafa").pack(side="left")
        self.trade_price = tk.Entry(trade_row, width=9)
        self.trade_price.pack(side="left", padx=(3, 12))
        tk.Button(trade_row, text="Купить", font=("Arial", 9, "bold"), relief="flat",
                  bg="#4caf50", fg="white", padx=10, cursor="hand2",
                  command=self.info_buy).pack(side="left", padx=(0, 6))
        tk.Button(trade_row, text="Продать", font=("Arial", 9, "bold"), relief="flat",
                  bg="#f57c00", fg="white", padx=10, cursor="hand2",
                  command=self.info_sell).pack(side="left")
        self.info_hint = tk.Label(self.info_frame,
                 text="Кликните по тикеру в таблице, чтобы увидеть историю сделок",
                 font=("Arial", 8), fg="#999", bg="#fafafa")
        self.info_hint.pack(anchor="w", padx=8, pady=2)
        self.passive_frame = tk.LabelFrame(bottom, text=" Пассивный доход ",
                                           font=("Arial", 9, "bold"),
                                           bg="#fafafa", fg="#9c27b0")
        self.passive_frame.pack(side="right", fill="y", padx=(10, 0))
        self.passive_labels = {}
        for label, key in (("Доход за год:", "gross"),
                           ("После НДФЛ:", "net"),
                           ("В месяц:", "month"),
                           ("С учётом инфляции:", "real")):
            row_f = tk.Frame(self.passive_frame, bg="#fafafa")
            row_f.pack(fill="x", padx=8)
            tk.Label(row_f, text=label, font=("Arial", 8), fg="#666",
                     bg="#fafafa").pack(side="left")
            self.passive_labels[key] = tk.Label(row_f, font=("Arial", 8, "bold"),
                                                text="…", bg="#fafafa")
            self.passive_labels[key].pack(side="right")
        settings = tk.Frame(self.passive_frame, bg="#fafafa")
        settings.pack(fill="x", padx=8, pady=(2, 6))
        tk.Label(settings, text="НДФЛ, %:", font=("Arial", 8),
                 bg="#fafafa").pack(side="left")
        self.tax_entry = tk.Entry(settings, width=4, font=("Arial", 8))
        self.tax_entry.insert(0, str(self.tax_pct))
        self.tax_entry.pack(side="left", padx=(3, 8))
        tk.Label(settings, text="Инфляция, %:", font=("Arial", 8),
                 bg="#fafafa").pack(side="left")
        self.infl_entry = tk.Entry(settings, width=4, font=("Arial", 8))
        self.infl_entry.insert(0, str(self.inflation_pct))
        self.infl_entry.pack(side="left", padx=(3, 0))
        for entry in (self.tax_entry, self.infl_entry):
            entry.bind("<Return>", lambda _e: self.update_passive())
            entry.bind("<FocusOut>", lambda _e: self.update_passive())

    def _fit_window_size(self):
        """Подобрать размер окна по содержимому: число строк таблицы,
        диаграмма долей, калькулятор. Ширина — не уже 760 px, высота
        ограничивается экраном. Минимальный размер фиксируется,
        чтобы при уменьшении портфеля окно не стало слишком мелким."""
        self.update_idletasks()
        w = max(self.winfo_reqwidth(), 760)
        h = min(self.winfo_reqheight(), self.winfo_screenheight() - 120)
        self.geometry(f"{w}x{h}")
        self.minsize(w, 400)

    def render_positions(self):
        for w in self.table.winfo_children():
            w.destroy()
        headers = ["Тикер", "Вид", "Кол-во", "Цена покупки", "Текущая цена",
                   "Прогноз", "Стоимость", "Прибыль/убыток"]
        for col, h in enumerate(headers):
            tk.Label(self.table, text=h, font=("Arial", 9, "bold"), bg="#fafafa",
                     fg="#555").grid(row=0, column=col, padx=6, sticky="w")
        if not self.data["positions"]:
            tk.Label(self.table, text="Позиций пока нет — добавьте первую сверху.",
                     font=("Arial", 9), fg="#888", bg="#fafafa").grid(
                row=1, column=0, columnspan=10, pady=8, sticky="w")
            self.pie.draw([])
            self.pillars.render()
            return
        total_value = total_pl = total_invested = 0
        has_price = False
        kind_values = {}   # вид актива -> стоимость (для круговой диаграммы)
        kind_details = {}  # вид -> [(тикер, стоимость)] (для подсказки)
        for i, pos in enumerate(self.data["positions"], start=1):
            price, updated, kind, face = self.quotes.get(
                pos["ticker"], (None, None, None, None))
            if not kind:
                kind = pos.get("kind")   # вид, заданный вручную
            st = inv.position_stats(pos, price, kind, face)
            color = "#444"
            if st["pl"] is not None:
                has_price = True
                total_value += st["value"]
                total_pl += st["pl"]
                color = "#2e7d32" if st["pl"] >= 0 else "#c62828"
                kind_values[kind or "Прочее"] = \
                    kind_values.get(kind or "Прочее", 0) + st["value"]
                kind_details.setdefault(kind or "Прочее", []).append(
                    (pos["ticker"], st["value"]))
            if st["invested"]:
                total_invested += st["invested"]
            display = pos["ticker"]
            ticker_lbl = tk.Label(self.table, text=display, font=("Arial", 9, "bold"),
                                  fg="#1565c0", bg="#fafafa", cursor="hand2")
            ticker_lbl.grid(row=i, column=0, padx=6, sticky="w")
            ticker_lbl.bind("<Button-1>",
                            lambda e, t=pos["ticker"]: self.select_asset(t))
            kind_lbl = tk.Label(self.table, text=kind or "—", font=("Arial", 8),
                                fg="#1565c0", bg="#fafafa", cursor="hand2")
            kind_lbl.grid(row=i, column=1, padx=6, sticky="w")
            kind_lbl.bind("<Button-1>",
                          lambda e, t=pos["ticker"]: self.edit_kind(t))
            tk.Label(self.table, text=str(pos["qty"]), bg="#fafafa").grid(
                row=i, column=2, padx=6, sticky="e")
            buy_txt = f"{pos['buy_price']:.2f} %" if kind == "Облигации" \
                else f"{pos['buy_price']:.2f}"
            tk.Label(self.table, text=buy_txt, bg="#fafafa").grid(
                row=i, column=3, padx=6, sticky="e")
            price_txt = (f"{price:.2f} %" if price is not None else "—") \
                if kind == "Облигации" \
                else (f"{price:.2f}" if price is not None else "—")
            tk.Label(self.table, text=price_txt, bg="#fafafa").grid(
                row=i, column=4, padx=6, sticky="e")
            rating = inv.consensus_rating(self.expected.get(pos["ticker"]))
            rating_colors = {"Покупать": "#2e7d32",
                             "Держать": "#f9a825",
                             "Продавать": "#c62828"}
            tk.Label(self.table, text=rating or "—", font=("Arial", 8, "bold"),
                     fg=rating_colors.get(rating, "#999"), bg="#fafafa").grid(
                row=i, column=5, padx=6, sticky="e")
            value_txt = f"{st['value']:,.0f} ₽".replace(",", " ") if st["value"] else "—"
            tk.Label(self.table, text=value_txt, bg="#fafafa").grid(
                row=i, column=6, padx=6, sticky="e")
            if st["pl"] is not None:
                pl_txt = f"{st['pl']:+,.0f} ₽ ({st['pl_pct']:+.1f}%)".replace(",", " ")
            else:
                pl_txt = "—"
            tk.Label(self.table, text=pl_txt, fg=color, bg="#fafafa").grid(
                row=i, column=7, padx=6, sticky="e")
        r = len(self.data["positions"]) + 1
        if has_price:
            total_pct = (total_pl / total_invested * 100) if total_invested else 0
            color = "#2e7d32" if total_pl >= 0 else "#c62828"
            tk.Label(self.table, text="Итого:", font=("Arial", 9, "bold"),
                     bg="#fafafa").grid(row=r, column=0, columnspan=2,
                                        sticky="w", pady=(6, 0))
            tk.Label(self.table, text=f"{total_value:,.0f} ₽".replace(",", " "),
                     font=("Arial", 9, "bold"), bg="#fafafa").grid(
                row=r, column=6, sticky="e", pady=(6, 0))
            tk.Label(self.table,
                     text=f"{total_pl:+,.0f} ₽ ({total_pct:+.1f}%)".replace(",", " "),
                     font=("Arial", 9, "bold"), fg=color, bg="#fafafa").grid(
                row=r, column=7, sticky="e", pady=(6, 0))
        realized = inv.realized_pl_total(self.data)
        if realized:
            rcolor = "#2e7d32" if realized >= 0 else "#c62828"
            tk.Label(self.table, text="Реализованная прибыль (проданные):",
                     font=("Arial", 9, "bold"), bg="#fafafa",
                     fg="#555").grid(row=r + 1, column=0, columnspan=7,
                                     sticky="w", pady=(2, 0))
            tk.Label(self.table,
                     text=f"{realized:+,.0f} ₽".replace(",", " "),
                     font=("Arial", 9, "bold"), fg=rcolor, bg="#fafafa").grid(
                row=r + 1, column=7, sticky="e", pady=(2, 0))
        shares = sorted(kind_values.items(), key=lambda kv: -kv[1])
        self.pie.draw(shares, kind_details)
        self.pillars.render()

    def add_position(self):
        try:
            qty = int(self.qty_entry.get().strip())
            price = float(self.price_entry.get().strip().replace(",", "."))
        except ValueError:
            messagebox.showinfo("Проверьте ввод",
                                "Количество — целое число, цена — число.\n"
                                "Например: SBER, 10, 250.50", parent=self)
            return
        ticker = self.ticker_entry.get().strip()
        if not ticker or qty <= 0 or price <= 0:
            messagebox.showinfo("Проверьте ввод",
                                "Заполните тикер, количество и цену покупки.",
                                parent=self)
            return
        resolved = inv.resolve_ticker(ticker)
        if resolved is None:
            messagebox.showinfo(
                "Инструмент не найден",
                f"Не удалось найти «{ticker}» на MOEX.\n\n"
                "Проверьте тикер: акции — SBER, GAZP, LKOH;\n"
                "ОФЗ — «ОФЗ 26245» или код выпуска SU26245RMFS4.",
                parent=self)
            return
        inv.add_position(self.data, resolved, qty, price)
        inv.save_portfolio(self.data)
        self.ticker_entry.delete(0, "end")
        self.qty_entry.delete(0, "end")
        self.price_entry.delete(0, "end")
        self.render_positions()
        self._fit_window_size()   # строк стало больше — подгоняем окно
        self.after(100, self.refresh_quotes)

    def edit_kind(self, ticker):
        """Ручная смена вида актива (клик по ячейке «Вид»).
        Выбор сохраняется в investments.json (поле "kind") и сразу
        учитывается: в таблице, в расчёте стоимости (для облигаций —
        через номинал) и на круговой диаграмме. «Авто» сбрасывает
        выбор и возвращает определение с биржи.
        """
        pos = next((p for p in self.data["positions"]
                    if p["ticker"] == ticker), None)
        if pos is None:
            return

        def apply(new_kind):
            pos["kind"] = new_kind or None
            inv.save_portfolio(self.data)
            q = self.quotes.get(ticker)
            if q is not None:
                auto_kind = q[2]
                # вид в кэше котировок тоже обновляем, чтобы диаграмма
                # перерисовалась без нового запроса к бирже
                self.quotes[ticker] = (q[0], q[1],
                                       new_kind or auto_kind, q[3])
            self.render_positions()
        menu = tk.Menu(self, tearoff=0)
        current = pos.get("kind")
        menu.add_command(label="Авто (определить с биржи)" + (
            "" if current else "  ✓"), command=lambda: apply(None))
        for k in ("Акции", "ETF/фонды", "Облигации", "Прочее"):
            menu.add_command(label=k + ("  ✓" if k == current else ""),
                             command=lambda k=k: apply(k))
        menu.add_separator()
        # столб тактики 50/25/25: ручной выбор приоритетнее авто
        cur_p = pos.get("pillar")

        def apply_pillar(p):
            pos["pillar"] = p
            inv.save_portfolio(self.data)
            self.render_positions()
        menu.add_command(label="Столб: авто" + ("" if cur_p else "  ✓"),
                         command=lambda: apply_pillar(None))
        for k, name in inv.PILLAR_NAMES.items():
            menu.add_command(
                label=f"Столб: {name}" + ("  ✓" if k == cur_p else ""),
                command=lambda k=k: apply_pillar(k))
        menu.tk_popup(self.winfo_pointerx(), self.winfo_pointery())

    def update_passive(self):
        """Пересчитать блок пассивного дохода в правом нижнем углу:
        дивиденды и купоны по позициям, НДФЛ, инфляция. Использует
        уже загруженные котировки (без новых запросов при пересчёте
        налога/инфляции)."""
        try:
            tax = float(self.tax_entry.get().strip().replace(",", "."))
            infl = float(self.infl_entry.get().strip().replace(",", "."))
        except ValueError:
            return
        self.tax_pct, self.inflation_pct = tax, infl
        try:
            nominal, _details = inv.passive_income(self.data, self.quotes)
        except Exception:
            nominal = 0.0
        total_value = 0.0
        for pos in self.data["positions"]:
            price, _, kind, facevalue = self.quotes.get(
                pos["ticker"], (None, None, None, None))
            if not kind:
                kind = pos.get("kind")
            stats = inv.position_stats(pos, price, kind, facevalue)
            if stats["value"]:
                total_value += stats["value"]
        net, real = inv.net_passive_income(nominal, total_value,
                                           tax, infl)

        def fmt(v):
            return f"{v:,.0f} ₽".replace(",", " ")
        self.passive_labels["gross"].config(text=fmt(nominal), fg="#333")
        self.passive_labels["net"].config(text=fmt(net), fg="#2e7d32")
        self.passive_labels["month"].config(text=fmt(net / 12), fg="#2e7d32")
        self.passive_labels["real"].config(
            text=f"{real:+,.0f} ₽".replace(",", " "),
            fg="#2e7d32" if real >= 0 else "#c62828")

    def calc_portfolio_return(self):
        """Ожидаемая доходность портфеля по историческим ценам MOEX:
        взвешенная среднегодовая доходность позиций, вес — доля
        актива в портфеле по текущей стоимости."""
        if not self.data["positions"]:
            self.status_label.config(text="Портфель пуст")
            return
        self.status_label.config(text="Считаю историческую доходность…")
        self.update_idletasks()
        by_assets, by_index, per_ticker = inv.portfolio_expected_return(self.data, years=10)
        if by_assets is None:
            self.status_label.config(
                text="Не удалось получить историю цен (проверьте интернет)")
            return
        self.expected = per_ticker
        sign = "+" if by_assets >= 0 else ""
        msg = f"Ожидаемая доходность портфеля: {sign}{by_assets:.1f}% годовых"
        if by_index is not None:
            msg += f"  •  по индексам (IMOEX/RGBI): {by_index:+.1f}%"
        self.status_label.config(text=msg)
        self.render_positions()   # обновляем колонку «Прогноз»
        self.calc_entries[2].delete(0, "end")
        self.calc_entries[2].insert(0, f"{by_assets:g}")
        total_value = 0
        for pos in self.data["positions"]:
            price, _, kind, face = self.quotes.get(
                pos["ticker"], (None, None, None, None))
            st = inv.position_stats(pos, price, kind, face)
            if st["value"]:
                total_value += st["value"]
        if total_value > 0:
            self.calc_entries[0].delete(0, "end")
            self.calc_entries[0].insert(0, f"{total_value:.0f}")
            self.calculate()   # сразу показываем итог с новыми данными

    def select_asset(self, ticker):
        """Показать внизу информацию об активе: историю покупок/продаж
        с датами и прибылью/убытком, а также поля для новой сделки."""
        self.selected_ticker = ticker
        self.info_hint.pack_forget()
        pos = next((p for p in self.data["positions"]
                    if p["ticker"] == ticker), None)
        q, _, kind, _ = self.quotes.get(ticker, (None, None, None, None))
        if not kind and pos:
            kind = pos.get("kind")
        title = ticker
        if pos:
            title += f" — в портфеле {pos['qty']} шт."
        if kind == "Облигации":
            title += "  (цены — в % от номинала)"
        self.info_title.config(text=title)
        for w in self.info_history.winfo_children():
            w.destroy()
        records = inv.asset_history(self.data, ticker)
        if not records:
            tk.Label(self.info_history, text="Сделок пока не было.",
                     font=("Arial", 8), fg="#999", bg="#fafafa").grid(
                row=0, column=0, sticky="w")
            return
        headers = ["Дата", "Действие", "Кол-во", "Цена", "Прибыль/убыток"]
        for c, h in enumerate(headers):
            tk.Label(self.info_history, text=h, font=("Arial", 8, "bold"),
                     fg="#555", bg="#fafafa").grid(row=0, column=c,
                                                   sticky="w", padx=(0, 14))
        for r, rec in enumerate(reversed(records), start=1):
            is_sell = rec.get("action") == "sell"
            pl = rec.get("pl")
            if pl is None:
                pl_txt, pl_color = "—", "#777"
            else:
                pl_txt = f"{pl:+,.0f} ₽".replace(",", " ")
                pl_color = "#2e7d32" if pl >= 0 else "#c62828"
            tk.Label(self.info_history, text=rec.get("date", ""),
                     font=("Arial", 8), bg="#fafafa").grid(
                row=r, column=0, sticky="w", padx=(0, 14))
            tk.Label(self.info_history,
                     text="Продажа" if is_sell else "Покупка",
                     font=("Arial", 8), fg="#f57c00" if is_sell else "#2e7d32",
                     bg="#fafafa").grid(row=r, column=1, sticky="w",
                                        padx=(0, 14))
            tk.Label(self.info_history, text=str(rec.get("qty", "")),
                     font=("Arial", 8), bg="#fafafa").grid(
                row=r, column=2, sticky="w", padx=(0, 14))
            tk.Label(self.info_history,
                     text=f"{rec.get('price', 0):,.2f}".replace(",", " "),
                     font=("Arial", 8), bg="#fafafa").grid(
                row=r, column=3, sticky="w", padx=(0, 14))
            tk.Label(self.info_history, text=pl_txt, font=("Arial", 8, "bold"),
                     fg=pl_color, bg="#fafafa").grid(row=r, column=4,
                                                     sticky="w", padx=(0, 14))

    def _read_trade_inputs(self):
        """Кол-во и цена из полей панели; (None, None) при ошибке ввода."""
        try:
            qty = int(self.trade_qty.get().strip())
            price = float(self.trade_price.get().strip().replace(",", "."))
        except ValueError:
            messagebox.showinfo(
                "Проверьте ввод",
                "Количество — целое число, цена — число.\n"
                "Например: 10 и 296.50", parent=self)
            return None, None
        if qty <= 0 or price <= 0:
            messagebox.showinfo("Проверьте ввод",
                                "Количество и цена должны быть больше нуля.",
                                parent=self)
            return None, None
        return qty, price

    def info_buy(self):
        """Купить выбранный актив: кол-во и цена из полей внизу."""
        if not self.selected_ticker:
            messagebox.showinfo("Выберите актив",
                                "Сначала кликните по тикеру в таблице.",
                                parent=self)
            return
        qty, price = self._read_trade_inputs()
        if qty is None:
            return
        inv.add_position(self.data, self.selected_ticker, qty, price)
        inv.save_portfolio(self.data)
        self.trade_qty.delete(0, "end")
        self.trade_price.delete(0, "end")
        self.render_positions()
        self.select_asset(self.selected_ticker)   # обновляем историю
        self._fit_window_size()
        self.after(100, self.refresh_quotes)

    def info_sell(self):
        """Продать выбранный актив: кол-во и цена из полей внизу."""
        ticker = self.selected_ticker
        if not ticker:
            messagebox.showinfo("Выберите актив",
                                "Сначала кликните по тикеру в таблице.",
                                parent=self)
            return
        pos = next((p for p in self.data["positions"]
                    if p["ticker"] == ticker), None)
        if pos is None:
            messagebox.showinfo("Нет актива", f"{ticker} нет в портфеле.",
                                parent=self)
            return
        qty, price = self._read_trade_inputs()
        if qty is None:
            return
        if qty > pos["qty"]:
            messagebox.showinfo(
                "Проверьте ввод",
                f"В портфеле только {pos['qty']} шт. {ticker}.",
                parent=self)
            return
        q, _, kind, face = self.quotes.get(ticker, (None, None, None, None))
        if not kind:
            kind = pos.get("kind")
        inv.sell_position(self.data, ticker, qty, price, kind, face)
        inv.save_portfolio(self.data)
        self.trade_qty.delete(0, "end")
        self.trade_price.delete(0, "end")
        if pos["qty"] - qty <= 0:
            # продано всё — позиция удалена, чистим кэши
            self.quotes.pop(ticker, None)
            self.expected.pop(ticker, None)
        self.render_positions()
        if pos["qty"] - qty > 0:
            self.select_asset(ticker)
        self._fit_window_size()
        self.after(100, self.refresh_quotes)

    def refresh_quotes(self):
        """Обновить статусы всех активов: цены MOEX + прибыль/убыток + диаграмма."""
        self.status_label.config(text="Обновляю курсы MOEX…")
        self.update_idletasks()
        if not self.data["positions"]:
            self.status_label.config(text="Портфель пуст")
            return
        self.quotes = inv.refresh_positions(self.data)
        # прогноз берём из кэша доходностей (без обращения к сети);
        # свежие значения появляются после «📈 Доходность портфеля»
        cache = inv.load_returns_cache()
        self.expected = {
            pos["ticker"]: (cache.get(pos["ticker"]) or {}).get("cagr")
            for pos in self.data["positions"]}
        ok = sum(1 for q in self.quotes.values() if q[0] is not None)
        failed = [t for t, q in self.quotes.items() if q[0] is None]
        msg = f"Обновлено {ok} из {len(self.quotes)}"
        if failed:
            msg += f" (не найдены: {', '.join(failed)})"
        self.status_label.config(text=msg)
        self.render_positions()
        self._fit_window_size()
        self.update_passive()

    def _build_calculator(self):
        calc = tk.LabelFrame(self, text=" Калькулятор сложного процента ",
                             font=("Arial", 10, "bold"), bg="#fafafa", fg="#444")
        calc.pack(fill="x", padx=10, pady=(5, 10))
        row = tk.Frame(calc, bg="#fafafa")
        row.pack(fill="x", padx=8, pady=6)
        fields = [("Стартовая сумма, ₽", "100000"),
                  ("Пополнение в месяц, ₽", "10000"),
                  ("Доходность, % годовых", "12"),
                  ("Срок, лет", "10")]
        self.calc_entries = []
        for text, default in fields:
            box = tk.Frame(row, bg="#fafafa")
            box.pack(side="left", padx=6)
            tk.Label(box, text=text, font=("Arial", 8), fg="#666",
                     bg="#fafafa").pack()
            entry = tk.Entry(box, width=11)
            entry.insert(0, default)
            entry.bind("<Return>", lambda e: self.calculate())
            entry.pack()
            self.calc_entries.append(entry)
        btn_row = tk.Frame(calc, bg="#fafafa")
        btn_row.pack(fill="x", padx=8, pady=(0, 8))
        tk.Button(btn_row, text="Рассчитать", font=("Arial", 9, "bold"),
                  relief="flat", bg="#4caf50", fg="white", padx=12,
                  cursor="hand2", command=self.calculate).pack(side="left")
        self.calc_result = tk.Label(btn_row, text="", font=("Arial", 10),
                                    bg="#fafafa", fg="#2e7d32")
        self.calc_result.pack(side="left", padx=12)
        self.calc_passive = tk.Label(calc, text="", font=("Arial", 9),
                                     bg="#fafafa", fg="#6a1b9a")
        self.calc_passive.pack(anchor="w", padx=8, pady=(0, 6))

    def calculate(self):
        try:
            vals = []
            for entry in self.calc_entries:
                text = entry.get().strip().replace(" ", "").replace(",", ".")
                vals.append(float(text))
            initial, monthly, rate, years = vals
            if initial < 0 or monthly < 0 or rate < 0 or years <= 0:
                raise ValueError
        except ValueError:
            messagebox.showinfo("Проверьте ввод",
                                "Все поля — неотрицательные числа, срок больше 0.",
                                parent=self)
            return
        final, invested, earned = inv.compound_interest(initial, monthly, rate, years)
        years_txt = f"{years:g}".replace(".", ",")
        self.calc_result.config(
            text=f"Через {years_txt} г.: {final:,.0f} ₽".replace(",", " ")
                 + f"   •   вложено: {invested:,.0f} ₽".replace(",", " ")
                 + f"   •   заработано: {earned:,.0f} ₽".replace(",", " ")
        )
        gross = final * rate / 100
        # пассивный доход с итоговой суммы: капитал final за год
        # приносит доход по ставке калькулятора; вычитаем налог
        # и учитываем покупательную способность (инфляцию)
        net, real = inv.net_passive_income(gross, final,
                                           self.tax_pct, self.inflation_pct)
        self.calc_passive.config(
            text=(f"Пассивный доход с итоговой суммы: {net:,.0f} ₽/год "
                  f"после НДФЛ; с учётом инфляции — {real:,.0f} ₽"
                  ).replace(",", " ")
        )


class PillarsPanel(tk.LabelFrame):
    """Панель «трёх столбов» 50/25/25 в правом столбце окна
    инвестиций: текущие доли против цели, разбивка рублёвого
    столба по секторам (4 сектора + денежный рынок по 10%),
    предупреждение о просадке и ручная привязка облигаций."""
    DEVIATION_WARN = 2.0   # п.п. недобора до цели — считаем «просел»

    def __init__(self, master, ivw):
        super().__init__(master, text=" Три столба — 50/25/25 ",
                         font=("Arial", 9, "bold"), bg="#fafafa", fg="#444")
        self.ivw = ivw
        self.body = tk.Frame(self, bg="#fafafa")
        self.body.pack(fill="both", expand=True, padx=6, pady=4)
        self.render()

    def render(self):
        for w in self.body.winfo_children():
            w.destroy()
        alloc = inv.pillar_allocation(self.ivw.data, self.ivw.quotes)
        total = alloc["total"]

        def rub(v):
            return f"{v:,.0f} ₽".replace(",", " ")

        # шапка таблицы: столб / цель / факт / отклонение
        grid = tk.Frame(self.body, bg="#fafafa")
        grid.pack(fill="x")
        for c, h in enumerate(("Столб", "Цель", "Факт", "Откл.")):
            tk.Label(grid, text=h, font=("Arial", 8, "bold"), bg="#fafafa",
                     fg="#555").grid(row=0, column=c, padx=4,
                                     pady=(2, 1), sticky="w")
        fell = []
        r = 1
        for key, target in inv.PILLAR_TARGETS.items():
            info = alloc["pillars"][key]
            dev = info["pct"] - target
            color = "#2e7d32" if dev >= 0 else (
                "#c62828" if -dev >= self.DEVIATION_WARN else "#f9a825")
            tk.Label(grid, text=inv.PILLAR_NAMES[key], font=("Arial", 8, "bold"),
                     bg="#fafafa").grid(row=r, column=0, padx=4, sticky="w")
            tk.Label(grid, text=f"{target}%", font=("Arial", 8),
                     bg="#fafafa").grid(row=r, column=1, padx=4, sticky="e")
            tk.Label(grid, text=f"{info['pct']:.1f}%", font=("Arial", 8, "bold"),
                     fg=color, bg="#fafafa").grid(row=r, column=2, padx=4,
                                                   sticky="e")
            tk.Label(grid, text=f"{dev:+.1f}", font=("Arial", 8),
                     fg=color, bg="#fafafa").grid(row=r, column=3, padx=4,
                                                  sticky="e")
            if dev < -self.DEVIATION_WARN:
                need = total * target / 100 - info["value"]
                fell.append(f"{inv.PILLAR_NAMES[key]}: {info['pct']:.1f}%"
                            f" (не хватает ≈{rub(max(0, need))})")
            r += 1
        if fell:
            tk.Label(self.body, font=("Arial", 8, "bold"), fg="#c62828",
                     bg="#fafafa", justify="left",
                     text="⚠ Просел, докупить при пополнении:\n"
                          + "\n".join("• " + f for f in fell)).pack(
                anchor="w", pady=(4, 2))
        if alloc["unclassified"]:
            tk.Label(self.body, font=("Arial", 8), fg="#f9a825",
                     bg="#fafafa", justify="left",
                     text="Не привязаны к столбу (задайте вручную):"
                     ).pack(anchor="w", pady=(4, 1))
            for ticker, value, kind in alloc["unclassified"]:
                row = tk.Frame(self.body, bg="#fafafa")
                row.pack(fill="x")
                tk.Label(row, text=f"{ticker} — {rub(value)}",
                         font=("Arial", 8), bg="#fafafa").pack(side="left")
                for k, name in inv.PILLAR_NAMES.items():
                    tk.Button(row, text=name, font=("Arial", 7), relief="flat",
                              bg="#2196f3", fg="white", padx=4, cursor="hand2",
                              command=lambda t=ticker, k=k:
                              self.assign_pillar(t, k)).pack(
                        side="left", padx=(4, 0), pady=1)
        sf = tk.Frame(self.body, bg="#fafafa")
        sf.pack(fill="x", pady=(4, 0))
        tk.Label(sf, text="Секторы рублёвого (цель 10%)",
                 font=("Arial", 8, "bold"), bg="#fafafa",
                 fg="#555").grid(row=0, column=0, columnspan=2,
                                 padx=4, pady=(2, 1), sticky="w")
        sectors = ["Финансы", "Нефтегаз", "Технологии",
                   "Металлургия и ритейл", "Денежный рынок"]
        for rr, s in enumerate(sectors, start=1):
            info = alloc["sectors"].get(s, {"value": 0.0, "pct": 0.0})
            dev = info["pct"] - inv.SECTOR_TARGET_PCT
            color = "#2e7d32" if dev >= 0 else (
                "#c62828" if -dev >= self.DEVIATION_WARN else "#f9a825")
            tk.Label(sf, text=s, font=("Arial", 8), bg="#fafafa").grid(
                row=rr, column=0, padx=4, sticky="w")
            tk.Label(sf, text=f"{info['pct']:.1f}% ({dev:+.1f})",
                     font=("Arial", 8), fg=color, bg="#fafafa").grid(
                row=rr, column=1, padx=4, sticky="e")
        extra = [s for s in alloc["sectors"] if s not in sectors]
        if extra:
            tk.Label(sf, font=("Arial", 7), fg="#777", bg="#fafafa",
                     text="Вне секторов: " + ", ".join(sorted(extra))
                     ).grid(row=len(sectors) + 1, column=0, columnspan=2,
                            padx=4, sticky="w")

    def assign_pillar(self, ticker, pillar):
        pos = next((p for p in self.ivw.data["positions"]
                    if p["ticker"] == ticker), None)
        if pos is None:
            return
        pos["pillar"] = pillar
        inv.save_portfolio(self.ivw.data)
        # render_positions перерисует и таблицу, и эту панель
        self.ivw.render_positions()