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

        """idx роботов"""
        self.idx_gk = 1
        self.idx1 = 0
        self.idx2 = 2

        self.enemy_idx_gk = 0
        self.enemy_idx1 = 1
        self.enemy_idx2 = 2

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

        
        waypoints[self.idx1] = wp.Waypoint(
            field.ball.get_pos(),
            0,
            wp.WType.S_BALL_KICK
        )

        return waypoints

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
        # if (ball - enemy_attacker1).mag() > (ball - enemy_attacker2).mag():
        #    attacker = enemy_attacker2
        #    idx_attacker = self.enemy_idx2
        # else:
        #    attacker = enemy_attacker1
        #    idx_attacker = self.enemy_idx1
        attacker = field.allies[self.enemy_idx1].get_pos()
        idx_attacker = self.enemy_idx1

        ### Вражеский робот готовиться к удару ###

        if (ball - attacker).mag() < 150:
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

            if cords1 is not None and cords2 is not None:
                cords_Sr = aux.average_point([cords1, cords2])
                pos = aux.closest_point_on_line(ball, cords_Sr, goalkeeper, "L")
            field.strategy_image.draw_dot(pos, (0, 0, 255), 200)
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

        if self.ball_status == BallStatus.Ready and (ball - attacker).mag() >= 150:

            ### Пересечение вектора полёта мяча и линии ворот ###

            cords1 = aux.get_line_intersection(
                self.old_ball,
                ball,
                field.ally_goal.up,
                field.ally_goal.down,
                "LL",
            )

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
                pos = aux.closest_point_on_line(ball, cords_Sr, goalkeeper, "L")
            else:
                pos = aux.closest_point_on_line(self.old_ball, ball, goalkeeper, "L")
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
            field.strategy_image.draw_dot(pos, (255, 0, 0), 200)

        self.old_ball = ball
        ################################### attacker ##########################################
        result_cords = []
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

        for cordes in result_cords:
            field.strategy_image.draw_line(
                ball, aux.Point(-4500, cordes[0]), (255, 0, 0), 3
            )
            field.strategy_image.draw_line(
                ball, aux.Point(-4500, cordes[1]), (255, 0, 0), 3
            )
            field.strategy_image.draw_line(
                aux.Point(-4500, cordes[0]), aux.Point(-4500, cordes[1]), (255, 0, 0), 3
            )

        result_cords = sorted(result_cords)
        if result_cords == []:
            result_cords = [[0, 0]]
        maximum = 0
        count = 0
        right = field.enemy_goal.up.y
        for cords_right in result_cords:
            if (
                field.enemy_goal.up.y > cords_right[0]
                and field.enemy_goal.up.y < cords_right[1]
            ):
                right = cords_right[1]
                break
        mid = 0
        while count < len(result_cords) and right < field.enemy_goal.down.y:
            left = result_cords[count][0]
            if left > right:
                if left > field.enemy_goal.down.y:
                    left = field.enemy_goal.down.y
                if maximum < left - right:
                    maximum = left - right
                    mid = aux.Point(-4500, (left + right) // 2)
                    field.strategy_image.draw_dot(mid, (255, 0, 0), 40)
                    right = result_cords[count][1]
            count += 1
        if mid is not 0: 
            arg_atacker = (mid - ball).arg()
            flag_to_kick_ball = wp.WType.S_BALL_KICK
        
        #def blok(x, y): 
        #    global pos
        #    global pos1
        #    global pos2
        #   pos =  aux.Point(x, y)
        #    pos1 = aux.Point(x, y + 200)
        #    pos2 = aux.Point(x, y - 200)
 
        #blok(500,500)
        ################################## Waypoints ##########################################

        waypoints[self.idx1] = wp.Waypoint(
            ball,
            arg_atacker,
            wp.WType.S_BALL_KICK
        )

        #waypoints[self.idx_gk] = wp.Waypoint(
        #   pos,
        #   args,
        #   flag_to_kick_goalkeeper,
        #)

        #waypoints[self.idx2] = wp.Waypoint(
        #   pos2,
        #   args,
        #   flag_to_kick_goalkeeper,
        #)

        return waypoints