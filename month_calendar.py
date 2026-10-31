# month_calendar.py — виджет календаря месяца (недели — строки, дни — квадраты)

import calendar
import tkinter as tk

from config import GAP, WEEKDAYS, MONTHS_RU


class MonthCalendar(tk.Frame):
    """Календарь одного месяца. Ничего не знает о привычках:

    отрисовку запускает draw(), данные (отмеченные/авто дни, дата
    создания) передаются параметрами, клики уходят в on_day_click.
    """

    def draw(self, year, month, marked, auto_days, created, on_day_click):
        """Перерисовать месяц.

        marked          — множество отмеченных дней (dt.date);
        auto_days       — подмножество marked, закрытое автоматически
                          (закрашивается светлее);
        created         — дата создания карточки или None: дни до неё
                          серые и некликабельные;
        on_day_click    — обработчик клика по дню месяца.
        """
        for w in self.winfo_children():
            w.destroy()

        tk.Label(self, text=f"{MONTHS_RU[month - 1]} {year}",
                 font=("Arial", 10, "bold")).grid(
            row=0, column=0, columnspan=7, sticky="w", pady=(0, 4))

        for col, name in enumerate(WEEKDAYS):
            tk.Label(self, text=name, font=("Arial", 8), fg="#666").grid(
                row=1, column=col, padx=GAP, sticky="w")

        cal = calendar.Calendar(firstweekday=0)  # неделя с понедельника
        row = 2
        for week in cal.monthdatescalendar(year, month):
            for col, day in enumerate(week):
                is_current_month = day.month == month
                # дни до создания карточки — серые и некликабельные
                is_before_creation = (
                    created is not None and is_current_month and day < created
                )
                square = tk.Label(
                    self,
                    text=str(day.day),
                    width=3,
                    height=1,
                    relief="solid",
                    font=("Arial", 9),
                    bd=1,
                )
                if day in marked:
                    square.config(bg="#4caf50", fg="white", bd=1)
                    if day in auto_days:
                        square.config(bg="#8bc34a")  # светлее: выполнено автоматически
                elif not is_current_month or is_before_creation:
                    square.config(bg="#f0f0f0", fg="#bbb")
                else:
                    square.config(bg="white", fg="#333", cursor="hand2")
                if is_current_month and not is_before_creation:
                    square.bind("<Button-1>", lambda e, d=day: on_day_click(d))
                square.grid(row=row, column=col, padx=GAP, pady=GAP, sticky="n")
            row += 1