# investments_ui.py — окно портфеля: позиции, статусы активов, круговая диаграмма

import tkinter as tk
from tkinter import messagebox

import investments as inv


class PieChart(tk.Canvas):
    """Круговая диаграмма долей активов (tk Canvas, без библиотек)."""

    COLORS = ["#4caf50", "#2196f3", "#ff9800", "#9c27b0",
              "#e91e63", "#00bcd4", "#795548", "#607d8b"]

    def __init__(self, master, width=200, height=200):
        super().__init__(master, width=width, height=height + 90, bg="#fafafa",
                         highlightthickness=0)
        self.w = width
        self.h = height

    def draw(self, shares):
        """shares: список [(вид актива, стоимость ₽)] без нулевых."""
        self.delete("all")
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
            start += extent
        # легенда под диаграммой
        y = self.h + 10
        for i, (label, value) in enumerate(shares):
            color = self.COLORS[i % len(self.COLORS)]
            pct = value / total * 100
            self.create_rectangle(6, y, 18, y + 12, fill=color, outline="")
            self.create_text(24, y + 6, anchor="w", font=("Arial", 8),
                             text=f"{label}: {pct:.1f}%"
                                  f" ({value:,.0f} ₽)".replace(",", " "))
            y += 16


class InvestmentsWindow(tk.Toplevel):
    """Отдельное окно: позиции, обновление котировок MOEX,
    круговая диаграмма структуры портфеля и калькулятор."""

    def __init__(self, master):
        super().__init__(master)
        self.title("Инвестиции")
        self.geometry("980x680")
        self.configure(bg="#fafafa")
        self.data = inv.load_portfolio()
        self.quotes = {}   # "TICKER" -> (price, updated, kind, facevalue)
        self.expected = {}  # "TICKER" -> среднегодовая доходность (для прогноза)

        self._build_portfolio()
        self._build_calculator()
        self.render_positions()
        # сразу обновляем информацию по всем активам при открытии окна
        self.after(100, self.refresh_quotes)

    # ================= портфель =================
    def _build_portfolio(self):
        pf = tk.LabelFrame(self, text=" Портфель ", font=("Arial", 10, "bold"),
                           bg="#fafafa", fg="#444")
        pf.pack(fill="both", expand=True, padx=10, pady=(10, 5))

        # строка добавления позиции
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

        # контент: таблица слева + круговая диаграмма справа
        content = tk.Frame(pf, bg="#fafafa")
        content.pack(fill="both", expand=True, padx=8, pady=(0, 4))
        self.table = tk.Frame(content, bg="#fafafa")
        self.table.pack(side="left", fill="both", expand=True)
        pie_col = tk.Frame(content, bg="#fafafa")
        pie_col.pack(side="right", padx=(14, 4), anchor="n")
        tk.Label(pie_col, text="Структура портфеля", font=("Arial", 9, "bold"),
                 bg="#fafafa", fg="#555").pack()
        self.pie = PieChart(pie_col, width=200, height=200)
        self.pie.pack()

        # кнопка обновления статусов активов
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

    def render_positions(self):
        for w in self.table.winfo_children():
            w.destroy()
        headers = ["Тикер", "Вид", "Кол-во", "Цена покупки", "Текущая цена",
                   "Прогноз", "Стоимость", "Прибыль/убыток", ""]
        for col, h in enumerate(headers):
            tk.Label(self.table, text=h, font=("Arial", 9, "bold"), bg="#fafafa",
                     fg="#555").grid(row=0, column=col, padx=6, sticky="w")

        if not self.data["positions"]:
            tk.Label(self.table, text="Позиций пока нет — добавьте первую сверху.",
                     font=("Arial", 9), fg="#888", bg="#fafafa").grid(
                row=1, column=0, columnspan=9, pady=8, sticky="w")
            self.pie.draw([])
            return

        total_value = total_pl = total_invested = 0
        has_price = False
        kind_values = {}   # вид актива -> стоимость (для круговой диаграммы)
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
            if st["invested"]:
                total_invested += st["invested"]

            display = pos["ticker"]
            tk.Label(self.table, text=display, font=("Arial", 9, "bold"),
                     bg="#fafafa").grid(row=i, column=0, padx=6, sticky="w")
            # ячейка «Вид» — кликом открывается меню выбора вида актива
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
            price_txt = f"{price:.2f} %" if kind == "Облигации" \
                else (f"{price:.2f}" if price is not None else "—")
            tk.Label(self.table, text=price_txt, bg="#fafafa").grid(
                row=i, column=4, padx=6, sticky="e")
            # консенсус-маркер: Покупать/Держать/Продавать
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
            del_btn = tk.Label(self.table, text="✕", fg="#999", cursor="hand2")
            del_btn.grid(row=i, column=8, padx=4)
            del_btn.bind("<Button-1>", lambda e, t=pos["ticker"]: self.remove_position(t))

        # итоговая строка
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

        # круговая диаграмма: доли видов активов в портфеле
        shares = sorted(kind_values.items(), key=lambda kv: -kv[1])
        self.pie.draw(shares)

    # ---- действия ----
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
        # резолвим пользовательский ввод в код MOEX (SBER, «ОФЗ 26245» и т.д.)
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
        # сразу подтягиваем цену нового актива
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
                # вид в кэше котировок тоже обновляем, чтобы диаграмма
                # перерисовалась без нового запроса к бирже
                auto_kind = q[2]
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
        menu.tk_popup(self.winfo_pointerx(), self.winfo_pointery())

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

        # подставляем результат в калькулятор сложного процента:
        # доходность — в поле «Доходность, % годовых»,
        # стартовая сумма — общая стоимость портфеля
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

    def remove_position(self, ticker):
        if messagebox.askyesno("Удалить", f"Удалить позицию {ticker}?", parent=self):
            inv.delete_position(self.data, ticker)
            inv.save_portfolio(self.data)
            self.quotes.pop(ticker, None)
            self.render_positions()

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

    # ================= калькулятор сложного процента =================
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