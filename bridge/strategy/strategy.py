"""Верхнеуровневый код стратегии"""

# pylint: disable=redefined-outer-name

# @package Strategy
# Расчет требуемых положений роботов исходя из ситуации на поле


import math

# !v DEBUG ONLY
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


class BallStatus_is_inside_poly(Enum):
    Not_inside_poly = 0
    Inside_poly = 1


class Strategy:
    """Основной класс с кодом стратегии"""

    def __init__(
        self,
        dbg_game_status: GameStates = GameStates.RUN,
    ) -> None:
        self.game_status = dbg_game_status
        self.active_team: ActiveTeam = ActiveTeam.ALL

        self.old_ball = aux.Point(0, 0)
        self.ball_status = BallStatus.Passive
        self.ball_status_poly = BallStatus_is_inside_poly.Not_inside_poly
        self.old_pos = aux.Point(0, 0)

        """idx роботов"""
        self.idx_gk = 1
        self.idx1 = 2
        self.idx2 = 0

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
        Рассчитать конечные точки для каждого робота
        """


        waypoints: list[wp.Waypoint] = []
        for i in range(const.TEAM_ROBOTS_MAX_COUNT):
            waypoints.append(
                wp.Waypoint(
                    field.allies[i].get_pos(),
                    field.allies[i].get_angle(),
                    wp.WType.S_STOP,
                )
            )

        global pos
        global pos1
        global pos2


        args = field.enemy_goal.center.arg()
        ball = field.ball.get_pos()
        attacker = field.allies[self.idx1].get_pos()
        attacker1 = field.allies[self.idx2].get_pos()

        ### наши роботы ###
        goalkeeper = field.allies[self.idx_gk].get_pos()

        ### флаг для определения бить или не бить вратарю по мячу ###
        flag_to_kick_goalkeeper = wp.WType.S_IGNOREOBSTACLES

        ### вражеские роботы ###
        enemy_goalkeeper = field.enemies[self.enemy_idx_gk].get_pos()
        enemy_attacker1 = field.enemies[self.enemy_idx1].get_pos()
        enemy_attacker2 = field.enemies[self.enemy_idx2].get_pos()
        list_enemy = [enemy_goalkeeper, enemy_attacker1, enemy_attacker2]

        ################################# goalkeeper ##################################

        ### Определение ближайшего вражеского робота к мячу ###
        if (ball - enemy_attacker1).mag() > (ball - enemy_attacker2).mag():
            attacker = enemy_attacker2
        else:
            attacker = enemy_attacker1
        attacker = field.allies[self.idx2].get_pos()

        ### Вражеский робот готовиться к удару ###

        if (ball - attacker).mag() < 250:
            pos = aux.closest_point_on_line(attacker, ball, goalkeeper, "R")

            ### Пересечение вектора атакующий робот - мяч и линии ворот ###

            cords1 = aux.get_line_intersection(
                attacker,
                ball,
                field.ally_goal.up,
                field.ally_goal.down,
                "LL",
            )

            ### Пересечение линии ворот и параллельной прямой проходящей через мяч ###

            cords2 = aux.get_line_intersection(
                ball,
                aux.Point(ball.x - 1, ball.y),
                field.ally_goal.up,
                field.ally_goal.down,
                "LL",
            )
            ### ближайшая точка к вектору мяч - средняя между прошлыми 2 точками ###
            cords_Sr = aux.average_point([cords1, cords2])
            if cords1 is not None and cords2 is not None:
                ### Берём отрезок полёта мяча внутри воротарской зоны ###
                result = aux.get_line_intersection(
                        ball,
                        cords_Sr,
                        field.ally_goal.frw_up - field.ally_goal.eye_forw * 1,
                        field.ally_goal.center_up,
                        "LS",
                )
                if result is None:
                    result = aux.get_line_intersection(
                            ball,
                            cords_Sr,
                            field.ally_goal.frw_down - field.ally_goal.eye_forw * 1,
                            field.ally_goal.center_down,
                            "LS",
                    )
                if result is None:
                    result = aux.get_line_intersection(
                            ball,
                            cords_Sr,
                            field.ally_goal.frw_up - field.ally_goal.eye_forw * 1,
                            field.ally_goal.frw_down - field.ally_goal.eye_forw * 1,
                            "LL",
                        )
                pos = aux.closest_point_on_line(result, cords_Sr, goalkeeper, "S")
                field.strategy_image.draw_line(result, cords_Sr, (0, 0, 255), 5)
                field.strategy_image.draw_line(pos, attacker, (0, 0, 255), 5)
                if aux.dist(pos, self.prev_pos) > 80:
                    self.pos_holds_timer = time()

                self.prev_pos = pos

                if time() - self.pos_holds_timer < 1:
                    pos = field.ally_goal.center + field.ally_goal.eye_forw * 300

                field.strategy_image.draw_dot(pos, (0, 0, 0), 40)
            
            self.ball_status = BallStatus.Ready

        ### Вражеский робот не у мяча ###

        else:

            ### Координаты мяча по оси х в зоне ворот по х ###

            if ball.x < field.ally_goal.up.x and ball.x > field.ally_goal.down.x:
                pos = aux.closest_point_on_line(
                    ball, aux.Point(ball.x - 1, ball.y), goalkeeper, "L"
                )

            ### Определяем на какой половине наши ворота ###

            if field.ally_goal.center.x > 0:
                argument_side = 1
            else:
                argument_side = -1

            ### Строим биссектрису для мяча, х мяча выше ворот ###

            if ball.x > field.ally_goal.up.x:
                pos = aux.closest_point_on_line(
                    ball, aux.Point(ball.x + argument_side, ball.y - 1), goalkeeper, "L"
                )

            ### Строим биссектрису для мяча, х мяча ниже ворот ###

            else:
                pos = aux.closest_point_on_line(
                    ball, aux.Point(ball.x + argument_side, ball.y + 1), goalkeeper, "L"
                )

        ### Ловим мяч ###

        if self.ball_status == BallStatus.Ready and (ball - attacker).mag() >= 250:
            ### Пересечение вектора полёта мяча и линии ворот ###
            if self.old_ball is not None:
                cords1 = aux.get_line_intersection(
                    self.old_ball,
                    ball,
                    field.ally_goal.up,
                    field.ally_goal.down,
                    "RL",
                )
            else:
                cords1 = None

            ### Пересечение линии ворот и параллельной прямой проходящей через мяч ###

            cords2 = aux.get_line_intersection(
                ball,
                aux.Point(ball.x + 1, ball.y),
                field.ally_goal.up,
                field.ally_goal.down,
                "LL",
            )

            ### ближайшая точка к вектору мяч - средняя между прошлыми 2 точками ###

            if cords1 is not None and cords2 is not None:
                cords_Sr = aux.average_point([cords1, cords2])
                if not aux.is_point_inside_poly(ball, field.ally_goal.hull):
                    result = aux.get_line_intersection(
                            ball,
                            cords_Sr,
                            field.ally_goal.frw_up - field.ally_goal.eye_forw * 1,
                            field.ally_goal.frw_down - field.ally_goal.eye_forw * 1,
                            "LL",
                        )
                else:
                    result = ball
                pos = aux.closest_point_on_line(result, cords_Sr, goalkeeper, "S")
                field.strategy_image.draw_line(result, cords_Sr, (0, 0, 255), 5)
                field.strategy_image.draw_line(pos, attacker, (0, 0, 255), 5)
                field.strategy_image.draw_dot(pos, (0, 0, 0), 40)
            elif cords1 is not None:
                cords_Sr = cords1
                if not aux.is_point_inside_poly(ball, field.ally_goal.hull):
                    result = aux.get_line_intersection(
                            ball,
                            cords_Sr,
                            field.ally_goal.frw_up - field.ally_goal.eye_forw * 1,
                            field.ally_goal.frw_down - field.ally_goal.eye_forw * 1,
                            "LL",
                        )
                else:
                    result = ball
                pos = aux.closest_point_on_line(result, cords_Sr, goalkeeper, "S")
                field.strategy_image.draw_line(result, cords_Sr, (0, 0, 255), 5)
                field.strategy_image.draw_line(pos, attacker, (0, 0, 255), 5)
                field.strategy_image.draw_dot(pos, (0, 0, 0), 40)
            else:
                cords_Sr = cords2
                result = aux.get_line_intersection(
                        ball,
                        cords_Sr,
                        field.ally_goal.frw_up - field.ally_goal.eye_forw * 1,
                        field.ally_goal.frw_down - field.ally_goal.eye_forw * 1,
                        "LL",
                    )
                pos = aux.closest_point_on_line(result, cords_Sr, goalkeeper, "S")
                field.strategy_image.draw_line(result, cords_Sr, (0, 0, 255), 5)
                field.strategy_image.draw_line(pos, attacker, (0, 0, 255), 5)
                field.strategy_image.draw_dot(pos, (0, 0, 0), 40)
            ### проверяем, что мяч в зоне ворот ###

            if aux.is_point_inside_poly(ball, field.ally_goal.hull):
                self.ball_status_poly = (
                    BallStatus_is_inside_poly.Inside_poly
                )  ### выходит из перехвата из за смены статуса ###

        ### Мяч остановился, после удара в зоне ворот ###

        if field.is_ball_stop_near_goal():
            pos = ball
            args = field.enemy_goal.center.arg()
            flag_to_kick_goalkeeper = wp.WType.S_BALL_KICK

        ### Мяч вылетел за зону ворот, после удара ###

        if (
            self.ball_status_poly == BallStatus_is_inside_poly.Inside_poly
            and not aux.is_point_inside_poly(ball, field.ally_goal.hull)
        ):
            self.ball_status_poly = BallStatus_is_inside_poly.Not_inside_poly
            self.ball_status = BallStatus.Passive

            pos = field.ally_goal.center + field.ally_goal.eye_forw * 300
    
        ### Координаты вне зоны ворот ###

        if not aux.is_point_inside_poly(pos, field.ally_goal.hull):
            pos = field.ally_goal.center + field.ally_goal.eye_forw * 300
            args = field.enemy_goal.center.arg()

        self.old_ball = field.ball_start_point
        field.strategy_image.draw_dot(pos, (255, 255, 0), 40)
        ################################### attacker ##########################################

        result_cords = [] ### массив пересечений косательных к вражеским робоотам и вражеских ворот ###

        ### Строим косательные к вражеским роботам, и записываем точки пересечениа вражеских ворот и полученных костальных ###
        for enemy in list_enemy:
            cords_peresch = []
            cords = aux.get_tangent_points(enemy, ball, const.ROBOT_R)
            if len(cords) >= 2:
                for count in range(2):
                    field.strategy_image.draw_dot(cords[0], (255, 0, 0), 40)
                    field.strategy_image.draw_dot(cords[1], (255, 0, 0), 40)
                    result = aux.get_line_intersection(
                        ball,
                        cords[count],
                        field.enemy_goal.center_up,
                        field.enemy_goal.center_down,
                        "RL",
                    )
                    if result is not None:
                        cords_peresch.append(result.y)
                if len(cords_peresch) > 1:
                    result_cords.append(cords_peresch)

        ### Hисуем прямые мяч - точка пересечения ворот и костальных ###

        for cordes in result_cords:
            field.strategy_image.draw_line(
                ball, aux.Point(field.enemy_goal.up.x, cordes[0]), (255, 0, 0), 3
            )
            field.strategy_image.draw_line(
                ball, aux.Point(field.enemy_goal.up.x, cordes[1]), (255, 0, 0), 3
            )
            field.strategy_image.draw_line(
                aux.Point(field.enemy_goal.up.x, cordes[0]), aux.Point(field.enemy_goal.up.x, cordes[1]), (255, 0, 0), 3
            )

        ### Cоритруем координаты пересечений по y ###

        result_cords = sorted(result_cords)
        maximum = 0
        count = 0

        ### Определяем самую первую точку 1###

        right = field.enemy_goal.up.y

        ### Проверем что точка 1 не лежит в отрезке закрывемым вражеским роботом, а если закрыть то меняем самую первую точку 1 ###

        for cords_right in result_cords:
            if (
                field.enemy_goal.up.y <= cords_right[1]
                and field.enemy_goal.up.y >= cords_right[0]
            ):
                right = cords_right[1]
                break

        ### Проходимся по прямым меняя точку 1 и точку 2, и находим максимальный свободный отрезок ###

        mid = 0
        left = None
        arg_atacker = (field.enemy_goal.center - ball).arg()
        while count < len(result_cords) and right < field.enemy_goal.down.y:
            left = result_cords[count][0]
            if left > right:
                if left > field.enemy_goal.down.y:
                    left = field.enemy_goal.down.y
                if maximum < left - right:
                    maximum = left - right
                    mid = aux.Point(field.enemy_goal.up.x, (left + right) // 2)
                    right = result_cords[count][1]
            count += 1

        ### Проверка 2 точки на существвание и чтобы лежала внутри ворот###
        
        if left is None:
            left = field.enemy_goal.down.y
        if left <= field.enemy_goal.down.y:
            left = field.enemy_goal.down.y
            if maximum < left - right:
                maximum = left - right
                mid = aux.Point(field.enemy_goal.up.x, (left + right) // 2)

        ### Проверка что mid посчитан ###
        if mid is not 0: 
            field.strategy_image.draw_dot(mid, (255, 0, 0), 40)
            arg_atacker = (mid - ball).arg()
            flag_to_kick_ball = wp.WType.S_BALL_KICK
        
        #def blok(x, y): 
        #    global pos
        #    global pos1
        #    global pos2
        #    pos =  aux.Point(x, y)
        #    pos1 = aux.Point(x, y + 200)
        #    pos2 = aux.Point(x, y - 200)

        ################################ atacker for test goalkeper ##################################

        ### Определение дальнего угла ворот от вратаря ###

        if (field.ally_goal.center_up - goalkeeper).mag() < (field.ally_goal.center_down - goalkeeper).mag():
            args2 = (
                field.ally_goal.down + field.ally_goal.eye_up * 100 - ball
            ).arg()
        else:
            args2 = (
                field.ally_goal.up - field.ally_goal.eye_up * 100 - ball
            ).arg()

        #################################### defer #######################################
        def the_nearest_robot(lst: list[int], pnt: aux.Point) -> list:
            min_mag = None
            idx = 0
            for i in lst:
                b = pnt - field.allies[i].get_pos()
                if min_mag is None or b.mag() < min_mag:
                    min_mag = b.mag()
                    idx = i

            return [idx, min_mag]

        def defer(robot):
            field.strategy_image.draw_line(
                field.enemy_goal.up, ball, (255, 0, 255), 3
            )
            field.strategy_image.draw_line(
                field.enemy_goal.down, ball, (255, 0, 255), 3
            )
            while(robot - aux.closest_point_on_line(field.enemy_goal.down, ball, robot, "S") > 50 and
                   robot - aux.closest_point_on_line(field.enemy_goal.up, ball, robot, "S") > 50):
                pass

            
        ################################## Waypoints ##########################################

        # waypoints[self.idx1] = wp.Waypoint(
        #    ball,
        #    arg_atacker,
        #    wp.WType.S_BALL_KICK
        # )

        waypoints[self.idx_gk] = wp.Waypoint(
           pos,
           args,
           flag_to_kick_goalkeeper,
        )

        waypoints[self.idx2] = wp.Waypoint(
          ball,
          args2,
          wp.WType.S_BALL_KICK,
        )

        return waypoints