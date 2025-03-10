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


class Strategy:
    """Основной класс с кодом стратегии.

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

        # Индексы наших роботов
        self.idx_gk = 2
        self.idx1 = 0
        self.idx2 = 1

        # Индексы вражеских роботов
        self.enemy_idx_gk = 2
        self.enemy_idx1 = 0
        self.enemy_idx2 = 1

        self.pos_holds_timer = 0
        self.prev_pos = aux.Point(0, 0)

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

        # ::NOTE:: думаю уже пора как-то обобщить эту логику, чтобы не прописывать id своих роботов и роботов соперника руками.
        # Что-то вроде такого:
        # list_ally = []
        # for robot, idx in field.allies:
        #     if robot.is_used():
        #         list_ally.append(robot)

        # Получаем позиции наших роботов
        attacker1 = field.allies[self.idx1].get_pos()
        attacker2 = field.allies[self.idx2].get_pos()
        goalkeeper = field.allies[self.idx_gk].get_pos()
        list_ally = [goalkeeper, attacker1, attacker2]

        # Получаем позиции вражеских роботов
        enemy_goalkeeper = field.enemies[self.enemy_idx_gk].get_pos()
        enemy_attacker1 = field.enemies[self.enemy_idx1].get_pos()
        enemy_attacker2 = field.enemies[self.enemy_idx2].get_pos()
        list_enemy = [enemy_goalkeeper, enemy_attacker1, enemy_attacker2]

        # Первоначальное значение направления
        enemy_goal_arg = field.enemy_goal.center.arg()

        # Вызываем вспомогательный метод для расчёта позиции вратаря
        # Здесь логика определения "attacker" внутри метода не меняется, хоть в оригинале оно переопределялось
        # Передаём позицию для нападающего из наших (idx2) как attacker.
        attacker = field.allies[self.idx2].get_pos()
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
            goalkeeper,
            enemy_attacker1,
            enemy_attacker2,
        )

        # ::NOTE:: аналогично ъ
        # Заполняем массив waypoint’ов для роботов
        waypoints[self.idx_gk] = wp.Waypoint(pos_gk, angle_gk, flag_kick_gk)
        waypoints[self.idx1] = wp.Waypoint(pos_attacker1, angle_attacker1, flag_kick_ball1)
        waypoints[self.idx2] = wp.Waypoint(pos_attacker2, angle_attacker2, flag_kick_ball2)

        self.old_ball = field.ball_start_point or aux.Point(0, 0)
        print(self.old_ball, ball)
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
        self, ball: aux.Point, enemy_list: list[aux.Point], candidate_points: list[aux.Point]
    ) -> aux.Point:
        """
        Находит оптимальную точку для паса, сравнивая расстояния.
        """
        maxim = 0
        res = aux.Point(0, 0)
        for enemy in enemy_list:
            for cand in candidate_points:
                diff = (enemy - cand).mag() - (enemy - aux.closest_point_on_line(ball, cand, enemy, "S")).mag()
                if ((diff > maxim and cand.y < 0) or (maxim == 0 and diff > maxim and cand.y > 0)):
                    maxim = diff
                    res = cand
        return res

    def _defer(self, robot: aux.Point, ball: aux.Point, field: fld.Field) -> aux.Point:
        """
        Вычисляет позицию для защиты ворот с отступлением.
        Отрисовка линий оставлена для визуальной отладки.
        """

        # ::NOTE:: этот блок кода очень страшно выглядит и не читается
        # опять же, стоит попробовать обобщить его, как и многое другое.
        # Старайся писать код, которые корректно работает с любым разумным количеством роботов(хоть с 1, хоть с 50)
        field.strategy_image.draw_line(ball, field.ally_goal.down, (255, 0, 255), 3)
        field.strategy_image.draw_line(ball, field.ally_goal.up, (255, 0, 255), 3)
        line_down = aux.closest_point_on_line(ball, field.ally_goal.down, robot, "S")
        offset_down = (aux.rotate(field.ally_goal.down - ball, math.pi / 2)).unity() * const.ROBOT_R
        field.strategy_image.draw_line(ball, line_down + offset_down, (255, 255, 255), 5)
        line_up = aux.closest_point_on_line(ball, field.ally_goal.up, robot, "S")
        offset_up = (aux.rotate(field.ally_goal.up - ball, math.pi / 2)).unity() * const.ROBOT_R
        field.strategy_image.draw_line(ball, line_up - offset_up, (255, 0, 255), 3)
        down_dist = (line_down + offset_down - robot).mag()
        up_dist = (line_up - offset_up - robot).mag()

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
            cords2 = aux.get_line_intersection(ball, aux.Point(ball.x - 1, ball.y), field.ally_goal.up, field.ally_goal.down, "LL")
            if cords1 is not None and cords2 is not None:
                cords_sr = aux.average_point([cords1, cords2])
                result = aux.get_line_intersection(
                    ball,
                    cords_sr,
                    field.ally_goal.frw_up - field.ally_goal.eye_forw,
                    field.ally_goal.center_up,
                    "LS",
                )
                if result is None:
                    result = aux.get_line_intersection(
                        ball,
                        cords_sr,
                        field.ally_goal.frw_down - field.ally_goal.eye_forw,
                        field.ally_goal.center_down,
                        "LS",
                    )
                if result is None:
                    result = aux.get_line_intersection(
                        ball,
                        cords_sr,
                        field.ally_goal.frw_up - field.ally_goal.eye_forw,
                        field.ally_goal.frw_down - field.ally_goal.eye_forw,
                        "LL",
                    )
                pos = aux.closest_point_on_line(result, cords_sr, goalkeeper, "S")
                field.strategy_image.draw_line(result, cords_sr, (0, 0, 255), 5)
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
            if field.ally_goal.up.x > ball.x > field.ally_goal.down.x:
                pos = aux.closest_point_on_line(ball, aux.Point(ball.x - 1, ball.y), goalkeeper, "L")
            else:
                pos = None  # Инициализация
            argument_side = 1 if field.ally_goal.center.x > 0 else -1
            if ball.x > field.ally_goal.up.x:
                pos = aux.closest_point_on_line(ball, aux.Point(ball.x + argument_side, ball.y - 1), goalkeeper, "L")
            else:
                pos = aux.closest_point_on_line(ball, aux.Point(ball.x + argument_side, ball.y + 1), goalkeeper, "L")

        # Если вратарь готов (мяч ранее отмечен как Ready) и противник далеко
        if self.ball_status == BallStatus.Ready and (ball - attacker).mag() >= 250:
            cords1 = (
                aux.get_line_intersection(self.old_ball, ball, field.ally_goal.up, field.ally_goal.down, "RL")
                if self.old_ball is not None
                else None
            )
            cords2 = aux.get_line_intersection(ball, aux.Point(ball.x + 1, ball.y), field.ally_goal.up, field.ally_goal.down, "LL")
            if cords1 is not None and cords2 is not None:
                cords_sr = aux.average_point([cords1, cords2])
                if not aux.is_point_inside_poly(ball, field.ally_goal.hull):
                    result = aux.get_line_intersection(
                        ball,
                        cords_sr,
                        field.ally_goal.frw_up - field.ally_goal.eye_forw,
                        field.ally_goal.frw_down - field.ally_goal.eye_forw,
                        "LL",
                    )
                else:
                    result = ball
                pos = aux.closest_point_on_line(result, cords_sr, goalkeeper, "S")
                field.strategy_image.draw_line(result, cords_sr, (0, 0, 255), 5)
                field.strategy_image.draw_line(pos, attacker, (0, 0, 255), 5)
                field.strategy_image.draw_dot(pos, (0, 0, 0), 40)
            elif cords1 is not None:
                cords_sr = cords1
                if not aux.is_point_inside_poly(ball, field.ally_goal.hull):
                    result = aux.get_line_intersection(
                        ball,
                        cords_sr,
                        field.ally_goal.frw_up - field.ally_goal.eye_forw,
                        field.ally_goal.frw_down - field.ally_goal.eye_forw,
                        "LL",
                    )
                else:
                    result = ball
                pos = aux.closest_point_on_line(result, cords_sr, goalkeeper, "S")
                field.strategy_image.draw_line(result, cords_sr, (0, 0, 255), 5)
                field.strategy_image.draw_line(pos, attacker, (0, 0, 255), 5)
                field.strategy_image.draw_dot(pos, (0, 0, 0), 40)
            elif cords2 is not None:
                cords_sr = cords2  # ::NOTE:: cords2 can be None
                result = aux.get_line_intersection(
                    ball,
                    cords_sr,
                    field.ally_goal.frw_up - field.ally_goal.eye_forw,
                    field.ally_goal.frw_down - field.ally_goal.eye_forw,
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
            pos = field.ally_goal.center + field.ally_goal.eye_forw * 300
            angle = field.enemy_goal.center.arg()
        else:
            angle = field.enemy_goal.center.arg()

        return pos, angle, flag_to_kick_goalkeeper

    def _process_attackers(
        self,
        field: fld.Field,
        ball: aux.Point,
        list_ally: list[aux.Point],
        list_enemy: list[aux.Point],
        attacker1: aux.Point,
        attacker2: aux.Point,
        goalkeeper: aux.Point,
        enemy_attacker1: aux.Point,
        enemy_attacker2: aux.Point,
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
                if len(cords_peresch) > 1:
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
        if const.POLARITY == 1:
            field_up = field.enemy_goal.up
            field_down = field.enemy_goal.down
        else:
            field_down = field.enemy_goal.up
            field_up = field.enemy_goal.down

        mid = 0
        left = result_cords[0][0] if result_cords else None
        right = field_up.y
        count = 0
        while count < len(result_cords):
            if left is not None and (left > right and right > field_up.y and left < field_down.y):
                break
            if result_cords[count][1] < field_down.y:
                right = max(result_cords[count][1], right)
            count += 1
            left = field_down.y if count == len(result_cords) else result_cords[count][0]
        if count != 0:
            count -= 1
        arg_attacker = (field.enemy_goal.center - ball).arg()
        while count < len(result_cords) and right < field_down.y:
            if left > right:
                if left > field_down.y:
                    left = field_down.y
                if left - right > maximum and left - right > 50:
                    maximum = left - right
                    mid = aux.Point(field_up.x, (left + right) // 2)
            right = result_cords[count][1]
            count += 1
        if left is None:
            left = field_down.y
        if left <= field_down.y:
            left = field_down.y
            if left - right > maximum:
                maximum = left - right
                mid = aux.Point(field_up.x, (left + right) // 2)
        if mid != 0:
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
            pos_attacker1 = attacker1
            angle_attacker1 = attacker1.arg()
            pos_attacker2, _ = self._pass(ball, attacker1, attacker2)
            angle_attacker2 = (ball - attacker2).arg()
            field.allies[self.idx2].set_dribbler_speed(15)
            if (attacker2 - ball).mag() < 100 or not field.is_ball_moves():
                self.passes_status = FlagToPasses.FALSE
        elif self.passes_status == FlagToPasses.TRUE_ATTACKER2:
            pos_attacker2 = attacker2
            angle_attacker2 = attacker2.arg()
            pos_attacker1, _ = self._pass(ball, attacker2, attacker1)
            angle_attacker1 = (ball - attacker1).arg()
            field.allies[self.idx1].set_dribbler_speed(15)
            if (attacker1 - ball).mag() < 100 or not field.is_ball_moves():
                self.passes_status = FlagToPasses.FALSE
        else:
            # Если враг ближе к мячу, выбираем стратегию блокирования и отступления
            nearest_enemy, dist_enemy = self._the_nearest_robot(list_enemy, ball)
            nearest_ally, dist_ally = self._the_nearest_robot(list_ally, ball)
            if dist_enemy < dist_ally:
                circle_point = self._circle_to_two_tangents(const.ROBOT_R, ball, field.ally_goal.down, field.ally_goal.up)
                if (attacker1 - circle_point).mag() < (attacker2 - circle_point).mag():
                    if ((enemy_attacker2 - ball).mag() - dist_enemy) < 10:
                        pos_attacker2 = self._block_robot_to_ball(ball, field.enemies[self.enemy_idx1].get_pos(), attacker2)
                    else:
                        pos_attacker2 = self._block_robot_to_ball(ball, field.enemies[self.enemy_idx2].get_pos(), attacker2)
                    pos_attacker1 = self._defer(attacker1, ball, field)
                else:
                    pos_attacker2 = self._defer(attacker2, ball, field)
                    if ((enemy_attacker2 - ball).mag() - dist_enemy) < 10:
                        pos_attacker1 = self._block_robot_to_ball(ball, field.enemies[self.enemy_idx1].get_pos(), attacker1)
                    else:
                        pos_attacker1 = self._block_robot_to_ball(ball, field.enemies[self.enemy_idx2].get_pos(), attacker1)
                flag_kick_ball1 = wp.WType.S_ENDPOINT
                flag_kick_ball2 = wp.WType.S_ENDPOINT
            else:
                if attacker1 == nearest_ally:
                    if mid != 0 and ball.x < 0:
                        pos_attacker1 = ball
                        pos_attacker2 = self._defer(attacker2, ball, field)
                        angle_attacker1 = arg_attacker
                        field.strategy_image.draw_line(ball, pos_attacker2, (255, 0, 255), 3)
                        flag_kick_ball1 = wp.WType.S_BALL_KICK
                        flag_kick_ball2 = wp.WType.S_ENDPOINT
                    else:
                        pos_attacker1 = ball
                        pos_attacker2 = self._optimal_point(ball, list_enemy, [aux.Point(-1000, 1000), aux.Point(-1000, -1000)])
                        # Используем _pas для получения угла паса
                        _, angle_attacker1 = self._pass(ball, attacker1, attacker2)
                        angle_attacker2 = (ball - attacker2).arg()
                        flag_kick_ball1 = wp.WType.S_BALL_PASS
                        flag_kick_ball2 = wp.WType.S_ENDPOINT
                        if not self.flag and (ball - attacker1).mag() < 250:
                            self.flag = True
                        if self.flag and field.is_ball_moves():
                            self.passes_status = FlagToPasses.TRUE_ATTACKER1
                            self.flag = False
                else:
                    if mid != 0 and ball.x < 0:
                        pos_attacker2 = ball
                        pos_attacker1 = self._defer(attacker1, ball, field)
                        field.strategy_image.draw_line(ball, pos_attacker1, (255, 0, 255), 3)
                        angle_attacker2 = arg_attacker
                        flag_kick_ball2 = wp.WType.S_BALL_KICK
                        flag_kick_ball1 = wp.WType.S_ENDPOINT
                    else:
                        pos_attacker2 = ball
                        pos_attacker1 = self._optimal_point(ball, list_enemy, [aux.Point(-1000, 1000), aux.Point(-1000, -1000)])
                        _, angle_attacker2 = self._pass(ball, attacker2, attacker1)
                        angle_attacker1 = (ball - attacker1).arg()
                        flag_kick_ball2 = wp.WType.S_BALL_PASS
                        flag_kick_ball1 = wp.WType.S_ENDPOINT
                        if not self.flag and (ball - attacker2).mag() < 250:
                            self.flag = True
                        if self.flag and field.is_ball_moves():
                            self.passes_status = FlagToPasses.TRUE_ATTACKER2
                            self.flag = False
        return pos_attacker1, angle_attacker1, flag_kick_ball1, pos_attacker2, angle_attacker2, flag_kick_ball2
