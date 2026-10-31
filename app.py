# app.py — главное окно приложения

import datetime as dt
import tkinter as tk
from tkinter import ttk, simpledialog

import DataHandler as DH
from habit_card import HabitCard


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
        tk.Label(top, text="Трекер привычек", font=("Arial", 16, "bold"),
                 bg="#fafafa").pack(side="left")
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

    def save(self):
        self.dh.save_data(self.data)

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")