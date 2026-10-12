# condition_panel.py — выпадающая панель условия (текст / список дел / таблица)

import datetime as dt
import tkinter as tk
from tkinter import ttk, messagebox

from config import TYPE_NAMES, TYPE_KEYS
from models import get_condition


class ConditionPanel(tk.Frame):
    """Панель дополнительного условия выполнения.

    Панель ничего не знает о приложении и карточке: изменения данных
    публикуются через on_change (карточка сохраняет и обновляет
    статистику/календарь), а перерисовка без сброса прокрутки —
    через preserve_scroll. Обе функции передаёт HabitCard.
    """

    def __init__(self, master, habit, on_change, preserve_scroll=None):
        super().__init__(master, bd=0)
        self.habit = habit
        self.on_change = on_change
        self._preserve_scroll = preserve_scroll or (lambda fn: fn())

        inner = tk.Frame(self, bg="#f5f5f5", padx=8, pady=8)
        inner.pack(fill="x", pady=(4, 0))

        # выбор типа условия
        type_row = tk.Frame(inner, bg="#f5f5f5")
        type_row.pack(fill="x")
        tk.Label(type_row, text="Тип условия:", font=("Arial", 9),
                 bg="#f5f5f5", fg="#555").pack(side="left")
        self.type_var = tk.StringVar(value=get_condition(habit)["type"])
        type_box = ttk.Combobox(
            type_row, textvariable=self.type_var, state="readonly", width=22,
            values=list(TYPE_NAMES.values()),
        )
        type_box.pack(side="left", padx=6)
        type_box.bind("<<ComboboxSelected>>", self.on_type_changed)

        # контент условия, перерисовывается при смене типа
        self.content_frame = tk.Frame(inner, bg="#f5f5f5")
        self.content_frame.pack(fill="x", pady=(4, 0))
        self.rerender()

    # ---- общие ----
    def on_type_changed(self, event=None):
        cond = get_condition(self.habit)
        cond["type"] = TYPE_KEYS[self.type_var.get()]
        self.habit["condition"] = cond
        self.on_change()
        self._preserve_scroll(self.rerender)

    def rerender(self):
        """Перерисовать содержимое панели под выбранный тип условия."""
        for w in self.content_frame.winfo_children():
            w.destroy()
        cond = get_condition(self.habit)
        getattr(self, "_render_cond_" + cond["type"])(cond)

    # ---- тип: текст ----
    def _render_cond_text(self, cond):
        entry = tk.Entry(self.content_frame, font=("Arial", 10), relief="solid", bd=1)
        entry.pack(fill="x")
        entry.insert(0, cond.get("text", ""))
        entry.bind("<FocusOut>", lambda e: self._save_text(entry))
        entry.bind("<Return>", lambda e: self._save_text(entry))

    def _save_text(self, entry):
        get_condition(self.habit)["text"] = entry.get().strip()
        self.on_change()

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
        get_condition(self.habit)["items"].append({"text": "", "done": False})
        self.on_change()
        self._preserve_scroll(self.rerender)

    def _toggle_item(self, idx, var):
        # состояние чекбокса меняется после обработчика — планируем отложенно
        self.after(50, lambda: self._apply_item_state(idx, var))

    def _apply_item_state(self, idx, var):
        get_condition(self.habit)["items"][idx]["done"] = var.get()
        self.on_change()

    def _save_item(self, idx, entry):
        get_condition(self.habit)["items"][idx]["text"] = entry.get()
        self.on_change()

    def _delete_item(self, idx):
        del get_condition(self.habit)["items"][idx]
        self.on_change()
        self._preserve_scroll(self.rerender)

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
            get_condition(self.habit)["goal"] = max(0, int(entry.get()))
        except ValueError:
            pass  # некорректный ввод — оставляем прежнее значение

    def _save_goal(self, entry):
        try:
            get_condition(self.habit)["goal"] = max(0, int(entry.get()))
        except ValueError:
            entry.delete(0, "end")
            entry.insert(0, str(get_condition(self.habit).get("goal", 0)))
            return
        self.on_change()

    def _add_cell(self):
        self._commit_goal()    # фиксируем цель до любых изменений
        # новый квадратик создаётся с весом 1; вес меняется после создания
        get_condition(self.habit)["cells"].append({"weight": 1, "done": False,
                                                   "date": None})
        self.on_change()
        # добавляем виджет прямо в существующую сетку — без перерисовки панели
        idx = len(get_condition(self.habit)["cells"]) - 1
        if getattr(self, "cells_grid", None) is None or not self.cells_grid.winfo_exists():
            return
        self._make_cell_box(self.cells_grid, idx, get_condition(self.habit)["cells"][idx])
        # после отрисовки нового бокса перекладываем всю сетку по ширине
        self.cells_grid.after_idle(
            lambda: self._reflow_cells(self.cells_grid.winfo_width())
        )

    def _toggle_cell(self, idx):
        self._commit_goal()    # фиксируем цель до расчёта автозакраски
        cell = get_condition(self.habit)["cells"][idx]
        if cell.get("locked"):
            # зафиксированный квадратик прошедшего дня не трогаем
            self._refresh_cell_view(idx)
            return
        cell["done"] = not cell.get("done", False)
        # квадратик запоминает, в какой день он был выполнен
        cell["date"] = dt.date.today().isoformat() if cell["done"] else None
        self.on_change()
        self._refresh_cell_view(idx)   # обновляем только этот квадратик

    def _set_weight(self, idx, weight):
        """Смена веса квадратика.

        Выполненный квадратик за прошлый день зафиксирован — его вес
        менять нельзя (иначе задним числом изменится прошлый результат).
        """
        self._commit_goal()
        cell = get_condition(self.habit)["cells"][idx]
        if cell.get("done") and cell.get("date") != dt.date.today().isoformat():
            messagebox.showinfo(
                "Вес зафиксирован",
                "Нельзя менять вес выполненного квадратика за прошлый день:\n"
                "результат прошедших суток уже зафиксирован.\n\n"
                "Снимите отметку с квадратика, чтобы изменить вес.",
            )
            self._refresh_cell_view(idx)  # вернуть кнопкам корректный вид
            return
        cell["weight"] = weight
        self.on_change()
        self._refresh_cell_view(idx)   # обновляем только кнопки веса

    def _refresh_cell_view(self, idx):
        """Обновить вид квадратика на месте, без перерисовки всей панели."""
        widgets = (getattr(self, "_cell_widgets", None) or [None])[idx]
        if not widgets:
            return
        cell = get_condition(self.habit)["cells"][idx]
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
        del get_condition(self.habit)["cells"][idx]
        self.on_change()

        # точечное удаление: уничтожаем только виджет этого квадратика,
        # панель и остальные боксы не пересоздаются — прокрутка на месте
        widgets = self._cell_widgets.pop(idx) if idx < len(self._cell_widgets) else None
        if widgets and widgets["box"].winfo_exists():
            widgets["box"].destroy()

        # обновляем номера у последующих квадратиков на месте
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