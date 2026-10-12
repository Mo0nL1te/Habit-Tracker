# main.py — точка входа: python main.py

from app import HabitTrackerApp

if __name__ == "__main__":
    app = HabitTrackerApp()
    app.geometry("640x720")
    app.mainloop()