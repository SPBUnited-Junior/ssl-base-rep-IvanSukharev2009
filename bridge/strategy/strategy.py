"""Верхнеуровневый код стратегии"""

# pylint: disable=redefined-outer-name

import math
from enum import Enum
from time import time
from typing import Optional

import bridge.router.waypoint as wp
from bridge import const
from bridge.auxiliary import aux, fld, rbt
from bridge.processors.referee_state_processor import Color as ActiveTeam
from bridge.processors.referee_state_processor import State as GameStates

class BallStatus(Enum):
    Active = 0
    Passive = 1
    Ready = 2


class BallStatusInsidePoly(Enum):
    NotInsidePoly = 0
    InsidePoly = 1


class FlagToPasses(Enum):
    FALSE = 0
    TRUE_ATTACKER1 = 1
    TRUE_ATTACKER2 = 2
    RELEASE = 3


class Strategy:
    """Основной класс с кодом стратегии.0

    Основная логика разбита на отдельные методы для улучшения читаемости и поддержки.
    """

    def __init__(
        self,
        dbg_game_status: GameStates = GameStates.RUN,
    ) -> None:
        self.game_status = dbg_game_status
        self.active_team: ActiveTeam = ActiveTeam.ALL

        self.old_ball = aux.Point(0, 0)
        self.flag = False
        self.ball_status = BallStatus.Passive
        self.ball_status_poly = BallStatusInsidePoly.NotInsidePoly
        self.passes_status = FlagToPasses.FALSE
        self.old_pos = aux.Point(0, 0)

        self.Robot_receiving_the_pass = 0
        # Индексы наших роботов
        self.idx_gk = 0
        self.idx1 = 1
        self.idx2 = 2

        # Индексы вражеских роботов
        self.enemy_idx_gk = 0
        self.enemy_idx1 = 1
        self.enemy_idx2 = 2

        self.pos_holds_timer = 0
        self.timer_stop_dribbler = 0
        self.prev_pos = aux.Point(0, 0)
        self.pos_to_pas = aux.Point(0, 0)
        self.old_pos = aux.Point(0, 0)

        self.list_optimal_point = []
        for x in range(-2000, 2000, 500):
            for y in range(-1300, 1300, 500):
                self.list_optimal_point.append(aux.Point(x, y))
        print(len(self.list_optimal_point))

    def change_game_state(
        self, new_state: GameStates, upd_active_team: ActiveTeam
    ) -> None:
        """Изменение состояния игры и цвета команды"""
        self.game_status = new_state
        self.active_team = upd_active_team

    def process(self, field: fld.Field) -> list[wp.Waypoint]:
        """
        Рассчитать конечные точки для каждого робота.
        Здесь лишь объединяем результаты работы вспомогательных методов.
        """
        # Инициализируем waypoints для каждого робота
        waypoints: list[wp.Waypoint] = []
        for i in range(const.TEAM_ROBOTS_MAX_COUNT):
            waypoints.append(
                wp.Waypoint(
                    field.allies[i].get_pos(),
                    field.allies[i].get_angle(),
                    wp.WType.S_STOP,
                )
            )

        ball = field.ball.get_pos()

        print(self.game_status)

        # ::NOTE:: думаю уже пора как-то обобщить эту логику, чтобы не прописывать id своих роботов и роботов соперника руками.
        # Что-то вроде такого:
        # list_ally = []
        # for robot, idx in field.allies:
        #     if robot.is_used():
        #         list_ally.append(robot)

        # Получаем позиции наших роботов
        goalkeeper = field.allies[self.idx_gk].get_pos()
        attacker1 = field.allies[self.idx1].get_pos()
        attacker2 = field.allies[self.idx2].get_pos()
        list_ally = [attacker1, attacker2]

        # Получаем позиции вражеских роботов
        enemy_goalkeeper = field.enemies[self.enemy_idx_gk].get_pos()
        enemy_attacker1 = field.enemies[self.enemy_idx1].get_pos()
        enemy_attacker2 = field.enemies[self.enemy_idx2].get_pos()

        list_enemy = [enemy_goalkeeper, enemy_attacker1, enemy_attacker2]
        attacker = self._the_nearest_robot(list_enemy, ball)[0]

        # Первоначальное значение направления
        enemy_goal_arg = field.enemy_goal.center.arg()
        self.game_status = GameStates.RUN
        if self.game_status == GameStates.HALT:
            return waypoints
        
        elif self.game_status == GameStates.STOP:
            waypoints[self.idx1] = wp.Waypoint(
                aux.Point(500, 1000), 
                0, 
                wp.WType.S_ENDPOINT
            )

            waypoints[self.idx2] = wp.Waypoint(
                aux.Point(500, -1000), 
                0, 
                wp.WType.S_ENDPOINT
            ) 
            return waypoints
        elif self.game_status == GameStates.STOP:
            return waypoints
        
        elif self.game_status == GameStates.PREPARE_PENALTY:
            if we_active:
                waypoints[self.idx1] = wp.Waypoint(
                    ball - field.ally_goal.eye_forw * 300, 
                    ball.arg, 
                    wp.WType.S_ENDPOINT
                )
            else:
                pos_gk, angle_gk, flag_kick_gk = self._process_goalkeeper(field, ball, attacker, goalkeeper, attacker)
                waypoints[self.idx_gk] = wp.Waypoint(
                    pos_gk, 
                    angle_gk, 
                    flag_kick_gk
                )

        elif self.game_status == GameStates.PENALTY:
            if we_active:
                field.allies[self.idx1].dribbler_speed_ = 10
                kick_delta = 150

                if abs(aux.get_angle_between_points(enemy_goalkeeper, ball, field.enemy_goal.up)) > abs(
                    aux.get_angle_between_points(enemy_goalkeeper, ball, field.enemy_goal.down)
                ):
                    target = aux.Point(field.enemy_goal.center.x, kick_delta)
                else:
                    target = aux.Point(field.enemy_goal.center.x, -kick_delta)

                waypoints[self.idx1] = wp.Waypoint(ball, aux.angle_to_point(ball, target), wp.WType.S_BALL_KICK)
            else:
                pos_gk, angle_gk, flag_kick_gk = self._process_goalkeeper(field, ball, attacker, goalkeeper, attacker)
                waypoints[self.idx_gk] = wp.Waypoint(
                    pos_gk, 
                    angle_gk, 
                    flag_kick_gk
                )
        elif self.game_status == GameStates.PREPARE_KICKOFF:
            pass
            


        # Вызываем вспомогательный метод для расчёта позиции вратаря
        # Здесь логика определения "attacker" внутри метода не меняется, хоть в оригинале оно переопределялось
        # Передаём позицию для нападающего из наших (idx2) как attacker.
        pos_gk, angle_gk, flag_kick_gk = self._process_goalkeeper(field, ball, attacker, goalkeeper, attacker1)
        
        # ::NOTE:: опять же, мне не нравится жесткая привязка к количеству роботов. Что если одного удалят, например?
        # Вызываем метод для расчёта позиций нападающих
        (
            pos_attacker1,
            angle_attacker1,
            flag_kick_ball1,
            pos_attacker2,
            angle_attacker2,
            flag_kick_ball2,
        ) = self._process_attackers(
            field,
            ball,
            list_ally,
            list_enemy,
            attacker1,
            attacker2,
            enemy_attacker1,
            enemy_attacker2,
        )

        # ::NOTE:: аналогично ъ
        # Заполняем массив waypoint’ов для роботов
        waypoints[self.idx_gk] = wp.Waypoint(
            pos_gk, 
            angle_gk, 
            flag_kick_gk
        )

        waypoints[self.idx1] = wp.Waypoint(
            pos_attacker1, 
            angle_attacker1, 
            flag_kick_ball1
        )

        waypoints[self.idx2] = wp.Waypoint(
            pos_attacker2, 
            angle_attacker2, 
            flag_kick_ball2
        )
        
        self.old_ball = field.ball_start_point or aux.Point(0, 0)
        return waypoints

    # ======================== Вспомогательные методы ========================

    def _passes(self, ball: aux.Point, robot: aux.Point) -> aux.Point:
        """
        Возвращает ближайшую точку на линии от старого положения мяча до робота.
        (Было вложенной функцией passes, вынесено для переиспользования.)
        """
        return aux.closest_point_on_line(self.old_ball, ball, robot, "R")

    def _pass(self, ball: aux.Point, robot_from: aux.Point, robot_to: aux.Point) -> tuple[aux.Point, float]:
        """
        Рассчитывает позицию и угол для паса между роботами.
        (Было вложенной функцией pas.)
        """
        # Определяем большие границы для проверки попадания в полигон
        lt = [
            aux.Point(robot_to.x + 1000, robot_to.y + 1000),
            aux.Point(robot_to.x + 1000, robot_to.y - 1000),
            aux.Point(robot_to.x - 1000, robot_to.y - 1000),
            aux.Point(robot_to.x - 1000, robot_to.y + 1000),
        ]
        candidate = self._passes(ball, robot_to)
        pos_f = candidate if aux.is_point_inside_poly(candidate, lt) else robot_to
        return pos_f, (robot_to - ball).arg()


    def _circle_to_two_tangents(
        self, radius: float, point: aux.Point, point1: aux.Point, point2: aux.Point
    ) -> aux.Point:
        """
        Вычисляет точку на окружности между двумя касательными.
        Добавлена проверка на деление на ноль при вычислении синуса.
        """
        if point1.y > point2.y:
            lower_point = point2
            top_point = point1
        else:
            lower_point = point1
            top_point = point2
        angle = aux.get_angle_between_points(point, top_point, lower_point) / 2
        sin_val = math.sin(angle) if abs(math.sin(angle)) > 1e-6 else 1e-6
        center = lower_point - point
        center = center.unity() * (radius / abs(sin_val))
        center = aux.rotate(center, -angle)
        return center + point  # Используем point как исходную точку (аналог ball в оригинале)

    def _the_nearest_robot(self, lst: list[aux.Point], pnt: aux.Point) -> tuple[aux.Point, float]:
        """
        Ищет ближайшего робота из списка по расстоянию до pnt.
        """
        min_mag = None
        nearest_robot = None
        for robot in lst:
            dist = (pnt - robot).mag()
            if min_mag is None or dist < min_mag:
                min_mag = dist
                nearest_robot = robot
        return nearest_robot, min_mag

    def _block_robot_to_ball(self, ball: aux.Point, enemy_robot: aux.Point, robot: aux.Point) -> aux.Point:
        """
        Вычисляет точку, в которой робот блокирует путь мяча от вражеского робота.
        """
        return aux.closest_point_on_line(ball, enemy_robot, robot, "S")

    def _optimal_point(
        self, robot: aux.Point, ball: aux.Point, enemy_list: list[aux.Point], candidate_points: list[aux.Point], dist: int, mid: aux.Point, field: fld.Field
    ) -> aux.Point:
        """
        Находит оптимальную точку для паса, сравнивая расстояния.
        """
        maxim = 0
        res = aux.Point(0, 0)
        for cand in candidate_points:
            minim = 10000
            flag_to_point = True
            if aux.dist(robot, cand) > dist:
                flag_to_point = False
                continue
            for enemy in enemy_list:
                if aux.dist(enemy, cand) < 300:
                    flag_to_point = False
                    break
                minim = min((enemy - aux.closest_point_on_line(ball, cand, enemy, "S")).mag(), minim)
            if (self.check_point(field, cand, enemy_list) > maxim and minim > const.ROBOT_R + 60 and flag_to_point and (mid is 0 or aux.dist(robot, aux.closest_point_on_line(ball, mid, robot)) > const.ROBOT_R + 60)):
                res = cand
                maxim = self.check_point(field, cand, enemy_list)
        field.strategy_image.draw_dot(res, (255, 0, 255), 3)
        return res

    def _defer(self, robot: aux.Point, ball: aux.Point, field: fld.Field) -> aux.Point:
        """
        Вычисляет позицию для защиты ворот с отступлением.
        Отрисовка линий оставлена для визуальной отладки.
        """

        # ::NOTE:: этот блок кода очень страшно выглядит и не читается
        # опять же, стоит попробовать обобщить его, как и многое другое.
        # Старайся писать код, которые корректно работает с любым разумным количеством роботов(хоть с 1, хоть с 50)

        line_down = aux.closest_point_on_line(ball, field.ally_goal.down, robot, "S")
        offset_down = (aux.rotate(field.ally_goal.down - ball, math.pi / 2)).unity() * const.ROBOT_R
        line_up = aux.closest_point_on_line(ball, field.ally_goal.up, robot, "S")
        offset_up = (aux.rotate(field.ally_goal.up - ball, math.pi / 2)).unity() * const.ROBOT_R
        down_dist = (line_down + offset_down - robot).mag()
        up_dist = (line_up - offset_up - robot).mag()

        field.strategy_image.draw_line(ball, field.ally_goal.down, (255, 0, 255), 3)
        field.strategy_image.draw_line(ball, field.ally_goal.up, (255, 0, 255), 3)
        field.strategy_image.draw_line(ball, line_up - offset_up, (255, 0, 255), 3)
        field.strategy_image.draw_line(ball, line_down + offset_down, (255, 255, 255), 5)

        if down_dist < up_dist:
            ans = line_down + offset_down
            if ((ans - robot).mag() > 40 or not aux.is_point_inside_poly(robot, [ball, field.ally_goal.up, field.ally_goal.down])) and aux.is_point_inside_poly(ans, [ball, field.ally_goal.up, field.ally_goal.down]):
                return ans
            else:
                return self._circle_to_two_tangents(const.ROBOT_R, ball, field.ally_goal.down, field.ally_goal.up)
        else:
            ans = line_up - offset_up
            if ((ans - robot).mag() > 40 or not aux.is_point_inside_poly(robot, [ball, field.ally_goal.up, field.ally_goal.down])) and aux.is_point_inside_poly(ans, [ball, field.ally_goal.up, field.ally_goal.down]):
                return ans
            else:
                return self._circle_to_two_tangents(const.ROBOT_R, ball, field.ally_goal.down, field.ally_goal.up)

    def _process_goalkeeper(
        self, field: fld.Field, ball: aux.Point, attacker: aux.Point, goalkeeper: aux.Point, pass_receiver
    ) -> tuple[aux.Point, float, wp.WType]:
        """
        Обрабатывает логику вратаря:
          - Если противник близко к мячу, рассчитываем траекторию спасения;
          - Если противник далеко, корректируем позицию вратаря в зависимости от положения мяча.
        Также обрабатывается ситуация, когда мяч движется в зоне ворот.
        """
        # Если противник близко к мячу (готовится к удару)
        if (ball - attacker).mag() < 250:
            pos = aux.closest_point_on_line(attacker, ball, goalkeeper, "R")
            cords1 = aux.get_line_intersection(attacker, ball, field.ally_goal.up, field.ally_goal.down, "LL")
            if cords1 is not None:
                result = aux.get_line_intersection(
                    ball,
                    cords1,
                    field.ally_goal.frw_up - field.ally_goal.eye_forw,
                    field.ally_goal.center_up,
                    "LS",
                )
                if result is aux.Point:
                    result = aux.get_line_intersection(
                        ball,
                        cords1,
                        field.ally_goal.frw_down - field.ally_goal.eye_forw,
                        field.ally_goal.center_down,
                        "LS",
                    )

                    pos = aux.closest_point_on_line(result, cords1, goalkeeper, "S")
                    field.strategy_image.draw_line(result, cords1, (0, 0, 255), 5)
                    field.strategy_image.draw_line(pos, attacker, (0, 0, 255), 5)
                    if aux.dist(pos, self.prev_pos) > 80:
                        self.pos_holds_timer = time()
                    self.prev_pos = pos
                    if time() - self.pos_holds_timer < 1:
                        pos = field.ally_goal.center + field.ally_goal.eye_forw * 300
                    field.strategy_image.draw_dot(pos, (0, 0, 0), 40)
            self.ball_status = BallStatus.Ready
        else:
            # Если противник не у мяча
            pos = field.ally_goal.center + field.ally_goal.eye_forw * 300
            angle = field.enemy_goal.center.arg()

        # Если вратарь готов (мяч ранее отмечен как Ready) и противник далеко
        if False:
            cords1 = aux.Point(10000, 0)
            cords1.arg = aux.rotate(field.allies[self.idx_gk].get_angle())
            
            if cords1 is not None:
                cords_sr = cords1
                if not aux.is_point_inside_poly(ball, field.ally_goal.hull):
                    result = aux.get_line_intersection(
                        attacker,
                        cords1,
                        field.ally_goal.frw_up - field.ally_goal.eye_forw,
                        field.ally_goal.frw_down - field.ally_goal.eye_forw,
                        "LL",
                    )
                    if result is None:
                        result = aux.get_line_intersection(
                                attacker,
                                cords1,
                                field.ally_goal.frw_down - field.ally_goal.eye_forw * 1,
                                field.ally_goal.center_down,
                                "LS",
                        )
                    if result is None:
                        result = aux.get_line_intersection(
                                attacker,
                                cords1,
                                field.ally_goal.frw_up - field.ally_goal.eye_forw * 1,
                                field.ally_goal.frw_down - field.ally_goal.eye_forw * 1,
                                "LL",
                            )

                    pos = aux.closest_point_on_line(result, cords_sr, goalkeeper, "S")
                    field.strategy_image.draw_line(result, cords_sr, (0, 0, 255), 5)
                    field.strategy_image.draw_line(pos, attacker, (0, 0, 255), 5)
                    field.strategy_image.draw_dot(pos, (0, 0, 0), 40)
            else:
                pass  # ::NOTE:: do sth if cords1 and coords2 is None
            if aux.is_point_inside_poly(ball, field.ally_goal.hull):
                self.ball_status_poly = BallStatusInsidePoly.InsidePoly

        # Если мяч остановился после удара в зоне ворот
        if field.is_ball_stop_near_goal():
            # Используем _pas для расчёта данных паса (здесь лишь для установки флага удара)
            _, _ = self._pass(ball, goalkeeper, pass_receiver)
            flag_to_kick_goalkeeper = wp.WType.S_BALL_KICK
        else:
            flag_to_kick_goalkeeper = wp.WType.S_ENDPOINT

        # Если мяч вылетел за зону ворот после удара
        if (
            self.ball_status_poly == BallStatusInsidePoly.InsidePoly
            and not aux.is_point_inside_poly(ball, field.ally_goal.hull)
        ):
            self.ball_status_poly = BallStatusInsidePoly.NotInsidePoly
            self.ball_status = BallStatus.Passive
            pos = field.ally_goal.center + field.ally_goal.eye_forw * 300

        # Если позиция вне зоны ворот, корректируем позицию и направление
        if not aux.is_point_inside_poly(pos, field.ally_goal.hull):
            pos = goalkeeper
            angle = field.enemy_goal.center.arg()
        else:
            angle = field.enemy_goal.center.arg()
        field.strategy_image.draw_dot(pos, (255, 0, 0), 40)
        self.old_pos = pos
        return pos, angle, flag_to_kick_goalkeeper

    def check_point(
        self,
        field: fld.Field,
        ball: aux.Point,
        list_enemy: list[aux.Point],     
    ) -> int:
        # Расчёт касательных к вражеским роботам
        result_cords = []
        for enemy in list_enemy:
            tangent_points = aux.get_tangent_points(enemy, ball, const.ROBOT_R)
            if len(tangent_points) >= 2:
                cords_peresch = []
                for count in range(2):
                    result = aux.get_line_intersection(
                        ball,
                        tangent_points[count],
                        field.enemy_goal.center_up,
                        field.enemy_goal.center_down,
                        "RL",
                    )
                    if result is not None:
                        cords_peresch.append(result.y)
                if len(cords_peresch) == 1:
                    if ball.y < 0:
                        result_cords.append(sorted([cords_peresch[0], 1500]))
                    else:
                        result_cords.append(sorted([cords_peresch[0], -1500]))
                if len(cords_peresch) > 1:
                    result_cords.append(sorted(cords_peresch))
        result_cords = sorted(result_cords)
        maximum = 0

        if (const.POLARITY == -1 and const.COLOR == const.Color.BLUE) or (const.POLARITY == 1 and const.COLOR == const.Color.YELLOW):
            field_up = field.enemy_goal.up
            field_down = field.enemy_goal.down
        else:
            field_down = field.enemy_goal.up
            field_up = field.enemy_goal.down

        mid = 0
        left = min(result_cords[0][0], field_down.y) if result_cords else None
        right = field_up.y
        count = 0
        arg_attacker = (field.enemy_goal.center - ball).arg()
        while count < len(result_cords):
            if left is not None and (left > right and right >= field_up.y and left <= field_down.y and left - right > 100):
                maximum = left - right
                mid = aux.Point(field_up.x, (left + right) // 2)
                break
            right = min(max(result_cords[count][1], right), field_down.y)
            count += 1
            if count < len(result_cords):
                left = result_cords[count][0]
            if left > field_down.y:
                left = field_down.y 

        if count != 0:
            count -= 1
        while count < len(result_cords) and right < field_down.y:
            if left > right:
                if left > field_down.y:
                    left = field_down.y
                if left - right > maximum and left - right > 100 and right >= field_up.y:
                    maximum = left - right
                    mid = aux.Point(field_up.x, (left + right) // 2)
            right = max(result_cords[count][1], right)
            count += 1
            if count < len(result_cords):
                left = result_cords[count][0]
        if left is None:
            left = field_down.y
        if left <= field_down.y:
            left = field_down.y
            if left - right > maximum and left > right and left - right > 100 and right >= field_up.y:
                maximum = left - right
                mid = aux.Point(field_up.x, (left + right) // 2)

        return maximum
        

    def _process_attackers(
        self,
        field: fld.Field,
        ball: aux.Point,
        list_ally: list[aux.Point],
        list_enemy: list[aux.Point],
        attacker1: aux.Point,
        attacker2: aux.Point,
        enemy_attacker1:aux.Point,
        enemy_attacker2:aux.Point
    ) -> tuple[aux.Point, float, wp.WType, aux.Point, float, wp.WType]:
        """
        Обрабатывает стратегию для нападающих:
          - Рассчитывает свободные зоны в воротах противника,
          - В зависимости от состояния паса и расстояния выбирает, кто бьёт по воротам, а кто принимает пас.
        """
        # Расчёт касательных к вражеским роботам
        result_cords = []
        for enemy in list_enemy:
            tangent_points = aux.get_tangent_points(enemy, ball, const.ROBOT_R)
            if len(tangent_points) >= 2:
                cords_peresch = []
                for count in range(2):
                    field.strategy_image.draw_dot(tangent_points[0], (255, 0, 0), 40)
                    field.strategy_image.draw_dot(tangent_points[1], (255, 0, 0), 40)
                    result = aux.get_line_intersection(
                        ball,
                        tangent_points[count],
                        field.enemy_goal.center_up,
                        field.enemy_goal.center_down,
                        "RL",
                    )
                    if result is not None:
                        cords_peresch.append(result.y)
                if len(cords_peresch) == 1:
                    if ball.y < 0:
                        result_cords.append(sorted([cords_peresch[0], 1500]))
                    else:
                        result_cords.append(sorted([cords_peresch[0], -1500]))
                elif len(cords_peresch) > 1:
                    result_cords.append(sorted(cords_peresch))
        for cordes in result_cords:
            field.strategy_image.draw_line(
                ball, aux.Point(field.enemy_goal.up.x, cordes[0]), (255, 0, 0), 3
            )
            field.strategy_image.draw_line(
                ball, aux.Point(field.enemy_goal.up.x, cordes[1]), (255, 0, 0), 3
            )
            field.strategy_image.draw_line(
                aux.Point(field.enemy_goal.up.x, cordes[0]),
                aux.Point(field.enemy_goal.up.x, cordes[1]),
                (255, 0, 0),
                3,
            )
        result_cords = sorted(result_cords)
        maximum = 0

        if (const.POLARITY == -1 and const.COLOR == const.Color.BLUE) or (const.POLARITY == 1 and const.COLOR == const.Color.YELLOW):
            field_up = field.enemy_goal.up
            field_down = field.enemy_goal.down
        else:
            field_down = field.enemy_goal.up
            field_up = field.enemy_goal.down

        mid = 0
        left = min(result_cords[0][0], field_down.y) if result_cords else None
        right = field_up.y
        count = 0
        arg_attacker = (field.enemy_goal.center - ball).arg()
        while count < len(result_cords):
            if left is not None and (left > right and right >= field_up.y and left <= field_down.y and left - right > 100):
                maximum = left - right
                mid = aux.Point(field_up.x, (left + right) // 2)
                break
            right = min(max(result_cords[count][1], right), field_down.y)
            count += 1
            if count < len(result_cords):
                left = result_cords[count][0]
            if left > field_down.y:
                left = field_down.y 

        if count != 0:
            count -= 1
        while count < len(result_cords) and right < field_down.y:
            if left > right:
                if left > field_down.y:
                    left = field_down.y
                if left - right > maximum and left - right > 100 and right >= field_up.y:
                    maximum = left - right
                    mid = aux.Point(field_up.x, (left + right) // 2)
            right = max(result_cords[count][1], right)
            count += 1
            if count < len(result_cords):
                left = result_cords[count][0]
        if left is None:
            left = field_down.y
        if left <= field_down.y:
            left = field_down.y
            if left - right > maximum and left > right and left - right > 100 and right >= field_up.y:
                maximum = left - right
                mid = aux.Point(field_up.x, (left + right) // 2)

        if mid is not 0:
            field.strategy_image.draw_dot(mid, (255, 0, 0), 40)
            arg_attacker = (mid - ball).arg()

        # Инициализация значений для нападающих по умолчанию
        pos_attacker1 = attacker1
        pos_attacker2 = attacker2
        angle_attacker1 = attacker1.arg()
        angle_attacker2 = attacker2.arg()
        flag_kick_ball1 = wp.WType.S_ENDPOINT
        flag_kick_ball2 = wp.WType.S_ENDPOINT

        # ::NOTE:: снова блок кода очень тяжело читается. Самое простое решение, как ни странно,
        # обобщить логику, тогда станет меньше ifов и читать код станет гораздо лучше

        # Обработка пасов, если ранее установлен соответствующий флаг
        if self.passes_status == FlagToPasses.TRUE_ATTACKER1:
            self.Robot_receiving_the_pass = field.allies[self.idx2]

            flag_kick_ball2 = wp.WType.S_ENDPOINT
            flag_kick_ball1 = wp.WType.S_ENDPOINT

            pos_attacker1 = attacker1
            angle_attacker1 = field.allies[self.idx1].get_angle()
            pos_attacker2, _ = self._pass(ball, attacker1, attacker2)
            angle_attacker2 = (ball - attacker2).arg()
            field.allies[self.idx2].set_dribbler_speed(15)
            if field.is_ball_in(self.Robot_receiving_the_pass):
                self.passes_status = FlagToPasses.RELEASE
                self.pos_to_pas = attacker2
                field.allies[self.idx2].set_dribbler_speed(0)
                self.timer_stop_dribbler = time()
            elif not field.is_ball_moves():
                self.passes_status = FlagToPasses.FALSE
                field.allies[self.idx2].set_dribbler_speed(0)
 
        elif self.passes_status == FlagToPasses.TRUE_ATTACKER2:
            self.Robot_receiving_the_pass = field.allies[self.idx1]

            flag_kick_ball2 = wp.WType.S_ENDPOINT
            flag_kick_ball1 = wp.WType.S_ENDPOINT

            pos_attacker2 = attacker2
            angle_attacker2 = field.allies[self.idx2].get_angle()
            pos_attacker1, _ = self._pass(ball, attacker2, attacker1)
            angle_attacker1 = (ball - attacker1).arg()
            field.allies[self.idx1].set_dribbler_speed(15)
            if field.is_ball_in(self.Robot_receiving_the_pass):
                self.passes_status = FlagToPasses.RELEASE
                self.pos_to_pas = attacker1
                field.allies[self.idx1].set_dribbler_speed(0)
                self.timer_stop_dribbler = time()
            elif not field.is_ball_moves():
                self.passes_status = FlagToPasses.FALSE
                field.allies[self.idx1].set_dribbler_speed(0)

        elif self.passes_status == FlagToPasses.RELEASE:
            
            if self.Robot_receiving_the_pass == field.allies[self.idx2]:
                angle_attacker2 = field.allies[self.idx2].get_angle()
                flag_kick_ball2 = wp.WType.S_ENDPOINT
                if time() - self.timer_stop_dribbler > 0.1:   
                
                    pos_attacker2 = self.pos_to_pas + (attacker2 - ball).unity() * (const.ROBOT_R * 1.5)
                    if aux.dist(attacker2, self.pos_to_pas + (attacker2 - ball).unity() * (const.ROBOT_R * 1.5)) < 20:
                        self.passes_status = FlagToPasses.FALSE

            else:
                angle_attacker1 = field.allies[self.idx1].get_angle()
                flag_kick_ball1 = wp.WType.S_ENDPOINT
                if time() - self.timer_stop_dribbler > 0.1:
                    pos_attacker1 = self.pos_to_pas + (attacker1 - ball).unity() * (const.ROBOT_R * 1.5)
                    if aux.dist(attacker1, self.pos_to_pas + (attacker1 - ball).unity() * (const.ROBOT_R * 1.5)) < 20:
                        self.passes_status = FlagToPasses.FALSE
        else:
            # Если враг ближе к мячу, выбираем стратегию блокирования и отступления
            nearest_enemy, dist_enemy = self._the_nearest_robot(list_enemy, ball)
            nearest_ally, dist_ally = self._the_nearest_robot(list_ally, ball)

            if attacker1 == nearest_ally:
                op_point = self._optimal_point(attacker2, ball, list_enemy, self.list_optimal_point, aux.dist(ball, attacker2), 0, field)
                if mid is not 0:
                    pos_attacker1 = ball
                    pos_attacker2 = self._optimal_point(attacker2, ball, list_enemy, self.list_optimal_point, 500, mid, field)
                    angle_attacker1 = arg_attacker
                    field.strategy_image.draw_line(ball, pos_attacker2, (255, 0, 255), 3)
                    flag_kick_ball1 = wp.WType.S_BALL_KICK
                    flag_kick_ball2 = wp.WType.S_ENDPOINT
                else:
                    pos_attacker1 = ball
                    pos_attacker2 = op_point
                    # Используем _pas для получения угла паса
                    _, angle_attacker1 = self._pass(ball, attacker1, attacker2)
                    angle_attacker2 = (ball - attacker2).arg()
                    angle_attacker1 = (op_point - ball).arg()
                    flag_kick_ball1 = wp.WType.S_BALL_PASS
                    flag_kick_ball2 = wp.WType.S_ENDPOINT
                    if not self.flag and (ball - attacker1).mag() < 250:
                        self.flag = True
                    if self.flag and field.ball.get_vel().mag() > 100:
                        self.passes_status = FlagToPasses.TRUE_ATTACKER1
                        self.flag = False
            else:
                op_point = self._optimal_point(attacker1, ball, list_enemy, self.list_optimal_point, aux.dist(ball, attacker1), 0, field)
                if mid is not 0:
                    pos_attacker2 = ball
                    pos_attacker1 = self._optimal_point(attacker1, ball, list_enemy, self.list_optimal_point, 500, mid, field)
                    field.strategy_image.draw_line(ball, pos_attacker1, (255, 0, 255), 3)
                    angle_attacker2 = arg_attacker
                    flag_kick_ball2 = wp.WType.S_BALL_KICK
                    flag_kick_ball1 = wp.WType.S_ENDPOINT
                else:
                    pos_attacker2 = ball
                    pos_attacker1 = op_point
                    _, angle_attacker2 = self._pass(ball, attacker2, attacker1)
                    angle_attacker1 = (ball - attacker1).arg()
                    angle_attacker2 = (op_point - ball).arg()
                    flag_kick_ball2 = wp.WType.S_BALL_PASS
                    flag_kick_ball1 = wp.WType.S_ENDPOINT
                    if not self.flag and (ball - attacker2).mag() < 250:
                        self.flag = True
                    if self.flag and field.ball.get_vel().mag() > 100:
                        self.passes_status = FlagToPasses.TRUE_ATTACKER2
                        self.flag = False
        return pos_attacker1, angle_attacker1, flag_kick_ball1, pos_attacker2, angle_attacker2, flag_kick_ball2