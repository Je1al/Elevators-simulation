import time
import random
import math
from typing import List, Dict, Optional


class Person:
    """
    Модель человека.
    Жизненный цикл:
    Created -> Choosing (3s) -> Waiting -> InElevator -> Delivered -> Exiting (3s) -> Gone
    """
    _id_counter = 0

    def __init__(self, origin: int, created_at: float):
        Person._id_counter += 1
        self.id = Person._id_counter
        self.origin = origin
        self.target: Optional[int] = None
        self.created_at = created_at

        # Timestamps for stats
        self.decision_time: Optional[float] = None  # Когда выбрал этаж
        self.enter_time: Optional[float] = None  # Когда вошел в лифт
        self.delivered_at: Optional[float] = None  # Когда вышел из лифта

        self.state: str = "choosing"  # choosing, waiting, in_elevator, delivered, evacuated

    def choose_target(self, num_floors: int):
        """Выбор этажа. Не может быть равен текущему."""
        choices = [f for f in range(1, num_floors + 1) if f != self.origin]
        if not choices:
            choices = [1]  # Fallback
        self.target = random.choice(choices)
        self.decision_time = time.time()
        self.state = "waiting"

    def get_wait_time(self) -> float:
        if self.decision_time and self.enter_time:
            return self.enter_time - self.decision_time
        return 0.0


class Elevator:
    """
    Модель лифта с инкрементальной физикой.
    """

    def __init__(self, eid: int, capacity: int = 8, max_speed: float = 2.0, max_accel: float = 1.0):
        self.id = eid
        self.capacity = capacity
        self.max_speed = max_speed
        self.max_accel = max_accel

        self.current_floor: float = 1.0  # float для плавности
        self.velocity: float = 0.0
        self.doors_open: bool = False

        self.targets: List[int] = []
        self.passengers: List[Person] = []

        # Stats
        self.trips = 0
        self.empty_trips = 0
        self.people_transported = 0

        # Logic flags
        self.direction: str = "idle"  # "up", "down", "idle"

    def add_target(self, floor: int):
        if floor not in self.targets:
            self.targets.append(floor)
            self._sort_targets()

    def clear_targets(self):
        self.targets.clear()

    def _sort_targets(self):
        # Сортировка целей в зависимости от текущего направления
        if self.direction == "up":
            self.targets.sort()
        elif self.direction == "down":
            self.targets.sort(reverse=True)
        else:
            # Если стоим, едем к ближайшему
            self.targets.sort(key=lambda f: abs(self.current_floor - f))

    def update_physics(self, dt: float, floor_height: float = 3.0):
        """
        Обновляет позицию и скорость. Возвращает True, если лифт движется.
        """
        if self.doors_open:
            self.velocity = 0.0
            return False

        if not self.targets:
            self.velocity = 0.0
            self.direction = "idle"
            return False

        target_floor = self.targets[0]
        target_y = (target_floor - 1) * floor_height
        current_y = (self.current_floor - 1) * floor_height

        dist = target_y - current_y

        # Определяем желаемое направление
        if abs(dist) < 0.05:
            # Приехали
            self.current_floor = float(target_floor)
            self.velocity = 0.0
            return False  # Stopped to open doors

        # Расчет физики: ускорение/торможение
        direction_sign = 1.0 if dist > 0 else -1.0
        self.direction = "up" if direction_sign > 0 else "down"

        # Дистанция торможения: v^2 / (2*a)
        stop_dist = (self.velocity ** 2) / (2 * self.max_accel)

        if abs(dist) <= stop_dist + 0.1:
            # Пора тормозить
            accel = -self.max_accel * (1.0 if self.velocity > 0 else -1.0)
        else:
            # Можно разгоняться
            if abs(self.velocity) < self.max_speed:
                accel = self.max_accel * direction_sign
            else:
                accel = 0.0  # Крейсерская скорость

        # v = v0 + at
        self.velocity += accel * dt

        # Лимит скорости (на всякий случай)
        if self.velocity > self.max_speed: self.velocity = self.max_speed
        if self.velocity < -self.max_speed: self.velocity = -self.max_speed

        # x = x0 + vt
        current_y += self.velocity * dt

        # Обратная конвертация в этажи
        self.current_floor = (current_y / floor_height) + 1
        return True

    def open_doors(self):
        if not self.doors_open:
            self.doors_open = True
            # Фиксируем статистику поездки
            self.trips += 1
            if not self.passengers:
                self.empty_trips += 1

    def close_doors(self):
        self.doors_open = False


class Building:
    def __init__(self, num_floors: int, num_elevators: int):
        self.num_floors = num_floors
        self.elevators = [Elevator(i + 1) for i in range(num_elevators)]
        self.people: List[Person] = []
        self.waiting_queues: Dict[int, List[Person]] = {f: [] for f in range(1, num_floors + 1)}

    def add_person(self, p: Person):
        self.people.append(p)
        # В очередь он попадает только после выбора этажа (через 3 сек)