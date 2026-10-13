# habit_card.py — карточка привычки: шапка, календарь, статистика, панель условия

import datetime as dt
import tkinter as tk
from tkinter import messagebox, simpledialog

from config import PAD
from models import (longest_streak, get_condition, get_created_date,
                    compute_auto_green_days)
from month_calendar import MonthCalendar
from condition_panel import ConditionPanel


class HabitCard(tk.Frame):
    """Карточка одной привычки.

    Компонует MonthCalendar и ConditionPanel. Панели и календарю данные
    не передаются «сверху вниз» насильно: панель сообщает об изменениях
    через колбэк on_condition_change, календарь — через on_day_click.
    """

    def __init__(self, master, app, habit):
        super().__init__(master, bd=1, relief="solid", padx=PAD, pady=PAD)
        self.app = app
        self.habit = habit

        # ---- шапка ----
        header = tk.Frame(self)
        header.pack(fill="x")
        # имя привычки: двойной клик по нему открывает редактирование
        self.name_label = tk.Label(header, text=habit["name"],
                                   font=("Arial", 12, "bold"), cursor="xterm")
        self.name_label.pack(side="left")
        self.name_label.bind("<Double-Button-1>", self.rename_habit)
        # дата создания карточки (или первая известная отметка для старых)
        created = get_created_date(habit)
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

        # ---- календарь месяца ----
        self.year = self.app.year
        self.month = self.app.month
        self.calendar = MonthCalendar(self)
        self.calendar.pack(fill="x", pady=(6, 2))

        # ---- строка статистики ----
        self.stats = tk.Label(self, font=("Arial", 10), fg="#444")
        self.stats.pack(anchor="w")

        # ---- выпадающая снизу панель условия (скрыта по умолчанию) ----
        self.condition_panel = ConditionPanel(
            self, habit,
            on_change=self.on_condition_change,
            preserve_scroll=self._run_preserving_scroll,
        )

        self.draw_month()

    # ---- связь с панелью условия ----
    def on_condition_change(self):
        """Данные условия изменились: сохранить и перерисовать календарь."""
        self.app.save()
        self.draw_month()

    def _run_preserving_scroll(self, fn):
        """Выполнить fn, не сбрасывая прокрутку списка карточек."""
        canvas = self.app.canvas
        top_frac = canvas.yview()[0]
        fn()
        canvas.after_idle(lambda: canvas.yview_moveto(top_frac))

    def toggle_extra(self, event=None):
        self.expanded = not self.expanded
        if self.expanded:
            self.condition_panel.pack(fill="x")   # выпадает снизу карточки
            self.arrow_btn.config(text="▴")
        else:
            self.condition_panel.pack_forget()    # скрывается
            self.arrow_btn.config(text="▾")

    # ---- действия с карточкой ----
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

    def delete_habit(self, event=None):
        if messagebox.askyesno("Удалить", f"Удалить привычку «{self.habit['name']}»?"):
            self.app.data["habits"].remove(self.habit)
            self.app.save()
            self.app.render_cards()

    def condition_hint(self):
        """Краткая сводка условия для строки статистики."""
        if not self.habit.get("condition"):
            return ""
        cond = get_condition(self.habit)
        if cond["type"] == "text":
            return f"   •   Условие: {cond['text']}" if cond["text"] else ""
        if cond["type"] == "checklist":
            if not cond["items"]:
                return ""
            done = sum(1 for it in cond["items"] if it.get("done"))
            return f"   •   Список: выполнено {done}/{len(cond['items'])}"
        return ""  # для таблицы подсказка в основной карточке не показывается

    # ---- отрисовка ----
    def draw_month(self):
        auto = compute_auto_green_days(self.habit, self.year, self.month,
                                       self.app.save)
        marked = self.manual_days() | auto
        self.calendar.draw(
            self.year, self.month, marked, auto,
            created=get_created_date(self.habit),
            on_day_click=self.toggle_day,
        )
        self.update_stats(marked, auto)

    def update_stats(self, marked, auto):
        """Перерисовать строку статистики (учитывает заданное условие).

        Серия считается по всем зелёным дням (ручные + автозакрытые),
        а не только по ручным отметкам.
        """
        streak = longest_streak(marked)
        auto_txt = f" (из них авто: {len(auto)})" if auto else ""
        self.stats.config(
            text=f"Отмечено дней в месяце: {len(marked)}{auto_txt}"
                 f"   •   Самая длинная серия: {streak} 🔥"
                 + self.condition_hint()
        )

    def manual_days(self):
        """Вручную отмеченные дни отображаемого месяца."""
        return {
            dt.date.fromisoformat(d)
            for d in self.habit["dates"]
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