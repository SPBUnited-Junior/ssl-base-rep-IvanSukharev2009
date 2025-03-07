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

class flag_to_passes(Enum):
    false = 0
    true_attacker1 = 1
    true_attacker2 = 2


class Strategy:
    """Основной класс с кодом стратегии"""

    def __init__(
        self,
        dbg_game_status: GameStates = GameStates.RUN,
    ) -> None:
        self.game_status = dbg_game_status
        self.active_team: ActiveTeam = ActiveTeam.ALL

        self.old_ball = aux.Point(0, 0)
        self.flag = False
        self.ball_status = BallStatus.Passive
        self.ball_status_poly = BallStatus_is_inside_poly.Not_inside_poly
        self.passes_status = flag_to_passes.false
        self.old_pos = aux.Point(0, 0)

        """ idx роботов """
        self.idx_gk = 1
        self.idx1 = 0
        self.idx2 = 2

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
        start = 0
        if start == 0:
            start = 1
            arg_atacker1 = 0
            arg_atacker2 = 0

        args = field.enemy_goal.center.arg()
        ball = field.ball.get_pos()

        """ наши роботы """
        attacker1 = field.allies[self.idx1].get_pos()
        attacker2 = field.allies[self.idx2].get_pos()
        goalkeeper = field.allies[self.idx_gk].get_pos()
        list_ally = [goalkeeper, attacker1, attacker2]

        """ флаг для определения бить или не бить вратарю по мячу """
        flag_to_kick_goalkeeper = wp.WType.S_IGNOREOBSTACLES

        """ вражеские роботы """
        enemy_goalkeeper = field.enemies[self.enemy_idx_gk].get_pos()
        enemy_attacker1 = field.enemies[self.enemy_idx1].get_pos()
        enemy_attacker2 = field.enemies[self.enemy_idx2].get_pos()
        list_enemy = [enemy_goalkeeper, enemy_attacker1, enemy_attacker2]

        ############################ Passes #############################
        def passes(ball: aux.Point, robot1: aux.Point, old_ball: aux.Point) -> list:
            arg_pass = (robot1 - ball).arg()
            return aux.closest_point_on_line(old_ball, ball, robot1, "R")
        def pas(ball: aux.Point, robot1: aux.Point, robot2: aux.Point) -> list:

            lt = [aux.Point(robot2.x + 400, robot2.y + 400),
                    aux.Point(robot2.x + 400, robot2.y - 400),
                    aux.Point(robot2.x - 400, robot2.y - 400),
                    aux.Point(robot2.x - 400, robot2.y + 400)
            ]
            
            if aux.is_point_inside_poly(passes(ball, robot2, self.old_ball), lt):
                pos_f = passes(ball, robot2, self.old_ball)
            else:
                pos_f = robot2

            return [pos_f, (robot2 - ball).arg()]

        ############################ goalkeeper ##################################

        """ Определение ближайшего вражеского робота к мячу """
        if (ball - enemy_attacker1).mag() > (ball - enemy_attacker2).mag():
            attacker = enemy_attacker2
        else:
            attacker = enemy_attacker1
        attacker = field.allies[self.idx2].get_pos()

        """ Вражеский робот готовиться к удару """

        if (ball - attacker).mag() < 250:
            pos = aux.closest_point_on_line(attacker, ball, goalkeeper, "R")

            """ Пересечение вектора атакующий робот - мяч и линии ворот """

            cords1 = aux.get_line_intersection(
                attacker,
                ball,
                field.ally_goal.up,
                field.ally_goal.down,
                "LL",
            )

            """ Пересечение линии ворот и параллельной прямой проходящей через мяч """

            cords2 = aux.get_line_intersection(
                ball,
                aux.Point(ball.x - 1, ball.y),
                field.ally_goal.up,
                field.ally_goal.down,
                "LL",
            )
            """ ближайшая точка к вектору мяч - средняя между прошлыми 2 точками """
            cords_Sr = aux.average_point([cords1, cords2])
            if cords1 is not None and cords2 is not None:
                """ Берём отрезок полёта мяча внутри воротарской зоны """
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

            

        else:
            """ Вражеский робот не у мяча """
            """ Координаты мяча по оси х в зоне ворот по х """
            if ball.x < field.ally_goal.up.x and ball.x > field.ally_goal.down.x:
                pos = aux.closest_point_on_line(
                    ball, aux.Point(ball.x - 1, ball.y), goalkeeper, "L"
                )

            """ Определяем на какой половине наши ворота """

            if field.ally_goal.center.x > 0:
                argument_side = 1
            else:
                argument_side = -1

            """ Строим биссектрису для мяча, х мяча выше ворот """

            if ball.x > field.ally_goal.up.x:
                pos = aux.closest_point_on_line(
                    ball, aux.Point(ball.x + argument_side, ball.y - 1), goalkeeper, "L"
                )

                """ Строим биссектрису для мяча, х мяча ниже ворот """

            else:
                pos = aux.closest_point_on_line(
                    ball, aux.Point(ball.x + argument_side, ball.y + 1), goalkeeper, "L"
                )

        """ Ловим мяч """

        if self.ball_status == BallStatus.Ready and (ball - attacker).mag() >= 250:
            """  Пересечение вектора полёта мяча и линии ворот """
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

            """ Пересечение линии ворот и параллельной прямой проходящей через мяч """

            cords2 = aux.get_line_intersection(
                ball,
                aux.Point(ball.x + 1, ball.y),
                field.ally_goal.up,
                field.ally_goal.down,
                "LL",
            )

            """ ближайшая точка к вектору мяч - средняя между прошлыми 2 точками """
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

            """ проверяем, что мяч в зоне ворот """
            if aux.is_point_inside_poly(ball, field.ally_goal.hull):
                """ выходит из перехвата из за смены статуса """
                self.ball_status_poly = (
                    BallStatus_is_inside_poly.Inside_poly
                )  
                

        """ Мяч остановился, после удара в зоне ворот """

        if field.is_ball_stop_near_goal():
            data_package = pas(goalkeeper, attacker1)
            pos_attacker1 = data_package[1]

            args = data_package[0]
            flag_to_kick_goalkeeper = wp.WType.S_BALL_KICK

        """ Мяч вылетел за зону ворот, после удара """

        if (
            self.ball_status_poly == BallStatus_is_inside_poly.Inside_poly
            and not aux.is_point_inside_poly(ball, field.ally_goal.hull)
        ):
            self.ball_status_poly = BallStatus_is_inside_poly.Not_inside_poly
            self.ball_status = BallStatus.Passive

            pos = field.ally_goal.center + field.ally_goal.eye_forw * 300
    
        """ Координаты вне зоны ворот """

        if not aux.is_point_inside_poly(pos, field.ally_goal.hull):
            pos = field.ally_goal.center + field.ally_goal.eye_forw * 300
            args = field.enemy_goal.center.arg()

        field.strategy_image.draw_dot(pos, (255, 255, 0), 40)
        ################################# attacker ##################################

        result_cords = [] ### массив пересечений косательных к вражеским робоотам и вражеских ворот 

        """ Строим косательные к вражеским роботам, и записываем точки пересечениа вражеских ворот и полученных костальных """
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
                    result_cords.append(sorted(cords_peresch))

        """ Hисуем прямые мяч - точка пересечения ворот и костальных """

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

        """ Cоритруем координаты пересечений по y """

        result_cords = sorted(result_cords)
        maximum = 0
        
        """ Определем координаты взависимости оот полярности """

        if const.POLARITY == 1:
            field_up = field.enemy_goal.up
            field_down = field.enemy_goal.down
        else:
            field_down = field.enemy_goal.up
            field_up = field.enemy_goal.down

        mid = 0
        left = None
        count = 0
        if count < len(result_cords):
            left = result_cords[count][0]
        right = field_up.y
        
        """ Определяем певый отрезок в воротах """
        while(count < len(result_cords) ):
            if (left > right and right > field_up.y and left < field_down.y):
                break
            if result_cords[count][1] < field_down.y:
                right = max(result_cords[count][1], right)
            count += 1
            if count == len(result_cords):
                left = field_down.y
            else:
                left = result_cords[count][0]

        if count != 0:
            count -= 1

        """ Перебираем свободные отрезки лежащие подрят """
        arg_atacker = (field.enemy_goal.center - ball).arg()
        while count < len(result_cords) and right < field_down.y:
            if left > right:
                if left > field_down.y:
                    left = field_down.y
                if maximum < left - right and left - right > 50:
                    maximum = left - right
                    mid = aux.Point(field_up.x, (left + right) // 2)
            right = result_cords[count][1]
            count += 1

        """ Проверка точки на существвание и чтобы лежала внутри ворот """
        if left is None:
            left = field_down.y
        if left <= field_down.y:
            left = field_down.y
            if maximum < left - right:
                maximum = left - right
                mid = aux.Point(field_up.x, (left + right) // 2)

        """ Проверка что mid посчитан """
        if mid is not 0: 
            field.strategy_image.draw_dot(mid, (255, 0, 0), 40)
            arg_atacker = (mid - ball).arg()

        ############################### defer #################################

        """ строим окружность между двух косательных """ 
        def Circle_to_two_tangents(radius: float, point:aux.Point, point_1: aux.Point, point_2: aux.Point) -> aux.Point:
            if point_1.y > point_2.y:
                lower_point = point_2
                top_point = point_1
            else:
                lower_point = point_1
                top_point = point_2
            angle = aux.get_angle_between_points(point, top_point, lower_point) / 2
            center = lower_point - point
            center = center.unity() * (radius / abs(math.sin(angle)))
            center = aux.rotate(center, -angle)
            return center + ball

        """ ближайшая точка среди точек к точке """
        def the_nearest_robot(lst: list[aux.Point], pnt: aux.Point) -> list:
            min_mag = None
            robot = 0
            for i in lst:
                b = pnt - i
                if min_mag is None or b.mag() < min_mag:
                    min_mag = b.mag()
                    robot = i
            return [robot, min_mag]

        """ блокировать робота """ 
        def block_robot_to_ball(ball:aux.Point, enemy_robot:aux.Point, robot:aux.Point) -> aux.Point:
            return aux.closest_point_on_line(ball, enemy_robot, robot, "S")

        list_point_passes = [aux.Point(-1000, 1000), 
        aux.Point(-1000, -1000),]

        def optimal_point(ball: aux.Point, lst: list[aux.Point], pnts: list[aux.Point]):
            maxim = 0
            res = aux.Point(0, 0)
            for i in lst:
                for j in pnts:
                    if ((i - j).mag() - (i - aux.closest_point_on_line(ball, j, i, "S")).mag() > maxim and j.y < 0) or (maxim == 0 and (i - j).mag() - (i - aux.closest_point_on_line(ball, j, i, "S")).mag() > maxim and j.y > 0):
                        maxim = (i - j).mag() - (i - aux.closest_point_on_line(ball, j, i, "S")).mag()
                        res = j
            return res

        """ защита ворот, с помощью деления зоны пополам """
        def defer(robot:aux.Point) -> aux.Point:
            field.strategy_image.draw_line(
               ball, field.ally_goal.down, (255, 0, 255), 3
            )  

            field.strategy_image.draw_line(
               ball, field.ally_goal.up, (255, 0, 255), 3
            )  

            field.strategy_image.draw_line(
                ball, aux.closest_point_on_line(ball, field.ally_goal.down, robot, "S") + ((aux.rotate(field.ally_goal.down - ball, math.pi / 2)).unity()) * const.ROBOT_R, (255, 255, 255), 5
            )           

            field.strategy_image.draw_line(
                ball, aux.closest_point_on_line(ball, field.ally_goal.up, robot, "S") - ((aux.rotate(field.ally_goal.up - ball, math.pi / 2)).unity()) * const.ROBOT_R, (255, 0, 255), 3
            ) 

            down = (aux.closest_point_on_line(ball, field.ally_goal.down, robot, "S") + ((aux.rotate(field.ally_goal.down - ball, math.pi / 2)).unity()) * const.ROBOT_R - robot).mag()
            up = (aux.closest_point_on_line(ball, field.ally_goal.up, robot, "S") - ((aux.rotate(field.ally_goal.up - ball, math.pi / 2)).unity()) * const.ROBOT_R - robot).mag()
            
            if down < up:
                ans = aux.closest_point_on_line(ball, field.ally_goal.down, robot, "S") + ((aux.rotate(field.ally_goal.down - ball, math.pi / 2)).unity()) * const.ROBOT_R
                if ((ans - robot).mag() > 40  or aux.is_point_inside_poly(robot, [ball, field.ally_goal.up, field.ally_goal.down]) is False) and aux.is_point_inside_poly(ans, [ball, field.ally_goal.up, field.ally_goal.down]) is True:
                    return ans
                else:
                    return Circle_to_two_tangents(const.ROBOT_R, ball, field.ally_goal.down, field.ally_goal.up)
            else:
                ans = aux.closest_point_on_line(ball, field.ally_goal.up, robot, "S") - ((aux.rotate(field.ally_goal.up - ball, math.pi / 2)).unity()) * const.ROBOT_R
                if ((ans - robot).mag() > 40 or aux.is_point_inside_poly(robot, [ball, field.ally_goal.up, field.ally_goal.down]) is False) and aux.is_point_inside_poly(ans, [ball, field.ally_goal.up, field.ally_goal.down]) is True:
                    return ans
                else:
                    return Circle_to_two_tangents(const.ROBOT_R, ball, field.ally_goal.down, field.ally_goal.up)

        if self.passes_status == flag_to_passes.true_attacker1:
            """ 2 робот принемает пас от 1 """
            pos_attacker1 = attacker1
            data_package = pas(ball, attacker1, attacker2)
            pos_attacker2 = data_package[0]
            arg_atacker2 = (ball - attacker2).arg()
            flag_to_kick_ball1 = wp.WType.S_IGNOREOBSTACLES
            flag_to_kick_ball2 = wp.WType.S_IGNOREOBSTACLES

            if (attacker2 - ball).mag() < 100 or not field.is_ball_moves():
                self.passes_status = flag_to_passes.false
        elif self.passes_status == flag_to_passes.true_attacker2:
            """ 1 робот принемает пас от 2 """
            pos_attacker2 = attacker2
            data_package = pas(ball, attacker2, attacker1)
            pos_attacker1 = data_package[0]
            arg_atacker1 = (ball - attacker1).arg()
            flag_to_kick_ball1 = wp.WType.S_IGNOREOBSTACLES
            flag_to_kick_ball2 = wp.WType.S_IGNOREOBSTACLES

            if (attacker1 - ball).mag() < 100 or not field.is_ball_moves():
                self.passes_status = flag_to_passes.false
        else:
            """Определяем чей робот ближе, наш или вражеский"""
            if the_nearest_robot(list_enemy, ball)[1] < the_nearest_robot(list_ally, ball)[1]: 
                """
                Определяем какой из наших роботов ближе к мячу и   
                    1) защита ворот
                    2) блокируем второго робота врага
                """
                if (attacker1 - Circle_to_two_tangents(const.ROBOT_R, ball, field.ally_goal.down, field.ally_goal.up)).mag() < (attacker2 - Circle_to_two_tangents(const.ROBOT_R, ball, field.ally_goal.down, field.ally_goal.up)).mag(): 
                    if ((enemy_attacker2 - ball).mag() - the_nearest_robot(list_enemy, ball)[1]) < 10:            
                        pos_attacker2 = block_robot_to_ball(ball, enemy_attacker1, attacker2)            
                    else:                                                                               
                        pos_attacker2 = block_robot_to_ball(ball, enemy_attacker2, attacker2)
                                    
                    pos_attacker1 = defer(attacker1) 
                else:
                    pos_attacker2 = defer(attacker2)
                    if ((enemy_attacker2 - ball).mag() - the_nearest_robot(list_enemy, ball)[1]) < 10:                                                                                
                        pos_attacker1 = block_robot_to_ball(ball, enemy_attacker1, attacker1)                                          
                    else:
                        pos_attacker1 = block_robot_to_ball(ball, enemy_attacker2, attacker1)
                flag_to_kick_ball2 = wp.WType.S_IGNOREOBSTACLES
                flag_to_kick_ball1 = wp.WType.S_IGNOREOBSTACLES
            else:
                """
                Определяем какой робот из наших ближе к мячу
                    1) Отправляеи его бить мяч в ворота или давать пас(нету паса)
                    2) В зависимости от ситуации 
                        a) даём пас 
                        б) бьём по воротам
                """
                if attacker1 == the_nearest_robot(list_ally, ball)[0]:      
                    if mid is not 0 and ball.x < 0:
                        """ удар в ворота """
                        pos_attacker1 = ball                                      
                        pos_attacker2 = defer(attacker2)                           
                        arg_atacker1 = arg_atacker                                  
                        field.strategy_image.draw_line(
                            ball, pos_attacker2, (255, 0, 255), 3
                        ) 
                        flag_to_kick_ball1 = wp.WType.S_BALL_KICK
                        flag_to_kick_ball2 = wp.WType.S_IGNOREOBSTACLES
                    else:
                        """ пас """
                        data_package = pas(ball, attacker1, attacker2)
                        pos_attacker1 = ball 
                        pos_attacker2 = optimal_point(ball, list_enemy, list_point_passes)
                        arg_atacker1 = data_package[1]
                        arg_atacker2 = (ball - attacker2).arg()
                        flag_to_kick_ball1 = wp.WType.S_BALL_KICK
                        flag_to_kick_ball2 = wp.WType.S_IGNOREOBSTACLES

                        """ перебираем ситуации чтобы понять когда принимать пас """
                        if self.flag == False and (ball - attacker1).mag() < 250:
                            self.flag = True
                        if self.flag == True and field.is_ball_moves():
                            self.passes_status = flag_to_passes.true_attacker1
                            self.flag = False

                else:
                    if mid is not 0 and ball.x < 0:
                        """ удар в ворота """
                        pos_attacker2 = ball
                        pos_attacker1 = defer(attacker1)
                        field.strategy_image.draw_line(
                            ball, pos_attacker1, (255, 0, 255), 3
                        ) 
                        arg_atacker2 = arg_atacker  
                        flag_to_kick_ball2 = wp.WType.S_BALL_KICK
                        flag_to_kick_ball1 = wp.WType.S_IGNOREOBSTACLES
                    else:
                        """ пас """
                        data_package = pas(ball, attacker2, attacker1)
                        pos_attacker2 = ball 
                        pos_attacker1 = optimal_point(ball, list_enemy, list_point_passes)
                        arg_atacker2 = data_package[1]
                        arg_atacker1 = (ball - attacker1).arg()
                        flag_to_kick_ball2 = wp.WType.S_BALL_KICK
                        flag_to_kick_ball1 = wp.WType.S_IGNOREOBSTACLES

                        """ перебираем ситуации чтобы понять когда принимать пас """
                        if self.flag == False and (ball - attacker2).mag() < 250:
                            self.flag = True
                        if self.flag == True and field.is_ball_moves():
                            self.passes_status = flag_to_passes.true_attacker2
                            self.flag = False


        ############################## Waypoints ###############################
        
        waypoints[self.idx_gk] = wp.Waypoint(
           pos,
           args,
           flag_to_kick_goalkeeper,
        )

        waypoints[self.idx1] = wp.Waypoint(
            pos_attacker1,
            arg_atacker1,
            flag_to_kick_ball1,
        )

        waypoints[self.idx2] = wp.Waypoint(
            pos_attacker2,
            arg_atacker2,
            flag_to_kick_ball2,
        )

        return waypoints