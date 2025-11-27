from typing import List, Optional
from models import Elevator, Person, Building


class Controller:
    def __init__(self, strategy_name="min_wait"):
        self.strategy_name = strategy_name

    def set_strategy(self, name: str):
        self.strategy_name = name

    def assign(self, building: Building):
        """Распределяет вызовы по лифтам."""
        for floor, queue in building.waiting_queues.items():
            if not queue:
                continue

            # Берем первого человека как представителя вызова с этого этажа
            person = queue[0]

            # Если кто-то уже едет на этот этаж чтобы забрать людей, пропускаем
            # (Упрощение: считаем, что лифт заберет всех, если есть место)
            assigned = False
            for e in building.elevators:
                if floor in e.targets and not e.passengers:  # e.passengers check prevents stopping if full logic implies bypass
                    # Но по ТЗ лифт должен останавливаться.
                    # Проверяем, едет ли он в ту же сторону, куда хочет человек?
                    # В данной реализации упростим: если этаж есть в целях, считаем его назначенным.
                    assigned = True
                    break
            if assigned:
                continue

            best_elevator = self._choose_elevator(building.elevators, floor, person.target)
            if best_elevator:
                best_elevator.add_target(floor)

    def _choose_elevator(self, elevators: List[Elevator], origin_floor: int, target_floor: Optional[int]) -> Optional[
        Elevator]:
        if self.strategy_name == "min_wait":
            return self._strategy_min_wait(elevators, origin_floor)
        elif self.strategy_name == "min_idle":
            return self._strategy_min_idle(elevators, origin_floor)
        return elevators[0]

    def _strategy_min_wait(self, elevators: List[Elevator], origin: int) -> Elevator:
        """Выбирает лифт, который приедет быстрее всего."""
        best_e = None
        min_score = float('inf')

        for e in elevators:
            if len(e.passengers) >= e.capacity:
                score = float('inf')  # Полный
            else:
                distance = abs(e.current_floor - origin)
                # Штраф, если лифт едет в другую сторону
                if e.direction == "up" and origin < e.current_floor:
                    distance += e.current_floor * 2
                elif e.direction == "down" and origin > e.current_floor:
                    distance += (20 - e.current_floor) * 2  # примерная эвристика

                score = distance / e.max_speed + len(e.targets) * 2  # +2 сек на каждую остановку

            if score < min_score:
                min_score = score
                best_e = e
        return best_e

    def _strategy_min_idle(self, elevators: List[Elevator], origin: int) -> Elevator:
        """Минимизация холостого хода: выбираем ближайший или тот, у кого меньше всего поездок."""
        # Сначала ищем лифты, которые уже едут в попутном направлении
        candidates = []
        for e in elevators:
            if len(e.passengers) >= e.capacity: continue
            is_on_way_up = e.direction == "up" and e.current_floor <= origin
            is_on_way_down = e.direction == "down" and e.current_floor >= origin
            if is_on_way_up or is_on_way_down or e.direction == "idle":
                candidates.append(e)

        if not candidates:
            candidates = elevators

        # Из кандидатов выбираем того, кто ближе
        return min(candidates, key=lambda e: abs(e.current_floor - origin))