import datetime as dt
import tkinter as tk
from tkinter import ttk, simpledialog, messagebox
import DataHandler as DH
import budget
from habit_card import HabitCard
from investments_ui import InvestmentsWindow

MONTHS = ["янв", "фев", "мар", "апр", "май", "июн",
          "июл", "авг", "сен", "окт", "ноя", "дек"]
MONTHS_FULL = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
               "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь",
               "Декабрь"]


class BudgetApp(tk.Tk):
    """Главное окно: модуль «Доходы/расходы». Планировщик задач и
    Инвестиции открываются отдельными окнами по кнопкам справа."""

    def __init__(self):
        super().__init__()
        self.title("Доходы / расходы")
        self.configure(bg="#fafafa")
        self.data = budget.load_budget()
        today = dt.date.today()
        self.sel_year, self.sel_month = today.year, today.month
        top = tk.Frame(self, bg="#fafafa")
        top.pack(fill="x", padx=10, pady=(10, 0))
        tk.Label(top, text="Доходы / расходы", font=("Arial", 16, "bold"),
                 bg="#fafafa").pack(side="left")
        self.nav = tk.Frame(top, bg="#fafafa")
        self.nav.pack(side="right")
        tk.Button(self.nav, text="💰 Инвестиции", font=("Arial", 10, "bold"),
                  relief="flat", bg="#ff9800", fg="white", padx=10, pady=3,
                  cursor="hand2",
                  command=self.open_investments).pack(side="right")
        tk.Button(self.nav, text="📋 Планировщик задач",
                  font=("Arial", 10, "bold"), relief="flat", bg="#2196f3",
                  fg="white", padx=10, pady=3, cursor="hand2",
                  command=self.open_planner).pack(side="right", padx=(0, 8))
        body = tk.Frame(self, bg="#fafafa")
        body.pack(fill="both", expand=True, padx=10, pady=10)
        # календарь месяцев — сверху над списком трат
        cal = tk.LabelFrame(body, text=" Месяцы ",
                            font=("Arial", 9, "bold"),
                            bg="#fafafa", fg="#444")
        cal.pack(fill="x")
        top_row = tk.Frame(cal, bg="#fafafa")
        top_row.pack(fill="x", padx=6, pady=(6, 0))
        tk.Button(top_row, text="‹ добавить месяц", font=("Arial", 8),
                  relief="flat", bg="#9e9e9e", fg="white", padx=8,
                  cursor="hand2",
                  command=self.add_month_back).pack(side="left")
        tk.Label(top_row, font=("Arial", 8), fg="#777", bg="#fafafa",
                 text="— расширить календарь на месяц назад "
                      "(например, заполнить прошлый месяц)").pack(
            side="left", padx=8)
        self.months_frame = tk.Frame(cal, bg="#fafafa")
        self.months_frame.pack(fill="x", padx=6, pady=6)
        self.month_view = tk.Frame(body, bg="#fafafa")
        self.month_view.pack(fill="both", expand=True, pady=(8, 0))
        self.render_months()
        self.render_month()
        # один обработчик колеса на всё окно: решает, скроллить ли
        # список статей, по положению курсора
        self.bind_all("<MouseWheel>", self._on_items_wheel)
        self._fit_size()

    def _fit_size(self):
        """Подогнать окно под содержимое: все блоки месяца, включая
        строку «Свободные деньги», должны быть видны целиком."""
        self.update_idletasks()
        w = max(self.winfo_reqwidth(), 720)
        h = min(self.winfo_reqheight(), self.winfo_screenheight() - 60)
        self.geometry(f"{w}x{h}")

    def _on_items_wheel(self, event):
        """Скролл блоков статей (обязательных и необязательных),
        если курсор над ними. Событие приходит на виджет под
        курсором (поле ввода, подпись), поэтому поднимаемся по
        цепочке родителей до холста блока."""
        for cv in (getattr(self, "items_canvas", None),
                   getattr(self, "opt_canvas", None)):
            if cv is None:
                continue
            w = cv.winfo_containing(event.x_root, event.y_root)
            while w is not None:
                if w is cv:
                    cv.yview_scroll(
                        int(-1 * (event.delta / 120)), "units")
                    return
                parent = w.master
                if parent is w:   # дошли до корня окна
                    break
                w = parent

    # --- календарь месяцев: один квадратик — один месяц ---
    def render_months(self):
        for w in self.months_frame.winfo_children():
            w.destroy()
        months = budget.month_list(self.data)
        sel_key = budget.month_key(self.sel_year, self.sel_month)
        for i, (y, m) in enumerate(months):
            key = budget.month_key(y, m)
            done = budget.month_done(self.data, key)
            is_sel = key == sel_key
            # выполненный месяц — зелёный, выбранный — с синей рамкой
            bg = "#2e7d32" if done else "#eeeeee"
            fg = "white" if done else "#333"
            cell = tk.Frame(self.months_frame, bg="#fafafa",
                            highlightbackground="#2196f3" if is_sel else "#fafafa",
                            highlightthickness=2 if is_sel else 0)
            cell.grid(row=i // 12, column=i % 12, padx=3, pady=3)
            lbl = tk.Label(cell, text=f"{MONTHS[m - 1]}\n{y % 100:02d}",
                           font=("Arial", 9, "bold"), bg=bg, fg=fg,
                           width=4, pady=4, cursor="hand2")
            lbl.pack()
            lbl.bind("<Button-1>",
                     lambda e, y=y, m=m: self.select_month(y, m))

    def select_month(self, year, month):
        self.sel_year, self.sel_month = year, month
        self.render_months()
        self.render_month()

    def add_month_back(self):
        """Расширить календарь на месяц назад и открыть этот месяц —
        так можно заполнить расчётный лист за прошлый месяц."""
        key = budget.add_month_back(self.data)
        budget.save_budget(self.data)
        y, m = int(key[:4]), int(key[5:])
        self.sel_year, self.sel_month = y, m
        self.render_months()
        self.render_month()

    # --- данные выбранного месяца ---
    def render_month(self):
        for w in self.month_view.winfo_children():
            w.destroy()
        key = budget.month_key(self.sel_year, self.sel_month)
        mdata = budget.month_data(self.data, key)
        frame = tk.LabelFrame(
            self.month_view, text=f" {MONTHS_FULL[self.sel_month - 1]} "
                                 f"{self.sel_year} ",
            font=("Arial", 10, "bold"), bg="#fafafa", fg="#444")
        frame.pack(fill="both", expand=True)
        income_row = tk.Frame(frame, bg="#fafafa")
        income_row.pack(fill="x", padx=8, pady=8)
        # зп приходит дважды: аванс 10-го (сумма известна из
        # расчётного листка 9-го) и остаток 25-го
        tk.Label(income_row, text="Аванс (10-го), ₽:",
                 font=("Arial", 10, "bold"), bg="#fafafa").pack(side="left")
        self.income10_entry = tk.Entry(income_row, width=11,
                                       font=("Arial", 10))
        self.income10_entry.insert(0, str(mdata["income_10"] or ""))
        self.income10_entry.pack(side="left", padx=(6, 14))
        tk.Label(income_row, text="ЗП (25-го), ₽:", font=("Arial", 10, "bold"),
                 bg="#fafafa").pack(side="left")
        self.income25_entry = tk.Entry(income_row, width=11,
                                       font=("Arial", 10))
        self.income25_entry.insert(0, str(mdata["income_25"] or ""))
        self.income25_entry.pack(side="left", padx=(6, 14))
        for entry in (self.income10_entry, self.income25_entry):
            entry.bind("<Return>", lambda _e: self.save_income())
            entry.bind("<FocusOut>", lambda _e: self.save_income())
        self.income_total_lbl = tk.Label(
            income_row, font=("Arial", 10, "bold"), fg="#2e7d32",
            bg="#fafafa", text=(f"Итого: "
                                 f"{budget.income_total(mdata):,.0f} ₽"
                                 ).replace(",", " "))
        self.income_total_lbl.pack(side="right")

        # --- статьи расходов с планом (прокручиваются, если
        # список длиннее отведённого места) ---
        items_box = tk.LabelFrame(frame, text=" Статьи с планом ",
                                  font=("Arial", 9, "bold"), bg="#fafafa",
                                  fg="#444")
        items_box.pack(fill="both", expand=True, padx=8, pady=4)
        wrap = tk.Frame(items_box, bg="#fafafa")
        wrap.pack(fill="both", expand=True)
        self.items_canvas = tk.Canvas(wrap, bg="#fafafa",
                                      highlightthickness=0)
        items_scroll = ttk.Scrollbar(wrap, orient="vertical",
                                     command=self.items_canvas.yview)
        items_inner = tk.Frame(self.items_canvas, bg="#fafafa")
        items_inner.bind(
            "<Configure>",
            lambda e: self.items_canvas.configure(
                scrollregion=self.items_canvas.bbox("all")))
        self.items_window = self.items_canvas.create_window(
            (0, 0), window=items_inner, anchor="nw")
        self.items_canvas.bind(
            "<Configure>",
            lambda e: self.items_canvas.itemconfig(
                self.items_window, width=self.items_canvas.winfo_width()))
        self.items_canvas.configure(yscrollcommand=items_scroll.set)
        self.items_canvas.pack(side="left", fill="both", expand=True)
        items_scroll.pack(side="right", fill="y")
        plan_items = [i for i in self.data["items"]
                      if not i.get("optional")]
        if not plan_items:
            tk.Label(items_inner, text="Статей пока нет — добавьте первую снизу.",
                     font=("Arial", 9), fg="#888", bg="#fafafa").pack(pady=6)
        for item in plan_items:
            self._render_item(items_inner, item, mdata, key)
        add_row = tk.Frame(items_box, bg="#fafafa")
        add_row.pack(fill="x", padx=6, pady=6)
        tk.Label(add_row, text="Статья:", font=("Arial", 9),
                 bg="#fafafa").pack(side="left")
        self.new_item_entry = tk.Entry(add_row, width=16)
        self.new_item_entry.pack(side="left", padx=(4, 10))
        tk.Label(add_row, text="План на месяц, ₽:", font=("Arial", 9),
                 bg="#fafafa").pack(side="left")
        self.new_plan_entry = tk.Entry(add_row, width=10)
        self.new_plan_entry.pack(side="left", padx=(4, 10))
        self.new_item_entry.bind("<Return>", lambda _e: self.add_item())
        self.new_plan_entry.bind("<Return>", lambda _e: self.add_item())
        tk.Button(add_row, text="＋ статья", font=("Arial", 9, "bold"),
                  relief="flat", bg="#4caf50", fg="white", padx=10,
                  cursor="hand2", command=self.add_item).pack(side="left")

        # --- необязательные траты: та же логика (план, суммы,
        # красный/серый), но на закрытие месяца не влияют ---
        opt_box = tk.LabelFrame(frame, text=" Необязательные траты ",
                                font=("Arial", 9, "bold"), bg="#fafafa",
                                fg="#6a1b9a")
        # блок компактный: не растягивается на всё свободное место,
        # лишние статьи прокручиваются внутри
        opt_box.pack(fill="x", padx=8, pady=4)
        opt_wrap = tk.Frame(opt_box, bg="#fafafa")
        opt_wrap.pack(fill="x")
        self.opt_canvas = tk.Canvas(opt_wrap, bg="#fafafa",
                                    highlightthickness=0, height=110)
        opt_scroll = ttk.Scrollbar(opt_wrap, orient="vertical",
                                   command=self.opt_canvas.yview)
        opt_inner = tk.Frame(self.opt_canvas, bg="#fafafa")
        opt_inner.bind(
            "<Configure>",
            lambda e: self.opt_canvas.configure(
                scrollregion=self.opt_canvas.bbox("all")))
        self.opt_window = self.opt_canvas.create_window(
            (0, 0), window=opt_inner, anchor="nw")
        self.opt_canvas.bind(
            "<Configure>",
            lambda e: self.opt_canvas.itemconfig(
                self.opt_window, width=self.opt_canvas.winfo_width()))
        self.opt_canvas.configure(yscrollcommand=opt_scroll.set)
        self.opt_canvas.pack(side="left", fill="both", expand=True)
        opt_scroll.pack(side="right", fill="y")
        opt_items = [i for i in self.data["items"] if i.get("optional")]
        if not opt_items:
            tk.Label(opt_inner,
                     text="Необязательных трат нет — добавьте снизу.",
                     font=("Arial", 9), fg="#888", bg="#fafafa").pack(pady=6)
        for item in opt_items:
            self._render_item(opt_inner, item, mdata, key)
        opt_add = tk.Frame(opt_box, bg="#fafafa")
        opt_add.pack(fill="x", padx=6, pady=6)
        tk.Label(opt_add, text="Статья:", font=("Arial", 9),
                 bg="#fafafa").pack(side="left")
        self.opt_item_entry = tk.Entry(opt_add, width=16)
        self.opt_item_entry.pack(side="left", padx=(4, 10))
        tk.Label(opt_add, text="План на месяц, ₽:", font=("Arial", 9),
                 bg="#fafafa").pack(side="left")
        self.opt_plan_entry = tk.Entry(opt_add, width=10)
        self.opt_plan_entry.pack(side="left", padx=(4, 10))
        self.opt_item_entry.bind(
            "<Return>", lambda _e: self.add_item(optional=True))
        self.opt_plan_entry.bind(
            "<Return>", lambda _e: self.add_item(optional=True))
        tk.Button(opt_add, text="＋ необязательная",
                  font=("Arial", 9, "bold"), relief="flat",
                  bg="#6a1b9a", fg="white", padx=10, cursor="hand2",
                  command=lambda: self.add_item(optional=True)).pack(
            side="left")

        # --- разовые траты: актуальны только в выбранном месяце ---
        one_box = tk.LabelFrame(frame, text=" Разовые траты этого месяца ",
                                font=("Arial", 9, "bold"), bg="#fafafa",
                                fg="#6a1b9a")
        one_box.pack(fill="x", padx=8, pady=4)
        if not mdata["oneoff"]:
            tk.Label(one_box, text="Нет разовых трат в этом месяце.",
                     font=("Arial", 8), fg="#888", bg="#fafafa").pack(
                anchor="w", padx=6, pady=4)
        for one in mdata["oneoff"]:
            row = tk.Frame(one_box, bg="#fafafa")
            row.pack(fill="x", padx=6, pady=1)
            tk.Label(row, text=f"{one['name']} — "
                                f"{one['amount']:,.0f} ₽".replace(",", " "),
                     font=("Arial", 9), fg="#6a1b9a",
                     bg="#fafafa").pack(side="left")
            del_lbl = tk.Label(row, text="✕", fg="#999", cursor="hand2",
                               font=("Arial", 9), bg="#fafafa")
            del_lbl.pack(side="right")
            del_lbl.bind("<Button-1>",
                         lambda e, o=one: self.delete_oneoff(o))
        one_add = tk.Frame(one_box, bg="#fafafa")
        one_add.pack(fill="x", padx=6, pady=6)
        tk.Label(one_add, text="Название:", font=("Arial", 8),
                 bg="#fafafa").pack(side="left")
        self.one_name_entry = tk.Entry(one_add, width=16)
        self.one_name_entry.pack(side="left", padx=(4, 8))
        tk.Label(one_add, text="Сумма, ₽:", font=("Arial", 8),
                 bg="#fafafa").pack(side="left")
        self.one_amount_entry = tk.Entry(one_add, width=9)
        self.one_amount_entry.pack(side="left", padx=(4, 8))
        self.one_name_entry.bind("<Return>", lambda _e: self.add_oneoff())
        self.one_amount_entry.bind("<Return>", lambda _e: self.add_oneoff())
        tk.Button(one_add, text="＋ разовая", font=("Arial", 8, "bold"),
                  relief="flat", bg="#6a1b9a", fg="white", padx=8,
                  cursor="hand2", command=self.add_oneoff).pack(side="left")

        # остаток месяца — «Свободные деньги»
        free = budget.free_money(self.data, mdata)
        spent = budget.month_spent(self.data, mdata)
        bottom = tk.Frame(frame, bg="#fafafa")
        bottom.pack(fill="x", padx=8, pady=(2, 8))
        tk.Label(bottom, text=f"Потрачено: {spent:,.0f} ₽".replace(",", " "),
                 font=("Arial", 10), fg="#666", bg="#fafafa").pack(side="left")
        tk.Label(bottom, font=("Arial", 11, "bold"), bg="#fafafa",
                 fg="#2e7d32" if free >= 0 else "#c62828",
                 text=(f"Свободные деньги: {free:+,.0f} ₽"
                       ).replace(",", " ")).pack(side="right")
        self._fit_size()

    def _render_item(self, parent, item, mdata, key=None):
        """Одна статья расходов. Обязательная: план, потрачено/план,
        не закрыта — горит красным; выполнена — серая зачёркнутая.
        Необязательная: зелёная <70% плана, жёлтая 70–100%,
        красная при превышении (превышение переносится на следующий
        месяц — план в нём уменьшается на перерасход)."""
        row = tk.Frame(parent, bg="#fafafa", bd=1, relief="solid")
        row.pack(fill="x", padx=6, pady=3, ipady=3)
        spent = budget.item_spent(mdata, item["name"])
        done = budget.item_done(mdata, item)
        # прогресс по плану: потрачено/план (например, 10000/20000)
        if item.get("optional") and key:
            plan = budget.optional_plan(self.data, item, key)
            carry = budget.optional_carry(self.data, item, key)
            if spent < plan * 0.7:
                fg = "#2e7d32"          # зелёный: потрачено <70%
            elif spent <= plan:
                fg = "#f9a825"          # жёлтый: 70–100% плана
            else:
                fg = "#c62828"          # красный: превышение
            status = (f"{spent:,.0f}/{plan:,.0f}"
                      ).replace(",", " ")
            if carry > 0:
                status += (f"  (перенос −{carry:,.0f})"
                           ).replace(",", " ")
            name_lbl = tk.Label(row, text=item["name"],
                                font=("Arial", 10, "bold"), fg=fg,
                                bg="#fafafa")
        else:
            fg = "#999" if done else "#c62828"
            status = (f"{spent:,.0f}/{item.get('plan') or 0:,.0f}"
                      ).replace(",", " ")
            name_lbl = tk.Label(row, text=item["name"],
                                font=("Arial", 10, "bold"), fg=fg,
                                bg="#fafafa")
            if done:
                name_lbl.config(font=("Arial", 10, "bold", "overstrike"))
        name_lbl.pack(side="left", padx=8)
        tk.Label(row, text=status, font=("Arial", 9), fg=fg,
                 bg="#fafafa").pack(side="left", padx=8)
        expense_entry = tk.Entry(row, width=9)
        expense_entry.pack(side="right", padx=(4, 2))
        expense_entry.bind("<Return>",
                           lambda _e, it=item, e=expense_entry:
                           self.add_expense(it, e))
        tk.Button(row, text="＋ расход", font=("Arial", 8), relief="flat",
                  bg="#2196f3", fg="white", padx=6, cursor="hand2",
                  command=lambda it=item, e=expense_entry:
                  self.add_expense(it, e)).pack(side="right")
        del_lbl = tk.Label(row, text="✕", fg="#999", cursor="hand2",
                           font=("Arial", 10), bg="#fafafa")
        del_lbl.pack(side="right", padx=(8, 4))
        del_lbl.bind("<Button-1>", lambda e, it=item: self.delete_item(it))
        # каждую трату по статье показываем строкой с ✕ — можно
        # убрать лишнюю, если добавил по ошибке
        for exp in [e2 for e2 in mdata["expenses"]
                    if e2["item"] == item["name"]]:
            sub = tk.Frame(parent, bg="#fafafa")
            sub.pack(fill="x", padx=24, pady=0)
            tk.Label(sub, font=("Arial", 8), fg="#777", bg="#fafafa",
                     text=f"• {exp['date']} — "
                          f"{exp['amount']:,.0f} ₽".replace(",", " ")
                     ).pack(side="left")
            dsub = tk.Label(sub, text="✕", fg="#999", cursor="hand2",
                            font=("Arial", 8), bg="#fafafa")
            dsub.pack(side="left", padx=4)
            dsub.bind("<Button-1>",
                      lambda e, x=exp: self.delete_expense(x))

    def delete_expense(self, exp):
        """Удалить одну трату по статье (например, лишнюю)."""
        key = budget.month_key(self.sel_year, self.sel_month)
        mdata = budget.month_data(self.data, key)
        if exp not in mdata["expenses"]:
            return
        mdata["expenses"].remove(exp)
        budget.save_budget(self.data)
        self.render_months()
        self.render_month()

    # --- действия ---
    def save_income(self):
        key = budget.month_key(self.sel_year, self.sel_month)
        mdata = budget.month_data(self.data, key)
        try:
            mdata["income_10"] = float(
                self.income10_entry.get().strip().replace(" ", "")
                .replace(",", ".")) if self.income10_entry.get().strip() else 0
            mdata["income_25"] = float(
                self.income25_entry.get().strip().replace(" ", "")
                .replace(",", ".")) if self.income25_entry.get().strip() else 0
        except ValueError:
            messagebox.showinfo("Проверьте ввод",
                                "Доход — число, например 70000.", parent=self)
            return
        budget.save_budget(self.data)
        self.render_month()

    def add_oneoff(self):
        name = self.one_name_entry.get().strip()
        try:
            amount = float(self.one_amount_entry.get().strip()
                           .replace(",", "."))
        except ValueError:
            messagebox.showinfo("Проверьте ввод",
                                "Сумма — число, например 3000.",
                                parent=self)
            return
        if not name or amount <= 0:
            messagebox.showinfo("Проверьте ввод",
                                "Укажите название и сумму больше 0.",
                                parent=self)
            return
        key = budget.month_key(self.sel_year, self.sel_month)
        mdata = budget.month_data(self.data, key)
        mdata["oneoff"].append(
            {"name": name, "amount": amount,
             "date": dt.date.today().isoformat()})
        budget.save_budget(self.data)
        self.render_month()

    def delete_oneoff(self, one):
        key = budget.month_key(self.sel_year, self.sel_month)
        mdata = budget.month_data(self.data, key)
        mdata["oneoff"].remove(one)
        budget.save_budget(self.data)
        self.render_month()

    def add_item(self, optional=False):
        if optional:
            name = self.opt_item_entry.get().strip()
            plan_text = self.opt_plan_entry.get()
        else:
            name = self.new_item_entry.get().strip()
            plan_text = self.new_plan_entry.get()
        try:
            plan = float(plan_text.strip().replace(",", "."))
        except ValueError:
            messagebox.showinfo("Проверьте ввод",
                                "План на месяц — число, например 20000.",
                                parent=self)
            return
        if not name or plan <= 0:
            messagebox.showinfo("Проверьте ввод",
                                "Укажите название статьи и план больше 0.",
                                parent=self)
            return
        if any(i["name"] == name for i in self.data["items"]):
            messagebox.showinfo("Уже есть",
                                f"Статья «{name}» уже в списке.", parent=self)
            return
        item = {"name": name, "plan": plan}
        if optional:
            item["optional"] = True
        self.data["items"].append(item)
        budget.save_budget(self.data)
        # набор статей изменился — перекрашиваем и календарь
        self.render_months()
        self.render_month()

    def delete_item(self, item):
        if not messagebox.askyesno("Удалить",
                                   f"Удалить статью «{item['name']}»?\n"
                                   "Внесённые траты останутся в данных.",
                                   parent=self):
            return
        self.data["items"].remove(item)
        budget.save_budget(self.data)
        self.render_months()
        self.render_month()

    def add_expense(self, item, entry):
        try:
            amount = float(entry.get().strip().replace(",", "."))
            if amount <= 0:
                raise ValueError
        except ValueError:
            messagebox.showinfo("Проверьте ввод",
                                "Сумма траты — число больше 0.", parent=self)
            return
        key = budget.month_key(self.sel_year, self.sel_month)
        mdata = budget.month_data(self.data, key)
        mdata["expenses"].append(
            {"item": item["name"], "amount": amount,
             "date": dt.date.today().isoformat()})
        budget.save_budget(self.data)
        # состояние месяца могло измениться — перекрашиваем и календарь
        self.render_months()
        self.render_month()

    def _lift_or_open(self, attr, cls):
        win = getattr(self, attr, None)
        if win is not None and win.winfo_exists():
            win.deiconify()
            win.lift()
            return
        setattr(self, attr, cls(self))

    def open_planner(self):
        self._lift_or_open("planner_window", PlannerWindow)

    def open_investments(self):
        self._lift_or_open("invest_window", InvestmentsWindow)


class PlannerWindow(tk.Toplevel):
    """Окно «Планировщик задач»: карточки привычек с календарями
    отметок (бывшее главное окно приложения)."""

    def __init__(self, master):
        super().__init__(master)
        self.title("Планировщик задач")
        self.configure(bg="#fafafa")
        self.master_app = master
        self.dh = DH.DataHandler()
        self.data = self.dh.load_data()
        today = dt.date.today()
        self.year, self.month = today.year, today.month
        self.geometry("640x720")
        container = tk.Frame(self, bg="#fafafa")
        container.pack(fill="both", expand=True, padx=10, pady=10)
        self.canvas = tk.Canvas(container, bg="#fafafa", highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical",
                                  command=self.canvas.yview)
        self.scroll_frame = tk.Frame(self.canvas, bg="#fafafa")
        self.scroll_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self.canvas_window = self.canvas.create_window(
            (0, 0), window=self.scroll_frame, anchor="nw")
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfig(
                self.canvas_window, width=self.canvas.winfo_width()),
        )
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        bottom = tk.Frame(self, bg="#fafafa")
        bottom.pack(fill="x", padx=10, pady=(0, 10))
        tk.Button(bottom, text="+ Добавить привычку",
                  font=("Arial", 11, "bold"), bg="#4caf50", fg="white",
                  relief="flat", padx=14, pady=6, cursor="hand2",
                  command=self.add_habit).pack(fill="x")
        self.render_cards()
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel,
                             add="+")

    def render_cards(self):
        for w in self.scroll_frame.winfo_children():
            w.destroy()
        if not self.data["habits"]:
            tk.Label(self.scroll_frame,
                     text="Пока нет привычек.\n"
                          "Нажмите «+ Добавить привычку» внизу.",
                     font=("Arial", 11), fg="#888", bg="#fafafa",
                     pady=40).pack()
            return
        for habit in self.data["habits"]:
            HabitCard(self.scroll_frame, self, habit).pack(
                fill="x", pady=6, padx=4)

    def add_habit(self):
        name = simpledialog.askstring("Новая привычка",
                                      "Название привычки:", parent=self)
        if name and name.strip():
            self.data["habits"].append(
                {"name": name.strip(), "dates": [], "condition": "",
                 "created": dt.date.today().isoformat()})
            self.save()
            self.render_cards()

    def save(self):
        self.dh.save_data(self.data)

    def _on_mousewheel(self, event):
        # прокручиваем список только когда курсор над этим окном:
        # bind_all срабатывает и в окне «Доходы/расходы»
        if self.canvas.winfo_containing(event.x_root,
                                        event.y_root) is self.canvas:
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")