import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import json
import time
from models import Building, Person
from controller import Controller
from simulation import Simulation


class MainApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Elevator System Simulation")
        self.root.geometry("1000x700")

        # Defaults
        self.num_floors = 10
        self.num_elevators = 3

        self.building = Building(self.num_floors, self.num_elevators)
        self.controller = Controller()
        self.sim = Simulation(self.building, self.controller, self.on_sim_update)

        self.setup_ui()
        self.root.after(100, self.periodic_ui_refresh)  # Fallback timer

    def setup_ui(self):
        # 1. Top Panel (Config & Controls)
        top_frame = ttk.Frame(self.root, padding=10)
        top_frame.pack(fill=tk.X)

        # Config
        conf_grp = ttk.LabelFrame(top_frame, text="Configuration", padding=5)
        conf_grp.pack(side=tk.LEFT, padx=5)

        ttk.Label(conf_grp, text="Floors (1-20):").grid(row=0, column=0)
        self.ent_floors = ttk.Entry(conf_grp, width=5)
        self.ent_floors.insert(0, str(self.num_floors))
        self.ent_floors.grid(row=0, column=1)

        ttk.Label(conf_grp, text="Elevators (1-5):").grid(row=1, column=0)
        self.ent_elevs = ttk.Entry(conf_grp, width=5)
        self.ent_elevs.insert(0, str(self.num_elevators))
        self.ent_elevs.grid(row=1, column=1)

        ttk.Button(conf_grp, text="Apply", command=self.apply_config).grid(row=2, column=0, columnspan=2, pady=5)

        # Strategy
        strat_grp = ttk.LabelFrame(top_frame, text="Strategy", padding=5)
        strat_grp.pack(side=tk.LEFT, padx=5)
        self.strat_var = tk.StringVar(value="min_wait")
        ttk.Radiobutton(strat_grp, text="Min Wait Time", variable=self.strat_var, value="min_wait",
                        command=self.change_strategy).pack(anchor=tk.W)
        ttk.Radiobutton(strat_grp, text="Min Idle Moves", variable=self.strat_var, value="min_idle",
                        command=self.change_strategy).pack(anchor=tk.W)

        # Controls
        ctrl_grp = ttk.LabelFrame(top_frame, text="Simulation Control", padding=5)
        ctrl_grp.pack(side=tk.LEFT, padx=5)

        btn_frame = ttk.Frame(ctrl_grp)
        btn_frame.pack()
        ttk.Button(btn_frame, text="Start", command=self.start_sim).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="Pause", command=self.pause_sim).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="Stop", command=self.stop_sim).pack(side=tk.LEFT)

        spd_frame = ttk.Frame(ctrl_grp)
        spd_frame.pack(pady=5)
        ttk.Button(spd_frame, text="Speed -", command=self.slow_down).pack(side=tk.LEFT)
        ttk.Button(spd_frame, text="Speed +", command=self.speed_up).pack(side=tk.LEFT)

        self.lbl_speed = ttk.Label(ctrl_grp, text="x1.0")
        self.lbl_speed.pack()

        fire_btn = ttk.Button(ctrl_grp, text="FIRE ALARM", command=self.toggle_fire)
        fire_btn.pack(fill=tk.X, pady=2)
        self.fire_btn = fire_btn

        # Scenario / Manual Spawn
        scen_grp = ttk.LabelFrame(top_frame, text="Scenario & Spawn", padding=5)
        scen_grp.pack(side=tk.LEFT, padx=5)

        ttk.Button(scen_grp, text="Import Scenario", command=self.import_scenario).pack(fill=tk.X)
        ttk.Button(scen_grp, text="Export Config", command=self.export_config).pack(fill=tk.X)

        man_frame = ttk.Frame(scen_grp)
        man_frame.pack(pady=5)
        ttk.Label(man_frame, text="Spawn @ F:").pack(side=tk.LEFT)
        self.ent_spawn = ttk.Entry(man_frame, width=3)
        self.ent_spawn.insert(0, "1")
        self.ent_spawn.pack(side=tk.LEFT)
        ttk.Button(man_frame, text="Add", command=self.manual_spawn).pack(side=tk.LEFT)

        # 2. Visualization
        vis_frame = ttk.Frame(self.root)
        vis_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.canvas = tk.Canvas(vis_frame, bg="white")
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 3. Stats Panel (Right side)
        stats_frame = ttk.Frame(vis_frame, width=250)
        stats_frame.pack(side=tk.RIGHT, fill=tk.Y)

        self.txt_stats = tk.Text(stats_frame, width=35, state=tk.DISABLED)
        self.txt_stats.pack(fill=tk.BOTH, expand=True)

        # 4. Status Bar
        self.status_var = tk.StringVar()
        self.status_var.set("Ready.")
        sts_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        sts_bar.pack(side=tk.BOTTOM, fill=tk.X)

    # --- Actions ---
    def apply_config(self):
        if self.sim.is_alive():
            messagebox.showerror("Error", "Stop simulation first.")
            return
        try:
            nf = int(self.ent_floors.get())
            ne = int(self.ent_elevs.get())
            if not (1 <= nf <= 20 and 1 <= ne <= 5):
                raise ValueError
            self.num_floors = nf
            self.num_elevators = ne
            self.building = Building(nf, ne)
            self.sim = Simulation(self.building, self.controller, self.on_sim_update)
            self.draw_canvas()
            messagebox.showinfo("Info", "Config applied.")
        except ValueError:
            messagebox.showerror("Error", "Floors: 1-20, Elevators: 1-5")

    def start_sim(self):
        self.sim.start_sim()
        self.status_var.set("Running...")

    def pause_sim(self):
        self.sim.pause_sim()
        self.status_var.set("Paused.")

    def stop_sim(self):
        success = self.sim.stop_sim()
        if success:
            self.status_var.set("Stopped.")
            self.show_final_report()
            # Re-init sim for next run
            self.building = Building(self.num_floors, self.num_elevators)
            self.sim = Simulation(self.building, self.controller, self.on_sim_update)
            self.draw_canvas()
        else:
            messagebox.showwarning("Cannot Stop", "Elevators must be empty and stopped.")

    def change_strategy(self):
        self.controller.set_strategy(self.strat_var.get())

    def speed_up(self):
        self.sim.speed_multiplier *= 2.0
        self.lbl_speed.config(text=f"x{self.sim.speed_multiplier}")

    def slow_down(self):
        self.sim.speed_multiplier /= 2.0
        self.lbl_speed.config(text=f"x{self.sim.speed_multiplier}")

    def toggle_fire(self):
        if not self.sim.fire_alarm:
            self.sim.trigger_fire()
            self.fire_btn.config(text="STOP FIRE", style="Accent.TButton")  # Needs theme or ignore style
        else:
            self.sim.stop_fire()
            self.fire_btn.config(text="FIRE ALARM")

    def manual_spawn(self):
        try:
            f = int(self.ent_spawn.get())
            if 1 <= f <= self.num_floors:
                p = Person(f, time.time())
                self.building.add_person(p)
            else:
                raise ValueError
        except:
            pass

    def import_scenario(self):
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if path:
            try:
                with open(path, 'r') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self.sim.load_scenario(data)
                        messagebox.showinfo("Success", "Scenario loaded.")
            except Exception as e:
                messagebox.showerror("Error", str(e))

    def export_config(self):
        path = filedialog.asksaveasfilename(defaultextension=".json")
        if path:
            cfg = {
                "num_floors": self.num_floors,
                "num_elevators": self.num_elevators
            }
            with open(path, 'w') as f:
                json.dump(cfg, f)

    # --- Visualization ---
    def on_sim_update(self):
        # Thread-safe trigger
        pass

    def periodic_ui_refresh(self):
        self.draw_canvas()
        self.update_stats_text()

        sim_time = getattr(self.sim, 'sim_time_accumulator', 0.0)
        transported = sum(e.people_transported for e in self.building.elevators)
        self.status_var.set(f"Time: {sim_time:.1f}s | Transported: {transported}")

        self.root.after(100, self.periodic_ui_refresh)

    def update_stats_text(self):
        self.txt_stats.config(state=tk.NORMAL)
        self.txt_stats.delete(1.0, tk.END)

        txt = f"Strategy: {self.strat_var.get()}\n\n"
        txt += "--- Elevators ---\n"
        for e in self.building.elevators:
            status = "MOVING" if e.velocity != 0 else ("OPEN" if e.doors_open else "IDLE")
            dr = "UP" if e.velocity > 0 else ("DOWN" if e.velocity < 0 else "-")
            txt += f"E{e.id}: F{e.current_floor:.1f} [{dr}] {status}\n"
            txt += f"    Ppl: {len(e.passengers)}/{e.capacity} | Trgt: {e.targets}\n"

        txt += "\n--- Queues ---\n"
        for f, q in self.building.waiting_queues.items():
            if q:
                txt += f"Floor {f}: {len(q)} waiting\n"

        self.txt_stats.insert(tk.END, txt)
        self.txt_stats.config(state=tk.DISABLED)

    def draw_canvas(self):
        self.canvas.delete("all")
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()

        if w < 10: return

        fh = h / (self.num_floors + 1)  # Floor height
        ew = w / (self.num_elevators + 2)  # Elevator width (visual)

        # Draw Floors
        for i in range(self.num_floors):
            y = h - (i + 1) * fh
            self.canvas.create_line(0, y, w, y, fill="#ccc")
            self.canvas.create_text(10, y - 10, text=f"F{i + 1}", anchor=tk.W)

            # Draw Waiting People (circles)
            q = self.building.waiting_queues.get(i + 1, [])
            for idx, p in enumerate(q):
                px = 40 + idx * 10
                self.canvas.create_oval(px, y - 15, px + 8, y - 7, fill="blue")

        # Draw Elevators
        for idx, e in enumerate(self.building.elevators):
            x_center = (idx + 1) * ew + 50
            y_bottom = h - (e.current_floor - 1) * fh - fh
            y_top = y_bottom - fh + 5

            # Shaft
            self.canvas.create_rectangle(x_center - 15, 0, x_center + 15, h, outline="#eee")

            # Cab
            color = "green" if e.doors_open else "gray"
            if self.sim.fire_alarm: color = "red"

            # Position interpolation
            rect_y_bot = h - (e.current_floor - 1) * fh - 5
            rect_y_top = rect_y_bot - (fh - 10)

            self.canvas.create_rectangle(x_center - 12, rect_y_top, x_center + 12, rect_y_bot, fill=color,
                                         outline="black")
            self.canvas.create_text(x_center, (rect_y_top + rect_y_bot) / 2, text=str(len(e.passengers)), fill="white")

    def show_final_report(self):
        stats = self.sim.get_stats()

        report = "=== FINAL REPORT ===\n\n"
        report += f"Total Transported: {stats['total_transported']}\n"
        report += f"Simulation Time: {stats['sim_time']:.2f}s\n"
        report += f"Fire Alarms: {stats['fire_alarms']} (Duration: {stats['fire_duration']:.1f}s)\n\n"

        report += "Per Elevator Stats:\n"
        for e in stats['elevators']:
            idle_pct = (e.empty_trips / e.trips * 100) if e.trips > 0 else 0
            report += f"E{e.id}: Trips={e.trips}, Idle={idle_pct:.1f}%, Ppl={e.people_transported}\n"

        # Save to file option
        res = messagebox.askyesno("Report", report + "\n\nSave to JSON?")
        if res:
            path = filedialog.asksaveasfilename(defaultextension=".json")
            if path:
                # Serialize simple dict
                out = {
                    "general": stats,
                    "elevators": [{"id": e.id, "trips": e.trips, "idle_trips": e.empty_trips} for e in
                                  stats['elevators']]
                }
                with open(path, 'w') as f:
                    # Remove non-serializable objects from 'stats' before dump if any
                    del out['general']['elevators']
                    json.dump(out, f, indent=4)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = MainApp()
    app.run()