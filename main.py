import customtkinter as ctk
import random
import time
import threading
import pygame
import json
import os
from plyer import notification
import pystray
from PIL import Image, ImageDraw
from datetime import datetime

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

HISTORY_FILE = "history.json"
EXERCISES_FILE = "exercises.json"

DEFAULT_EXERCISES = {
    "Растяжка": [
        {"name": "Наклоны", "reps": "15 раз"}, {"name": "Кобра", "reps": "30 сек"},
        {"name": "Замок", "reps": "20 сек"}, {"name": "Шпагат", "reps": "1 мин"}
    ],
    "Выносливость": [
        {"name": "Берпи", "reps": "10 раз"}, {"name": "Планка", "reps": "45 сек"},
        {"name": "Скакалка", "reps": "100 прыжков"}, {"name": "Джампинг Джек", "reps": "30 раз"}
    ],
    "Сила": [
        {"name": "Приседания", "reps": "20 раз"}, {"name": "Отжимания", "reps": "15 раз"},
        {"name": "Выпады", "reps": "10 на ногу"}, {"name": "Пресс", "reps": "25 раз"}
    ]
}


class SlotDrum(ctk.CTkCanvas):
    def __init__(self, master, items, on_stop=None, **kwargs):
        super().__init__(master, width=180, height=150, bg="#2b2b2b",
                         highlightthickness=2, highlightbackground="#3b8ed0", **kwargs)
        self.items = items
        self.on_stop = on_stop
        self.item_height = 50
        self.visible_height = 150
        self.speed = 0
        self.running = False
        self.offset = 0
        self.selected_index = None

        self.inner = ctk.CTkFrame(self, fg_color="transparent")
        self.create_window(0, 0, anchor="nw", window=self.inner)
        self.setup_labels()

        center_y = self.visible_height / 2
        self.create_rectangle(5, center_y - 25, 175, center_y + 25, outline="#00ff99", width=3)

    def setup_labels(self):
        for widget in self.inner.winfo_children(): widget.destroy()
        self.display_items = self.items * 3
        self.labels = []
        for item in self.display_items:
            text = f"{item['name']}\n({item['reps']})"
            lbl = ctk.CTkLabel(self.inner, text=text, height=self.item_height, width=180,
                               font=("Arial", 11, "bold"), fg_color="transparent")
            lbl.pack()
            self.labels.append(lbl)
        self.total_height = len(self.display_items) * self.item_height
        self.configure(scrollregion=(0, 0, 180, self.total_height))

    def animate(self):
        if not self.running: return
        if self.speed <= 0.5:
            self.speed = 0;
            self.running = False;
            self.snap_to_item()
            if self.on_stop: self.on_stop(self)
            return
        self.offset += self.speed
        loop_height = self.total_height / 3
        if self.offset >= loop_height: self.offset -= loop_height
        self.yview_moveto(self.offset / self.total_height)
        self.speed *= 0.95
        self.after(20, self.animate)

    def snap_to_item(self):
        center = self.offset + self.visible_height / 2
        index = round(center / self.item_height)
        self.offset = (index * self.item_height) - self.visible_height / 2
        self.yview_moveto(max(0, self.offset) / self.total_height)
        self.selected_index = index % len(self.items)

    def highlight(self):
        for lbl in self.labels: lbl.configure(fg_color="transparent", text_color="white")
        if self.selected_index is not None:
            for i, lbl in enumerate(self.labels):
                if i % len(self.items) == self.selected_index:
                    lbl.configure(fg_color="#00ff99", text_color="black")

    def spin(self, force):
        if self.running: return
        for lbl in self.labels: lbl.configure(fg_color="transparent", text_color="white")
        self.speed = force;
        self.running = True;
        self.animate()


class FitnessApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Fitness Slots Ultra PRO")
        self.geometry("650x600")

        self.load_data()
        self.init_sounds()

        self.tray_icon = None
        self.sidebar_open = False
        self.stop_check = 0

        self.main_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_frame.pack(fill="both", expand=True)

        ctk.CTkLabel(self.main_frame, text="🎰 ФИТНЕС-РУЛЕТКА", font=("Arial", 28, "bold"), text_color="#3b8ed0").pack(
            pady=20)

        self.drums_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.drums_frame.pack(pady=10)
        self.create_drums()

        self.spin_btn = ctk.CTkButton(self.main_frame, text="КРУТИТЬ БАРАБАН", command=self.start_spin,
                                      height=50, font=("Arial", 18, "bold"), corner_radius=25)
        self.spin_btn.pack(pady=20)

        self.result_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        ctk.CTkButton(self.result_frame, text="ВЫПОЛНИЛ ✅", fg_color="#28a745",
                      command=lambda: self.add_to_history("Выполнено")).pack(side="left", padx=10)
        ctk.CTkButton(self.result_frame, text="ПРОПУСТИТЬ ❌", fg_color="#dc3545",
                      command=lambda: self.add_to_history("Пропущено")).pack(side="left", padx=10)

        self.setup_timer_ui()
        self.setup_sidebar()

        self.menu_btn = ctk.CTkButton(self, text="☰", width=40, height=40, corner_radius=8, command=self.toggle_sidebar)
        self.menu_btn.place(x=10, y=10)

        self.refresh_history_ui()
        self.protocol("WM_DELETE_WINDOW", self.hide_to_tray)

    def init_sounds(self):
        pygame.mixer.init()
        try:
            self.sound_spin = pygame.mixer.Sound("sounds/spin.mp3")
            self.sound_success = pygame.mixer.Sound("sounds/success.mp3")
            self.sound_fail = pygame.mixer.Sound("sounds/fail.mp3")
            self.sound_click = pygame.mixer.Sound("sounds/click.mp3")

            self.sound_spin.set_volume(0.5)
            self.sound_success.set_volume(0.7)
            self.sound_fail.set_volume(0.7)
            self.sound_click.set_volume(0.4)
        except:
            print("Звуки не найдены")

            class Dummy:
                def play(self): pass

                def set_volume(self, v): pass

            self.sound_spin = self.sound_success = self.sound_fail = self.sound_click = Dummy()

    def load_data(self):
        if os.path.exists(EXERCISES_FILE):
            with open(EXERCISES_FILE, "r", encoding="utf-8") as f:
                self.exercises_data = json.load(f)
        else:
            self.exercises_data = DEFAULT_EXERCISES
            self.save_exercises()

        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                self.history_data = json.load(f)
        else:
            self.history_data = []

    def save_exercises(self):
        with open(EXERCISES_FILE, "w", encoding="utf-8") as f:
            json.dump(self.exercises_data, f, ensure_ascii=False, indent=4)

    def save_history(self):
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(self.history_data, f, ensure_ascii=False, indent=4)

    def create_drums(self):
        if hasattr(self, 'drum1'):
            self.drum1.destroy();
            self.drum2.destroy();
            self.drum3.destroy()
        self.drum1 = SlotDrum(self.drums_frame, self.exercises_data["Растяжка"], on_stop=self.drum_stopped)
        self.drum1.grid(row=0, column=0, padx=5)
        self.drum2 = SlotDrum(self.drums_frame, self.exercises_data["Выносливость"], on_stop=self.drum_stopped)
        self.drum2.grid(row=0, column=1, padx=5)
        self.drum3 = SlotDrum(self.drums_frame, self.exercises_data["Сила"], on_stop=self.drum_stopped)
        self.drum3.grid(row=0, column=2, padx=5)

    def setup_timer_ui(self):
        container = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        container.pack(pady=20)
        self.entries = {}
        for i, unit in enumerate(["HH", "MM", "SS"]):
            f = ctk.CTkFrame(container, fg_color="#2b2b2b", corner_radius=10)
            f.grid(row=0, column=i, padx=8)
            ctk.CTkButton(f, text="▲", width=30, height=20, fg_color="transparent",
                          command=lambda u=unit: self.change_time(u, 1)).pack()
            e = ctk.CTkEntry(f, width=55, height=35, border_width=0, fg_color="transparent", font=("Arial", 18, "bold"),
                             justify="center")
            e.insert(0, "00");
            e.pack();
            self.entries[unit] = e
            ctk.CTkButton(f, text="▼", width=30, height=20, fg_color="transparent",
                          command=lambda u=unit: self.change_time(u, -1)).pack()
        ctk.CTkButton(self.main_frame, text="СТАРТ ТАЙМЕРА", fg_color="#00ff99", text_color="black",
                      font=("Arial", 14, "bold"), command=self.start_timer_thread).pack()

    def setup_sidebar(self):
        self.sidebar = ctk.CTkFrame(self, width=280, corner_radius=0, fg_color="#1e1e1e", border_width=1,
                                    border_color="#3b8ed0")
        self.sidebar.place(x=-300, y=0, relheight=1)
        ctk.CTkLabel(self.sidebar, text="ИСТОРИЯ", font=("Arial", 20, "bold"), text_color="#3b8ed0").pack(pady=20)
        self.history_box = ctk.CTkScrollableFrame(self.sidebar, width=240, fg_color="transparent")
        self.history_box.pack(expand=True, fill="both", padx=10, pady=10)
        ctk.CTkButton(self.sidebar, text="⚙️ УПРАЖНЕНИЯ", command=self.open_exercise_editor).pack(pady=10)

    def open_exercise_editor(self):
        self.sound_click.play()
        ed = ctk.CTkToplevel(self)
        ed.title("Редактор")
        ed.geometry("450x550")
        ed.attributes("-topmost", True)

        tabs = ctk.CTkTabview(ed)
        tabs.pack(fill="both", expand=True, padx=5, pady=5)

        for cat in self.exercises_data.keys():
            tabs.add(cat)
            f_main = tabs.tab(cat)
            scroll = ctk.CTkScrollableFrame(f_main, height=300)
            scroll.pack(fill="x", pady=5)
            self.update_ed_list(scroll, cat)

            ctk.CTkLabel(f_main, text="Новое упражнение:", font=("Arial", 10)).pack()
            name_e = ctk.CTkEntry(f_main, placeholder_text="Название...")
            name_e.pack(fill="x", padx=20, pady=2)
            reps_e = ctk.CTkEntry(f_main, placeholder_text="Кол-во (н-р: 15 раз)")
            reps_e.pack(fill="x", padx=20, pady=2)
            ctk.CTkButton(f_main, text="Добавить",
                          command=lambda c=cat, n=name_e, r=reps_e, s=scroll: self.add_ex(c, n, r, s)).pack(pady=10)

    def update_ed_list(self, scroll, cat):
        for w in scroll.winfo_children(): w.destroy()
        for item in self.exercises_data[cat]:
            f = ctk.CTkFrame(scroll, fg_color="#333333")
            f.pack(fill="x", pady=2)
            ctk.CTkLabel(f, text=f"{item['name']} - {item['reps']}", font=("Arial", 11)).pack(side="left", padx=5)
            ctk.CTkButton(f, text="×", width=25, fg_color="#aa3333",
                          command=lambda c=cat, i=item, s=scroll: self.rem_ex(c, i, s)).pack(side="right")

    def add_ex(self, cat, n_entry, r_entry, scroll):
        n, r = n_entry.get().strip(), r_entry.get().strip()
        if n and r:
            self.exercises_data[cat].append({"name": n, "reps": r})
            self.save_exercises();
            self.update_ed_list(scroll, cat);
            self.create_drums()
            n_entry.delete(0, 'end');
            r_entry.delete(0, 'end')

    def rem_ex(self, cat, item, scroll):
        if len(self.exercises_data[cat]) > 1:
            self.exercises_data[cat].remove(item)
            self.save_exercises();
            self.update_ed_list(scroll, cat);
            self.create_drums()

    def add_to_history(self, status):
        if status == "Выполнено":
            self.sound_success.play()
        else:
            self.sound_fail.play()

        res = [
            f"{self.drum1.items[self.drum1.selected_index]['name']} ({self.drum1.items[self.drum1.selected_index]['reps']})",
            f"{self.drum2.items[self.drum2.selected_index]['name']} ({self.drum2.items[self.drum2.selected_index]['reps']})",
            f"{self.drum3.items[self.drum3.selected_index]['name']} ({self.drum3.items[self.drum3.selected_index]['reps']})"
        ]

        entry = {"time": datetime.now().strftime("%d.%m %H:%M"), "status": status, "ex": res}
        self.history_data.insert(0, entry)
        self.save_history();
        self.refresh_history_ui()
        self.result_frame.pack_forget()

    def refresh_history_ui(self):
        for w in self.history_box.winfo_children(): w.destroy()
        for item in self.history_data[:30]:
            color = "#28a745" if item["status"] == "Выполнено" else "#dc3545"
            card = ctk.CTkFrame(self.history_box, fg_color="#2b2b2b")
            card.pack(fill="x", pady=3)

            ctk.CTkLabel(card,
                         text=f"{item['time']} - {item['status']}",
                         text_color=color,
                         font=("Arial", 14, "bold")
                         ).pack(pady=(1,0))

            ex_list = item.get("ex", [])
            if isinstance(ex_list, list):
                ctk.CTkLabel(card,
                             text="• " + "\n• ".join(ex_list),
                             font=("Arial", 12),
                             justify="left"
                             ).pack(pady=(0, 10))

    def change_time(self, unit, delta):
        val = (int(self.entries[unit].get()) + delta) % (24 if unit == "HH" else 60)
        self.entries[unit].delete(0, 'end');
        self.entries[unit].insert(0, f"{val:02d}")

    def start_spin(self):
        self.sound_spin.play();
        self.result_frame.pack_forget()
        self.stop_check = 0
        self.drum1.spin(random.randint(20, 35))
        self.drum2.spin(random.randint(25, 40))
        self.drum3.spin(random.randint(30, 45))

    def drum_stopped(self, d):
        self.stop_check += 1
        if self.stop_check == 3:
            self.drum1.highlight();
            self.drum2.highlight();
            self.drum3.highlight()
            self.result_frame.pack(pady=10)

    def toggle_sidebar(self):
        self.sound_click.play()
        if not self.sidebar_open:
            self.sidebar.place(x=0);
            self.sidebar.lift();
            self.menu_btn.lift()
            self.sidebar_open = True;
            self.menu_btn.configure(text="✕")
        else:
            self.sidebar.place(x=-300);
            self.sidebar_open = False;
            self.menu_btn.configure(text="☰")

    def start_timer_thread(self):
        try:
            ts = int(self.entries["HH"].get()) * 3600 + int(self.entries["MM"].get()) * 60 + int(
                self.entries["SS"].get())
            if ts > 0: threading.Thread(target=self.timer_worker, args=(ts,), daemon=True).start(); self.hide_to_tray()
        except:
            pass

    def timer_worker(self, s):
        time.sleep(s)
        notification.notify(title="Пора!", message="Время тренировки!", app_name="FitnessSlots")
        self.after(0, self.show_from_tray)
        self.after(1000, self.start_spin)

    def hide_to_tray(self):
        self.withdraw()
        if self.tray_icon is None:
            img = Image.new('RGB', (64, 64), color=(31, 106, 165))
            d = ImageDraw.Draw(img);
            d.ellipse([10, 10, 54, 54], fill="#00ff99")
            m = pystray.Menu(pystray.MenuItem('Открыть', self.show_from_tray), pystray.MenuItem('Выход', self.exit_app))
            self.tray_icon = pystray.Icon("fit_app", img, "Fitness Slots", m)
            threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def show_from_tray(self, icon=None):
        if self.tray_icon: self.tray_icon.stop(); self.tray_icon = None
        self.deiconify();
        self.lift();
        self.focus_force()

    def exit_app(self, icon=None):
        if self.tray_icon: self.tray_icon.visible = False; self.tray_icon.stop()
        self.destroy();
        os._exit(0)


if __name__ == "__main__":
    FitnessApp().mainloop()