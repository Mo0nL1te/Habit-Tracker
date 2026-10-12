import calendar
import datetime as dt
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import DataHandler as DH


CELL = 30          # размер квадратика дня
GAP = 4            # зазор между квадратами
PAD = 10           # отступы внутри карточки
WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


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


# ----------------------------- интерфейс -----------------------------

class HabitCard(tk.Frame):
    """Карточка одной привычки: заголовок, календарь месяца, статистика."""

    def __init__(self, master, app, habit):
        super().__init__(master, bd=1, relief="solid", padx=PAD, pady=PAD)
        self.app = app
        self.habit = habit  # {"name": str, "dates": ["YYYY-MM-DD", ...], "condition": str}

        header = tk.Frame(self)
        header.pack(fill="x")
        # имя привычки: двойной клик по нему открывает редактирование
        self.name_label = tk.Label(header, text=habit["name"],
                                   font=("Arial", 12, "bold"), cursor="xterm")
        self.name_label.pack(side="left")
        self.name_label.bind("<Double-Button-1>", self.rename_habit)
        # дата создания карточки (или первая известная отметка для старых)
        created = self.get_created_date()
        if created:
            tk.Label(header, text=f"с {created.strftime('%d.%m.%Y')}",
                     font=("Arial", 8), fg="#999").pack(side="left", padx=(8, 0))
        edit_hint = tk.Label(header, text="✎", fg="#999", cursor="hand2",
                             font=("Arial", 10))
        edit_hint.pack(side="left", padx=(6, 0))
        edit_hint.bind("<Button-1>", self.rename_habit)

        del_btn = tk.Label(header, text="✕", fg="#999", cursor="hand2", font=("Arial", 11))
        del_btn.pack(side="right")
        del_btn.bind("<Button-1>", self.delete_habit)

        # стрелочка раскрытия панели дополнительного условия
        self.expanded = False
        self.arrow_btn = tk.Label(header, text="▾", fg="#666", cursor="hand2",
                                  font=("Arial", 11), width=2)
        self.arrow_btn.pack(side="right", padx=(0, 4))
        self.arrow_btn.bind("<Button-1>", self.toggle_extra)

        self.calendar_widget = tk.Frame(self)
        self.calendar_widget.pack(fill="x", pady=(6, 2))

        self.stats = tk.Label(self, font=("Arial", 10), fg="#444")
        self.stats.pack(anchor="w")

        # выпадающая снизу панель дополнительного условия (скрыта по умолчанию)
        self.extra_panel = tk.Frame(self, bd=0)
        inner = tk.Frame(self.extra_panel, bg="#f5f5f5", padx=8, pady=8)
        inner.pack(fill="x", pady=(4, 0))

        # выбор типа условия
        type_row = tk.Frame(inner, bg="#f5f5f5")
        type_row.pack(fill="x")
        tk.Label(type_row, text="Тип условия:", font=("Arial", 9),
                 bg="#f5f5f5", fg="#555").pack(side="left")
        self.type_var = tk.StringVar(value=self.get_condition()["type"])
        type_box = ttk.Combobox(
            type_row, textvariable=self.type_var, state="readonly", width=22,
            values=["Текст", "Список дел", "Таблица с квадратиками"],
        )
        type_box.pack(side="left", padx=6)
        type_box.bind("<<ComboboxSelected>>", self.on_type_changed)

        # контент условия, перерисовывается при смене типа
        self.content_frame = tk.Frame(inner, bg="#f5f5f5")
        self.content_frame.pack(fill="x", pady=(4, 0))
        self._rerender_keep_scroll()

        self.year = self.app.year
        self.month = self.app.month
        self.draw_month()

    # ---- панель дополнительного условия ----
    def get_condition(self):
        """Вернуть условие привычки; старый строковый формат конвертируется."""
        cond = self.habit.get("condition")
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

    TYPE_NAMES = {"text": "Текст", "checklist": "Список дел",
                  "table": "Таблица с квадратиками"}
    TYPE_KEYS = {v: k for k, v in TYPE_NAMES.items()}

    def on_type_changed(self, event=None):
        cond = self.get_condition()
        cond["type"] = self.TYPE_KEYS[self.type_var.get()]
        self.habit["condition"] = cond
        self.app.save()
        self._rerender_keep_scroll()
        self.update_stats()

    def render_condition_ui(self):
        """Перерисовать содержимое панели под выбранный тип условия."""
        for w in self.content_frame.winfo_children():
            w.destroy()
        cond = self.get_condition()
        getattr(self, "_render_cond_" + cond["type"])(cond)

    def _rerender_keep_scroll(self):
        """Перерисовать панель, не сбрасывая прокрутку списка карточек.

        Перерисовка панели меняет scrollregion канваса, из-за чего окно
        прокрутки «прыгает» в самый верх. Запоминаем текущую позицию
        и восстанавливаем её после перерисовки.
        """
        canvas = self.app.canvas
        top_frac = canvas.yview()[0]
        self.render_condition_ui()
        canvas.after_idle(lambda: canvas.yview_moveto(top_frac))

    # ---- тип: текст ----
    def _render_cond_text(self, cond):
        entry = tk.Entry(self.content_frame, font=("Arial", 10), relief="solid", bd=1)
        entry.pack(fill="x")
        entry.insert(0, cond.get("text", ""))
        entry.bind("<FocusOut>", lambda e: self._save_text(entry))
        entry.bind("<Return>", lambda e: self._save_text(entry))

    def _save_text(self, entry):
        self.get_condition()["text"] = entry.get().strip()
        self.app.save()
        self.update_stats()

    # ---- тип: список дел ----
    def _render_cond_checklist(self, cond):
        for i, item in enumerate(cond["items"]):
            row = tk.Frame(self.content_frame, bg="#f5f5f5")
            row.pack(fill="x", pady=1)
            var = tk.BooleanVar(value=item.get("done", False))
            chk = tk.Checkbutton(row, variable=var, bg="#f5f5f5")
            chk.pack(side="left")
            chk.bind("<Button-1>", lambda e, idx=i, v=var: self._toggle_item(idx, v), add="+")
            entry = tk.Entry(row, font=("Arial", 9), relief="flat", bg="#f5f5f5")
            entry.pack(side="left", fill="x", expand=True)
            entry.insert(0, item.get("text", ""))
            entry.bind("<FocusOut>", lambda e, idx=i, en=entry: self._save_item(idx, en))
            entry.bind("<Return>", lambda e, idx=i, en=entry: self._save_item(idx, en))
            del_btn = tk.Label(row, text="✕", fg="#999", cursor="hand2", font=("Arial", 9))
            del_btn.pack(side="left", padx=2)
            del_btn.bind("<Button-1>", lambda e, idx=i: self._delete_item(idx))
        add_btn = tk.Button(self.content_frame, text="＋ пункт", font=("Arial", 9),
                            relief="flat", bg="#e0e0e0", cursor="hand2",
                            command=self._add_item)
        add_btn.pack(anchor="w", pady=(2, 0))

    def _add_item(self):
        self.get_condition()["items"].append({"text": "", "done": False})
        self.app.save()
        self._rerender_keep_scroll()

    def _toggle_item(self, idx, var):
        # состояние чекбокса меняется после обработчика — планируем отложенно
        self.after(50, lambda: self._apply_item_state(idx, var))

    def _apply_item_state(self, idx, var):
        self.get_condition()["items"][idx]["done"] = var.get()
        self.app.save()
        self.update_stats()

    def _save_item(self, idx, entry):
        self.get_condition()["items"][idx]["text"] = entry.get()
        self.app.save()

    def _delete_item(self, idx):
        del self.get_condition()["items"][idx]
        self.app.save()
        self._rerender_keep_scroll()
        self.update_stats()

    # ---- тип: таблица с квадратиками (номер + вес 1/2/3) ----
    def _render_cond_table(self, cond):
        # строка настройки: целевой вес за сутки
        goal_row = tk.Frame(self.content_frame, bg="#f5f5f5")
        goal_row.pack(fill="x", pady=(0, 3))
        tk.Label(goal_row, text="Вес за сутки (день закрасится зелёным):",
                 font=("Arial", 9), bg="#f5f5f5", fg="#555").pack(side="left")
        goal_entry = tk.Entry(goal_row, width=4, font=("Arial", 9), relief="solid", bd=1)
        goal_entry.pack(side="left", padx=4)
        goal_entry.insert(0, str(cond.get("goal", 0)))
        goal_entry.bind("<FocusOut>", lambda e: self._save_goal(goal_entry))
        goal_entry.bind("<Return>", lambda e: self._save_goal(goal_entry))
        # клики по Label/Button не уводят фокус с поля — держим свежую ссылку
        self.goal_entry = goal_entry

        # строка добавления: кнопка (вес задаётся после создания квадратика)
        add_row = tk.Frame(self.content_frame, bg="#f5f5f5")
        add_row.pack(fill="x", pady=(0, 3))
        tk.Button(add_row, text="＋ квадратик", font=("Arial", 9), relief="flat",
                  bg="#e0e0e0", cursor="hand2",
                  command=self._add_cell).pack(side="left", padx=4)

        # сетка квадратиков: номер, клик = выполнено, кнопки веса, удаление
        self._cell_widgets = []   # ссылки на виджеты каждого квадратика
        self.cells_grid = tk.Frame(self.content_frame, bg="#f5f5f5")
        self.cells_grid.pack(fill="x")
        for i, cell in enumerate(cond["cells"]):
            self._make_cell_box(self.cells_grid, i, cell)
        # при изменении ширины панели перекладываем сетку заново
        self.cells_grid.bind(
            "<Configure>",
            lambda e: self._reflow_cells(e.width),
        )

    def _make_cell_box(self, grid, i, cell):
        box = tk.Frame(grid, bg="#f5f5f5")
        # сразу кладём в сетку (одна строка), точную раскладку сделает _reflow_cells
        box.grid(row=0, column=i, padx=4, pady=3, sticky="w")

        num_label = tk.Label(box, text=f"№{i + 1}", font=("Arial", 7), bg="#f5f5f5",
                             fg="#777")
        num_label.pack()

        square = tk.Label(box, text="✔", width=4, height=1, relief="solid", bd=1,
                          font=("Arial", 9))
        if cell.get("done"):
            square.config(bg="#4caf50", fg="white")
        else:
            square.config(bg="white", fg="#ccc", cursor="hand2")
        square.pack()
        square.bind("<Button-1>", lambda e, idx=i: self._toggle_cell(idx))

        weight_row = tk.Frame(box, bg="#f5f5f5")
        weight_row.pack()
        w_btns = []  # ссылки на кнопки веса для точечного обновления
        for w_val in (1, 2, 3):
            w_btn = tk.Label(weight_row, text=str(w_val), font=("Arial", 8),
                             cursor="hand2", padx=3)
            if cell.get("weight", 1) == w_val:
                w_btn.config(fg="#4caf50", font=("Arial", 8, "bold"))
            else:
                w_btn.config(fg="#999")
            w_btn.bind("<Button-1>", lambda e, idx=i, wv=w_val: self._set_weight(idx, wv))
            w_btn.pack(side="left")
            w_btns.append(w_btn)

        del_btn = tk.Label(box, text="✕", fg="#999", cursor="hand2",
                           font=("Arial", 7))
        del_btn.pack()
        del_btn.bind("<Button-1>", lambda e, idx=i: self._delete_cell(idx))

        # запоминаем виджеты, чтобы обновлять их на месте без перерисовки
        while len(self._cell_widgets) <= i:
            self._cell_widgets.append(None)
        self._cell_widgets[i] = {"box": box, "square": square, "weights": w_btns,
                                 "num_label": num_label, "del_btn": del_btn}
        return box

    def _reflow_cells(self, width):
        """Разложить сетку квадратиков по доступной ширине панели."""
        if not hasattr(self, "cells_grid") or not self.cells_grid.winfo_exists():
            return
        boxes = self.cells_grid.winfo_children()
        if not boxes or width <= 1:
            return
        cell_w = max(1, max(b.winfo_reqwidth() for b in boxes)) + 8  # + padx
        per_row = max(1, width // cell_w)
        for i, box in enumerate(boxes):
            box.grid_configure(row=i // per_row, column=i % per_row,
                               padx=4, pady=3, sticky="w")

    def _commit_goal(self):
        """Принудительно зафиксировать цель за сутки из поля ввода.

        Клик по Label (квадратик, кнопка веса) не забирает фокус у Entry,
        поэтому FocusOut может не сработать — вызываем перед любым действием.
        """
        entry = getattr(self, "goal_entry", None)
        if entry is None or not entry.winfo_exists():
            return
        try:
            self.get_condition()["goal"] = max(0, int(entry.get()))
        except ValueError:
            pass  # некорректный ввод — оставляем прежнее значение

    def _save_goal(self, entry):
        try:
            self.get_condition()["goal"] = max(0, int(entry.get()))
        except ValueError:
            entry.delete(0, "end")
            entry.insert(0, str(self.get_condition().get("goal", 0)))
            return
        self.app.save()
        self.draw_month()      # дни могли закраситься/погаснуть
        self.update_stats()

    def _add_cell(self):
        self._commit_goal()    # фиксируем цель до любых изменений
        # новый квадратик создаётся с весом 1; вес меняется после создания
        self.get_condition()["cells"].append({"weight": 1, "done": False,
                                              "date": None})
        self.app.save()
        # добавляем виджет прямо в существующую сетку — без перерисовки панели
        idx = len(self.get_condition()["cells"]) - 1
        if getattr(self, "cells_grid", None) is None or not self.cells_grid.winfo_exists():
            return
        box = self._make_cell_box(self.cells_grid, idx, self.get_condition()["cells"][idx])
        # после отрисовки нового бокса перекладываем всю сетку по ширине
        self.cells_grid.after_idle(
            lambda: self._reflow_cells(self.cells_grid.winfo_width())
        )
        self.update_stats()

    def _toggle_cell(self, idx):
        self._commit_goal()    # фиксируем цель до расчёта автозакраски
        cell = self.get_condition()["cells"][idx]
        if cell.get("locked"):
            # зафиксированный квадратик прошедшего дня не трогаем
            self._refresh_cell_view(idx)
            return
        cell["done"] = not cell.get("done", False)
        # квадратик запоминает, в какой день он был выполнен
        cell["date"] = dt.date.today().isoformat() if cell["done"] else None
        self.app.save()
        self._refresh_cell_view(idx)   # обновляем только этот квадратик
        self.update_stats()
        self.draw_month()      # день мог закраситься зелёным (или погаснуть)

    def _set_weight(self, idx, weight):
        """Смена веса квадратика.

        Выполненный квадратик за прошлый день зафиксирован — его вес
        менять нельзя (иначе задним числом изменится прошлый результат).
        У невыполненного и сегодняшнего квадратика вес свободно меняется.
        """
        self._commit_goal()
        cell = self.get_condition()["cells"][idx]
        if cell.get("done") and cell.get("date") != dt.date.today().isoformat():
            messagebox.showinfo(
                "Вес зафиксирован",
                "Нельзя менять вес выполненного квадратика за прошлый день:\n"
                "результат прошедших суток уже зафиксирован.\n\n"
                "Снимите отметку с квадратика, чтобы изменить вес.",
                parent=self.app,
            )
            self._refresh_cell_view(idx)  # вернуть кнопкам корректный вид
            return
        cell["weight"] = weight
        self.app.save()
        self._refresh_cell_view(idx)   # обновляем только кнопки веса
        self.update_stats()
        self.draw_month()      # смена веса может включить/выключить автодень

    def _refresh_cell_view(self, idx):
        """Обновить вид квадратика на месте, без перерисовки всей панели.

        Перерисовка панели меняет scrollregion канваса, из-за чего список
        карточек прыгает вверх. Здесь мы лишь перекрашиваем существующие
        виджеты, размер панели не меняется — прокрутка остаётся на месте.
        """
        widgets = (getattr(self, "_cell_widgets", None) or [None])[idx]
        if not widgets:
            return
        cell = self.get_condition()["cells"][idx]
        square = widgets["square"]
        if cell.get("done"):
            square.config(bg="#4caf50", fg="white", cursor="arrow")
        else:
            square.config(bg="white", fg="#ccc", cursor="hand2")
        for w_val, w_btn in zip((1, 2, 3), widgets["weights"]):
            if cell.get("weight", 1) == w_val:
                w_btn.config(fg="#4caf50", font=("Arial", 8, "bold"))
            else:
                w_btn.config(fg="#999", font=("Arial", 8))

    def _delete_cell(self, idx):
        self._commit_goal()
        del self.get_condition()["cells"][idx]
        self.app.save()

        # точечное удаление: уничтожаем только виджет этого квадратика,
        # панель и остальные боксы не пересоздаются — прокрутка на месте
        widgets = self._cell_widgets.pop(idx) if idx < len(self._cell_widgets) else None
        if widgets and widgets["box"].winfo_exists():
            widgets["box"].destroy()

        # обновляем номера у последующих квадратиков на месте
        # (замыкания в кнопках уже указывают на новые индексы после pop)
        for i in range(idx, len(self._cell_widgets)):
            box_widgets = self._cell_widgets[i]
            if box_widgets and "num_label" in box_widgets:
                box_widgets["num_label"].config(text=f"№{i + 1}")
        # лямбды кнопок ссылались на старые индексы: пересоздаём их привязки
        self._rebind_cell_callbacks()

        if getattr(self, "cells_grid", None) is not None and self.cells_grid.winfo_exists():
            self.cells_grid.after_idle(
                lambda: self._reflow_cells(self.cells_grid.winfo_width())
            )
        self.update_stats()
        self.draw_month()      # удаление квадратика может погасить автодень

    def _rebind_cell_callbacks(self):
        """Перепривязать события кнопок квадратиков к актуальным индексам.

        Лямбды создавались со старыми индексами; после удаления одного
        квадратика все последующие сдвинулись на -1. Перепривязываем
        заново, не пересоздавая виджеты.
        """
        for i, widgets in enumerate(self._cell_widgets):
            if not widgets:
                continue
            widgets["square"].unbind("<Button-1>")
            widgets["square"].bind("<Button-1>", lambda e, idx=i: self._toggle_cell(idx))
            for w_val, w_btn in zip((1, 2, 3), widgets["weights"]):
                w_btn.unbind("<Button-1>")
                w_btn.bind("<Button-1>", lambda e, idx=i, wv=w_val: self._set_weight(idx, wv))
            if "del_btn" in widgets:
                widgets["del_btn"].unbind("<Button-1>")
                widgets["del_btn"].bind("<Button-1>", lambda e, idx=i: self._delete_cell(idx))

    def toggle_extra(self, event=None):
        self.expanded = not self.expanded
        if self.expanded:
            self.extra_panel.pack(fill="x")           # выпадает снизу карточки
            self.arrow_btn.config(text="▴")
        else:
            self.extra_panel.pack_forget()            # скрывается
            self.arrow_btn.config(text="▾")

    def get_created_date(self):
        """Дата создания карточки; для старых привычек — самая ранняя отметка."""
        created_iso = self.habit.get("created")
        if created_iso:
            return dt.date.fromisoformat(created_iso)
        if self.habit["dates"]:
            return dt.date.fromisoformat(min(self.habit["dates"]))
        return None

    def rename_habit(self, event=None):
        """Редактирование названия привычки через диалог."""
        new_name = simpledialog.askstring(
            "Переименовать",
            "Новое название привычки:",
            initialvalue=self.habit["name"],
            parent=self.app,
        )
        if new_name and new_name.strip() and new_name.strip() != self.habit["name"]:
            self.habit["name"] = new_name.strip()
            self.name_label.config(text=self.habit["name"])
            self.app.save()

    def condition_hint(self):
        """Краткая сводка условия для строки статистики."""
        if not self.habit.get("condition"):
            return ""
        cond = self.get_condition()
        if cond["type"] == "text":
            return f"   •   Условие: {cond['text']}" if cond["text"] else ""
        if cond["type"] == "checklist":
            if not cond["items"]:
                return ""
            done = sum(1 for it in cond["items"] if it.get("done"))
            return f"   •   Список: выполнено {done}/{len(cond['items'])}"
        return ""  # для таблицы подсказка в основной карточке не показывается

    # ---- отрисовка месяца ----
    def draw_month(self):
        for w in self.calendar_widget.winfo_children():
            w.destroy()

        self.title_label = tk.Label(
            self.calendar_widget,
            text=f"{calendar.month_name[self.month]} {self.year}".replace(
                calendar.month_name[self.month],
                ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
                 "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"][self.month - 1]
            ),
            font=("Arial", 10, "bold"),
        )
        self.title_label.grid(row=0, column=0, columnspan=7, sticky="w", pady=(0, 4))

        for col, name in enumerate(WEEKDAYS):
            tk.Label(self.calendar_widget, text=name, font=("Arial", 8), fg="#666").grid(
                row=1, column=col, padx=GAP, sticky="w"
            )

        cal = calendar.Calendar(firstweekday=0)  # неделя с понедельника
        row = 2
        for week in cal.monthdatescalendar(self.year, self.month):
            for col, day in enumerate(week):
                is_current_month = day.month == self.month
                # дни до создания карточки — серые и некликабельные
                created = self.get_created_date()
                is_before_creation = (
                    created is not None and is_current_month and day < created
                )
                square = tk.Label(
                    self.calendar_widget,
                    text=str(day.day),
                    width=3,
                    height=1,
                    relief="solid",
                    font=("Arial", 9),
                    bd=1,
                )
                if day in self.marked_days():
                    square.config(bg="#4caf50", fg="white", bd=1)
                    if day in self.auto_green_days():
                        square.config(bg="#8bc34a")  # светлее: выполнено автоматически
                elif not is_current_month or is_before_creation:
                    square.config(bg="#f0f0f0", fg="#bbb")
                else:
                    square.config(bg="white", fg="#333", cursor="hand2")
                if is_current_month and not is_before_creation:
                    square.bind("<Button-1>", lambda e, d=day: self.toggle_day(d))
                square.grid(row=row, column=col, padx=GAP, pady=GAP, sticky="n")
            row += 1

        self.update_stats()

    def update_stats(self):
        """Перерисовать строку статистики (учитывает заданное условие)."""
        streak = longest_streak(self.habit["dates"])
        marked = len(self.marked_days())
        auto = len(self.auto_green_days())
        auto_txt = f" (из них авто: {auto})" if auto else ""
        self.stats.config(
            text=f"Отмечено дней в месяце: {marked}{auto_txt}   •   Самая длинная серия: {streak} 🔥"
                 + self.condition_hint()
        )

    def marked_days(self):
        marked = {
            dt.date.fromisoformat(d)
            for d in self.habit["dates"]
            if dt.date.fromisoformat(d).month == self.month
            and dt.date.fromisoformat(d).year == self.year
        }
        # дни, автоматически выполненные по таблице квадратиков
        marked |= self.auto_green_days()
        return marked

    def auto_green_days(self):
        """Дни, выполненные по таблице квадратиков.

        Правила:
        - любой день с накопленным весом >= цели закрашивается сам;
        - излишек сверх цели (для любого дня, не только сегодняшнего)
          переносится назад: вес >= цель*2 — закрашивается ещё и ближайший
          незаполненный предыдущий день, >= цель*3 — два предыдущих, и т.д.

        Прошедшие сутки «фиксируются»: при первом же пересчёте после
        завершения дня автозакрытые дни переносятся в dates и дальше
        выглядят как ручная отметка (тёмно-зелёные) и не пересчитываются.
        """
        cond = self.habit.get("condition")
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

        # 2) перенос излишка на предыдущие сутки — для КАЖДОГО дня,
        #    набравшего цель (не только сегодня)
        manual = set(self.habit["dates"])  # вручную заполненные не трогаем
        # граница переноса: дата создания привычки, а если её нет —
        # самая ранняя отметка или 30 дней назад
        floor_iso = self.habit.get("created") or (
            min(self.habit["dates"]) if self.habit["dates"]
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

        # 3) фиксация прошедших суток: автозакрытые дни до вчерашнего
        #    включительно переносятся в dates — они больше не пересчитываются
        #    и закрашиваются как ручная отметка (тёмно-зелёный)
        yesterday_iso = (dt.date.today() - dt.timedelta(days=1)).isoformat()
        to_fix = [d for d in green if d <= yesterday_iso and d not in manual]
        if to_fix:
            self.habit["dates"].extend(to_fix)
            # выполненные квадратики прошедших дней тоже фиксируем:
            # их вес больше не влияет на расчёт (защита от переделки)
            for cell in cond["cells"]:
                if cell.get("done") and cell.get("date") in to_fix:
                    cell["locked"] = True
            self.app.save()

        # фильтруем по отображаемому месяцу
        return {
            dt.date.fromisoformat(d)
            for d in green
            if dt.date.fromisoformat(d).month == self.month
            and dt.date.fromisoformat(d).year == self.year
        }

    # ---- клик по дню ----
    def toggle_day(self, day):
        iso = day.isoformat()
        if iso in self.habit["dates"]:
            self.habit["dates"].remove(iso)
        else:
            self.habit["dates"].append(iso)
        self.app.save()
        self.draw_month()


class HabitTrackerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Трекер привычек")
        self.configure(bg="#fafafa")
        self.dh = DH.DataHandler()
        self.data = self.dh.load_data()

        today = dt.date.today()
        self.year, self.month = today.year, today.month

        # ---- верхняя панель ----
        top = tk.Frame(self, bg="#fafafa")
        top.pack(fill="x", padx=10, pady=(10, 0))
        tk.Label(top, text="Трекер привычек", font=("Arial", 16, "bold"), bg="#fafafa").pack(side="left")
        self.nav = tk.Frame(top, bg="#fafafa")
        self.nav.pack(side="right")

        # ---- прокручиваемая область с карточками ----
        container = tk.Frame(self, bg="#fafafa")
        container.pack(fill="both", expand=True, padx=10, pady=10)
        self.canvas = tk.Canvas(container, bg="#fafafa", highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=self.canvas.yview)
        self.scroll_frame = tk.Frame(self.canvas, bg="#fafafa")
        self.scroll_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self.canvas_window = self.canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfig(self.canvas_window, width=self.canvas.winfo_width()),
        )
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # ---- кнопка добавления внизу ----
        bottom = tk.Frame(self, bg="#fafafa")
        bottom.pack(fill="x", padx=10, pady=(0, 10))
        tk.Button(
            bottom, text="+ Добавить привычку", font=("Arial", 11, "bold"),
            bg="#4caf50", fg="white", relief="flat", padx=14, pady=6,
            cursor="hand2", command=self.add_habit,
        ).pack(fill="x")

        self.render_cards()
        # прокрутка колесом мыши
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    # ---- карточки ----
    def render_cards(self):
        for w in self.scroll_frame.winfo_children():
            w.destroy()
        if not self.data["habits"]:
            tk.Label(
                self.scroll_frame,
                text="Пока нет привычек.\nНажмите «+ Добавить привычку» внизу.",
                font=("Arial", 11), fg="#888", bg="#fafafa", pady=40,
            ).pack()
            return
        for habit in self.data["habits"]:
            HabitCard(self.scroll_frame, self, habit).pack(fill="x", pady=6, padx=4)

    # ---- действия ----
    def add_habit(self):
        name = simpledialog.askstring("Новая привычка", "Название привычки:", parent=self)
        if name and name.strip():
            self.data["habits"].append({"name": name.strip(), "dates": [], "condition": "",
                                        "created": dt.date.today().isoformat()})
            self.save()
            self.render_cards()

    def delete_habit(self, event=None):
        pass  # переопределяется в карточке

    def save(self):
        self.dh.save_data(self.data)

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")


# патчим удаление (метод у карточки имеет доступ к своей привычке)
def _delete_habit(self, event=None):
    if messagebox.askyesno("Удалить", f"Удалить привычку «{self.habit['name']}»?"):
        self.app.data["habits"].remove(self.habit)
        self.app.save()
        self.app.render_cards()

HabitCard.delete_habit = _delete_habit


if __name__ == "__main__":
    app = HabitTrackerApp()
    app.geometry("640x720")
    app.mainloop()