import threading
import time
import json
from typing import List, Dict, Any, Optional
from models import Building, Person
from controller import Controller


class Simulation(threading.Thread):
    def __init__(self, building: Building, controller: Controller, ui_callback=None):
        super().__init__(daemon=True)
        self.building = building
        self.controller = controller
        self.ui_callback = ui_callback

        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()  # Running by default
        self.lock = threading.RLock()

        self.speed_multiplier = 1.0
        self.sim_start_time: Optional[float] = None
        self.last_tick_time: Optional[float] = None

        # Scenario
        self.scenario: List[Dict] = []

        # Fire Alarm
        self.fire_alarm = False
        self.fire_start_time = None
        self.total_fire_duration = 0.0
        self.fire_alarms_count = 0

    def load_scenario(self, events: List[Dict]):
        # Sort by time
        self.scenario = sorted(events, key=lambda x: x.get('time', 0))

    def run(self):
        self.sim_start_time = time.time()
        self.last_tick_time = time.time()
        scenario_idx = 0

        while not self._stop_event.is_set():
            self._pause_event.wait()  # Блокирует поток, если пауза

            now = time.time()
            real_dt = now - self.last_tick_time
            self.last_tick_time = now

            dt = real_dt * self.speed_multiplier
            elapsed_sim_time = (now - self.sim_start_time)  # Это реальное время, для сценария надо скейлить?
            # Упрощение: сценарий выполняется по реальному времени * speed, но сложнее синхронизировать.
            # Будем считать scenario 'time' как "секунд симуляции". Нам нужен счетчик sim_time.

            if not hasattr(self, 'sim_time_accumulator'):
                self.sim_time_accumulator = 0.0
            self.sim_time_accumulator += dt

            with self.lock:
                # 1. Scenario Events
                while scenario_idx < len(self.scenario):
                    ev = self.scenario[scenario_idx]
                    if ev['time'] <= self.sim_time_accumulator:
                        self._process_event(ev)
                        scenario_idx += 1
                    else:
                        break

                # 2. Person Logic
                for p in list(self.building.people):
                    # Choosing state (3s)
                    if p.state == "choosing":
                        if (now - p.created_at) * self.speed_multiplier >= 3.0:
                            # Исправлено: условие "в течение 3 секунд".
                            # Здесь мы просто ждем 3 "симуляционных" секунды (примерно)
                            # Или можно упростить: (now - created) > 3/speed
                            p.choose_target(self.building.num_floors)
                            self.building.waiting_queues[p.origin].append(p)

                    # Delivered cleanup (3s existence)
                    elif p.state == "delivered" and p.delivered_at:
                        if (now - p.delivered_at) * self.speed_multiplier >= 3.0:
                            self.building.people.remove(p)

                    # Fire evacuation (3s to disappear)
                    elif p.state == "evacuated":
                        # Можно добавить таймер, пока удаляем сразу или через 3 сек
                        if (
                                now - p.delivered_at) * self.speed_multiplier >= 3.0:  # delivered_at используется как время эвакуации
                            self.building.people.remove(p)

                # 3. Elevator Logic
                if self.fire_alarm:
                    self._handle_fire_logic(dt, now)
                else:
                    self.controller.assign(self.building)
                    self._handle_normal_elevator_logic(dt, now)

            if self.ui_callback:
                self.ui_callback()

            # Sleep to save CPU, adjusted by speed
            time.sleep(max(0.01, 0.05 / max(0.1, self.speed_multiplier)))

    def _process_event(self, ev):
        action = ev.get('action')
        if action == 'spawn':
            count = ev.get('count', 1)
            floor = ev.get('floor', 1)
            target = ev.get('target', None)  # Optional logic override
            for _ in range(count):
                p = Person(floor, time.time())
                if target:  # Если в сценарии задан целевой этаж заранее
                    # Хак: переопределяем логику выбора
                    # p.state = "choosing" но мы запомним target
                    pass
                self.building.add_person(p)
        elif action == 'fire_start':
            self.trigger_fire()
        elif action == 'fire_end':
            self.stop_fire()

    def _handle_fire_logic(self, dt, now):
        # Лифты едут на 1 этаж без остановок
        for e in self.building.elevators:
            e.clear_targets()
            e.add_target(1)
            # Принудительно закрыть двери если не на 1 этаже
            if e.current_floor != 1 and e.doors_open:
                e.close_doors()

            moving = e.update_physics(dt)

            if not moving and e.current_floor == 1:
                e.open_doors()
                # Evacuate everyone inside
                for p in list(e.passengers):
                    p.state = "evacuated"
                    p.delivered_at = now  # timestamp for removal
                    e.passengers.remove(p)
                    self.building.people.remove(p)  # Или переместить в delivered список?
                    # ТЗ: "Все люди должны исчезнуть через 3 секунды".
                    # Оставим в self.building.people но пометим evacuated
                    self.building.people.append(p)

                    # Люди на этажах тоже эвакуируются
        for floor in self.building.waiting_queues:
            queue = self.building.waiting_queues[floor]
            while queue:
                p = queue.pop()
                p.state = "evacuated"
                p.delivered_at = now

    def _handle_normal_elevator_logic(self, dt, now):
        for e in self.building.elevators:
            # Physics
            moving = e.update_physics(dt)

            # Logic when stopped at target
            if not moving and (e.doors_open or (e.targets and e.targets[0] == int(e.current_floor))):
                floor = int(e.current_floor)
                if not e.doors_open:
                    e.open_doors()
                    self.door_timer = now  # Start door open timer logic could be added

                # Unload
                for p in list(e.passengers):
                    if p.target == floor:
                        e.passengers.remove(p)
                        e.people_transported += 1
                        p.state = "delivered"
                        p.delivered_at = now

                # Remove floor from targets
                if floor in e.targets:
                    e.targets.remove(floor)

                # Load (Кнопка "Ход" нажимается автоматически после посадки)
                queue = self.building.waiting_queues[floor]
                # Take people who want to go in the current direction (or any if idle)
                # Simple logic: take everyone fitting capacity
                while queue and len(e.passengers) < e.capacity:
                    p = queue[0]  # Peek
                    # Check direction match if not idle
                    # (Упрощение: берем всех, сортировка целей лифта разрулит)
                    p = queue.pop(0)
                    p.state = "in_elevator"
                    p.enter_time = now
                    e.passengers.append(p)
                    if p.target:
                        e.add_target(p.target)

                # Close doors and move (if targets exist)
                # In a real sim, we'd wait a bit. Here assume instant close after logic for simplicity
                # OR add a small delay logic variable.
                e.close_doors()

    # Controls
    def start_sim(self):
        if not self.is_alive():
            self._stop_event.clear()
            self.start()
        self.resume_sim()

    def pause_sim(self):
        self._pause_event.clear()

    def resume_sim(self):
        self._pause_event.set()

    def stop_sim(self):
        with self.lock:
            # Check condition: "Only if all elevators empty and stopped"
            for e in self.building.elevators:
                if e.passengers or e.velocity != 0 or e.current_floor != int(e.current_floor):
                    return False
            self._stop_event.set()
            self._pause_event.set()  # Ensure thread wakes up to exit
            return True

    def trigger_fire(self):
        with self.lock:
            if not self.fire_alarm:
                self.fire_alarm = True
                self.fire_start_time = time.time()
                self.fire_alarms_count += 1

    def stop_fire(self):
        with self.lock:
            if self.fire_alarm:
                self.fire_alarm = False
                if self.fire_start_time:
                    self.total_fire_duration += time.time() - self.fire_start_time
                    self.fire_start_time = None

    def get_stats(self):
        # Collect logic
        total_transported = sum(e.people_transported for e in self.building.elevators)
        return {
            "elevators": self.building.elevators,
            "total_transported": total_transported,
            "fire_alarms": self.fire_alarms_count,
            "fire_duration": self.total_fire_duration,
            "sim_time": self.sim_time_accumulator if hasattr(self, 'sim_time_accumulator') else 0
        }