# =============================================================================
# >> IMPORTS
# =============================================================================
# Python
from configparser import ConfigParser
from enum import IntEnum
from time import time

# Source.Python
from colors import Color
from commands.say import SayCommand
from engines.precache import Model
from engines.server import global_vars
from engines.trace import (
    ContentMasks, engine_trace, GameTrace, MAX_TRACE_LENGTH, Ray,
    TraceFilterSimple)
from entities.constants import SolidType
from entities.entity import Entity
from entities.helpers import index_from_pointer
from entities.hooks import EntityCondition, EntityPostHook, EntityPreHook
from events import Event
from filters.players import PlayerIter
from listeners import OnLevelInit
from listeners.tick import Delay, Repeat
from mathlib import Vector
from messages import HudMsg, SayText2
from players.dictionary import PlayerDictionary
from players.entity import Player
from stringtables.downloads import Downloadables

# CTF
from .core.cvars import config_manager
from .core.paths import DOWNLOADLIST_PATH, MAPDATA_PATH
from .core.strings import colorize, common_strings, strip_colors, tagged
from .info import info


# =============================================================================
# >> CONSTANTS
# =============================================================================
FLAG_MODEL = Model("models/props/cs_militia/caseofbeer01.mdl")
FLAG_DIMENSIONS = (0, 0, 12)
RED_FLAG_COLOR = Color(210, 80, 70)
BLUE_FLAG_COLOR = Color(0, 100, 255)
GLOW_DISTANCE = 10240
DROP_FLAG_COMMAND_DELAY = 2

HUDMSG_COLOR = Color(255, 205, 70)
HUDMSG_X = -1
HUDMSG_Y = 0.1
HUDMSG_EFFECT = 2
HUDMSG_FADEIN = 0.05
HUDMSG_FADEOUT = 0
HUDMSG_HOLDTIME = 3
HUDMSG_FXTIME = 0
HUDMSG_CHANNEL = 5

FLAGMSG_COLOR = Color(255, 205, 70)
FLAGMSG_X = 0.05
FLAGMSG_Y = 0.9
FLAGMSG_EFFECT = 0
FLAGMSG_FADEIN = 0
FLAGMSG_FADEOUT = 0
FLAGMSG_HOLDTIME = 2
FLAGMSG_FXTIME = 0
FLAGMSG_CHANNEL = 6


class FlagTeam(IntEnum):
    RED = 2
    BLUE = 3


class FlagState(IntEnum):
    AT_BASE = 0
    STOLEN = 1
    DROPPED = 2


WIN_CONDITIONS = {
    0: 9,  # Round draw
    2: 8,  # Terrorists win
    3: 7,  # Counter-Terrorists win
}


# =============================================================================
# >> GLOBAL VARIABLES
# =============================================================================
_flags = {}
_team_points = {}
_round_end = False

_ecx_storage_start_touch_flags = {}
_ecx_storage_start_touch_zones = {}

downloadables = Downloadables()
with open(DOWNLOADLIST_PATH) as f:
    for line in f:
        line = line.strip()
        if not line:
            continue

        downloadables.add(line)


# =============================================================================
# >> CLASSES
# =============================================================================
class CTFPlayerDictionary(PlayerDictionary):
    def on_automatically_removed(self, index):
        ctfplayer = self[index]

        for flag in _flags.values():
            if flag.ctfplayer is not None and flag.ctfplayer == ctfplayer:
                flag.drop()


class CTFPlayer:
    _self_attributes = ('player', 'dropped_flag_at')

    def __init__(self, index):
        self.player = Player(index)
        self.dropped_flag_at = 0

    def __eq__(self, other):
        return self.player == other.player

    def __getattr__(self, attr_name):
        return getattr(self.player, attr_name)

    def __setattr__(self, attr_name, value):
        if attr_name in self._self_attributes:
            return super().__setattr__(attr_name, value)

        setattr(self.player, attr_name, value)

    @property
    def team(self):
        try:
            return FlagTeam(self.player.team)
        except ValueError:
            return None

ctfplayers = CTFPlayerDictionary(CTFPlayer)


class Flag:
    def __init__(self, team, model, color, glow_distance, origin, cap_v1,
                 cap_v2):

        self.team = team
        self.model = model
        self.color = color
        self.glow_distance = glow_distance
        self.origin = origin
        self._cap_v1 = cap_v1
        self._cap_v2 = cap_v2

        self._entity = None
        self._capture_zone_entity = None
        self._ctfplayer = None
        self._state = FlagState.AT_BASE
        self._dropped_at = 0
        self._return_delay = None

    def __repr__(self):
        return f"<Flag ({self.team.name}) - {self._state.name}>"

    @property
    def ctfplayer(self):
        return self._ctfplayer

    @property
    def state(self):
        return self._state

    @property
    def state_string(self):
        if self.state == FlagState.AT_BASE:
            return common_strings['location home']

        if self.state == FlagState.STOLEN:
            return common_strings['location player'].tokenized(
                player=self.ctfplayer.name)

        if self.state == FlagState.DROPPED:
            time_left = config_manager['dropped_flag_return_timeout']
            time_left -= time() - self._dropped_at

            return common_strings['location dropped'].tokenized(
                time=time_left
            )

    @property
    def entity_index(self):
        if self._entity is None:
            return -1

        return self._entity.index

    @property
    def capture_zone_entity_index(self):
        if self._capture_zone_entity is None:
            return -1

        return self._capture_zone_entity.index

    def _find_floor(self, origin):
        if origin is None:
            origin = self.origin

        end_trace_vec = origin + Vector(0, 0, -1) * MAX_TRACE_LENGTH

        trace = GameTrace()
        engine_trace.trace_ray(
            Ray(origin, end_trace_vec),
            ContentMasks.ALL,
            TraceFilterSimple(),
            trace
        )

        if not trace.did_hit():
            return None

        return trace.end_position

    def _spawn_entity(self, origin=None):
        floor_origin = self._find_floor(origin)
        if floor_origin is None:
            origin = self.origin
        else:
            origin = floor_origin + Vector(0, 0, FLAG_DIMENSIONS[2] / 2)

        self._entity = Entity.create('prop_dynamic_glow')
        self._entity.model = self.model

        if config_manager['flags_glow']:
            self._entity.glow_color = self.color
            self._entity.glow_enabled = True
            self._entity.set_key_value_int('glowdist', self.glow_distance)

        self._entity.solid_type = SolidType.VPHYSICS
        self._entity.teleport(origin)
        self._entity.spawn()

    def _remove_entity(self):
        self._entity.remove()
        self._entity = None

    def _split_players(self):
        enemy_players, team_players = [], []
        for player in PlayerIter():
            if player.team == self.team.value:
                team_players.append(player.index)
            else:
                enemy_players.append(player.index)

        return enemy_players, team_players

    def init(self):
        self._state = FlagState.AT_BASE
        self._spawn_entity()

        if self._return_delay is not None and self._return_delay.running:
            self._return_delay.cancel()

        self._return_delay = None

    def init_capture_zone(self):
        self._capture_zone_entity = entity = Entity.create('trigger_multiple')
        entity.set_key_value_string(
            "model", "maps/{map_name}.bsp".format(
                map_name=global_vars.map_name))

        entity.spawn()

        entity.flags = 1  # Gets triggered and angry by clients
        entity.solid_type = SolidType.BBOX

        origin = (self._cap_v1 + self._cap_v2) / 2
        v1 = self._cap_v1 - origin
        v2 = self._cap_v2 - origin

        entity.origin = origin
        entity.mins = Vector(min(v1.x, v2.x), min(v1.y, v2.y), min(v1.z, v2.z))
        entity.maxs = Vector(max(v1.x, v2.x), max(v1.y, v2.y), max(v1.z, v2.z))

    def steal(self, ctfplayer):
        if self._state not in (FlagState.DROPPED, FlagState.AT_BASE):
            raise ValueError(f"Flag state is {self._state} - cannot steal!")

        self._state = FlagState.STOLEN
        self._dropped_at = 0

        self._remove_entity()
        self._ctfplayer = ctfplayer

        if self._return_delay is not None and self._return_delay.running:
            self._return_delay.cancel()

        send_flag_message(common_strings['flag stolen'], self, self.ctfplayer)

        enemy_players, team_players = self._split_players()
        config_manager['team_flag_stolen_sound'].play(*team_players)
        config_manager['enemy_flag_stolen_sound'].play(*enemy_players)

    def drop(self):
        if self._state != FlagState.STOLEN:
            raise ValueError(f"Flag state is {self._state} - cannot drop!")

        self._state = FlagState.DROPPED
        self._dropped_at = time()

        origin = self.ctfplayer.origin
        self._spawn_entity(origin)

        send_flag_message(common_strings['flag dropped'], self, self.ctfplayer)

        self._ctfplayer = None

        self._return_delay = Delay(
            config_manager['dropped_flag_return_timeout'],
            self.return_, cancel_on_level_end=True)

        enemy_players, team_players = self._split_players()
        config_manager['team_flag_dropped_sound'].play(*team_players)
        config_manager['enemy_flag_dropped_sound'].play(*enemy_players)

    def return_(self, player=None):
        if self._state != FlagState.DROPPED:
            raise ValueError(f"Flag state is {self._state} - cannot return!")

        self._state = FlagState.AT_BASE
        self._dropped_at = 0

        self._remove_entity()
        self._spawn_entity()

        self._return_delay = None

        if player is None:
            send_flag_message(common_strings['flag returned'], self)
        else:
            send_flag_message(
                common_strings['flag returned_player'], self, player)

        enemy_players, team_players = self._split_players()
        config_manager['team_flag_returned_sound'].play(*team_players)
        config_manager['enemy_flag_returned_sound'].play(*enemy_players)

    def capture(self):
        if self._state != FlagState.STOLEN:
            raise ValueError(f"Flag state is {self._state} - cannot capture!")

        self._state = FlagState.AT_BASE

        send_flag_message(
            common_strings['flag captured'], self, self.ctfplayer)

        _team_points[self.ctfplayer.team] += 1
        if _team_points[self.ctfplayer.team] >= config_manager['caps_to_win']:
            victory(self.ctfplayer.team)
        else:
            self._spawn_entity()

        self._ctfplayer = None

        enemy_players, team_players = self._split_players()
        config_manager['team_flag_captured_sound'].play(*team_players)
        config_manager['enemy_flag_captured_sound'].play(*enemy_players)


# =============================================================================
# >> FUNCTIONS
# =============================================================================
def victory(team):
    message = common_strings['team victory ' + team.name.lower()]
    SayText2(tagged(colorize(message))).send()

    for team in _team_points.keys():
        _team_points[team] = 0

    info_map_parameters = Entity.find_or_create('info_map_parameters')
    info_map_parameters.fire_win_condition(WIN_CONDITIONS.get(
        team.value, WIN_CONDITIONS[0]))


def send_flag_message(message, flag, player=None):
    if player is None:
        message = message.tokenized(
            flag=colorize(
                common_strings['flag name ' + flag.team.name.lower()]),
        )
    else:
        message = message.tokenized(
            player=player.name,
            flag=colorize(
                common_strings['flag name ' + flag.team.name.lower()]),
        )

    SayText2(tagged(colorize(message))).send()
    HudMsg(
        strip_colors(message),
        color1=HUDMSG_COLOR,
        x=HUDMSG_X,
        y=HUDMSG_Y,
        effect=HUDMSG_EFFECT,
        fade_in=HUDMSG_FADEIN,
        fade_out=HUDMSG_FADEOUT,
        hold_time=HUDMSG_HOLDTIME,
        fx_time=HUDMSG_FXTIME,
        channel=HUDMSG_CHANNEL,
    ).send()


def get_server_file(path):
    server_path = path.dirname() / (path.namebase + "_server" + path.ext)
    if server_path.isfile():
        return server_path
    return path


def vector_from_str(str_):
    return Vector(*list(map(lambda x: float(x.strip()), str_.split(','))))


def load_map_data(map_name):
    _flags.clear()

    path_ini = get_server_file(MAPDATA_PATH / f"{map_name}.ini")

    if not path_ini.isfile():
        return

    with open(path_ini, 'r') as f:
        config = ConfigParser()
        config.read_file(f)

        red_origin = vector_from_str(config['red_flag']['origin'])
        red_capture_zone_point1 = vector_from_str(
            config['red_flag']['capture_zone_point1'])
        red_capture_zone_point2 = vector_from_str(
            config['red_flag']['capture_zone_point2'])
        blue_origin = vector_from_str(config['blue_flag']['origin'])
        blue_capture_zone_point1 = vector_from_str(
            config['blue_flag']['capture_zone_point1'])
        blue_capture_zone_point2 = vector_from_str(
            config['blue_flag']['capture_zone_point2'])

        _flags[FlagTeam.RED.value] = Flag(
            FlagTeam.RED, FLAG_MODEL, RED_FLAG_COLOR, GLOW_DISTANCE,
            red_origin, red_capture_zone_point1, red_capture_zone_point2)

        _flags[FlagTeam.BLUE.value] = Flag(
            FlagTeam.BLUE, FLAG_MODEL, BLUE_FLAG_COLOR, GLOW_DISTANCE,
            blue_origin, blue_capture_zone_point1, blue_capture_zone_point2)


# =============================================================================
# >> LOAD & UNLOAD
# =============================================================================
def load():
    if global_vars.map_name is not None:
        load_map_data(global_vars.map_name)


# =============================================================================
# >> EVENTS
# =============================================================================
@SayCommand(['!dropflag', '!df'])
def say_df(command, index, team_only):
    if not config_manager['allow_drop_flag_command']:
        SayText2(tagged(colorize(common_strings['disabled']))).send(index)
        return

    ctfplayer = ctfplayers[index]
    for flag in _flags.values():
        if flag.ctfplayer is not None and flag.ctfplayer == ctfplayer:
            ctfplayer.dropped_flag_at = time()
            flag.drop()
            break

    else:
        SayText2(tagged(colorize(
            common_strings['no_flag_on_you']))).send(index)


# =============================================================================
# >> EVENTS
# =============================================================================
@Event('round_start')
def on_round_start(game_event):
    global _round_end
    _round_end = False

    for team in _team_points.keys():
        _team_points[team] = 0

    for team in FlagTeam:
        _team_points[team] = 0

    for flag in _flags.values():
        flag.init()
        flag.init_capture_zone()


@Event('round_end')
def on_round_end(game_event):
    global _round_end
    _round_end = True


@Event('player_death')
def on_player_death(game_event):
    ctfplayer = ctfplayers.from_userid(game_event['userid'])
    for flag in _flags.values():
        if flag.ctfplayer is not None and flag.ctfplayer == ctfplayer:
            flag.drop()
            break


# =============================================================================
# >> HOOKS
# =============================================================================
@EntityPreHook(EntityCondition.equals_entity_classname(
    'trigger_multiple'), "start_touch")
def pre_start_touch(stack_data):
    entity_index = index_from_pointer(stack_data[0])
    other_index = index_from_pointer(stack_data[1])
    _ecx_storage_start_touch_zones[
        stack_data.registers.esp.address.address] = (entity_index, other_index)


@EntityPreHook(EntityCondition.equals_entity_classname(
    'prop_dynamic_glow'), "start_touch")
def pre_start_touch(stack_data):
    entity_index = index_from_pointer(stack_data[0])
    other_index = index_from_pointer(stack_data[1])
    _ecx_storage_start_touch_flags[
        stack_data.registers.esp.address.address] = (entity_index, other_index)


@EntityPostHook(EntityCondition.equals_entity_classname(
    'trigger_multiple'), "start_touch")
def post_start_touch(stack_data, ret_val):
    entity_index, other_index = _ecx_storage_start_touch_zones.pop(
        stack_data.registers.esp.address.address)

    try:
        ctfplayer = ctfplayers[other_index]
    except ValueError:
        return

    if ctfplayer.team is None:
        return

    if (config_manager['capping_requires_flag_at_base'] and
            _flags[ctfplayer.team].state != FlagState.AT_BASE):

        return

    for flag in _flags.values():
        if flag.capture_zone_entity_index != entity_index:
            continue

        if flag.ctfplayer is not None and flag.ctfplayer == ctfplayer:
            flag.capture()

        break


@EntityPostHook(EntityCondition.equals_entity_classname(
    'prop_dynamic_glow'), "start_touch")
def post_start_touch(stack_data, ret_val):
    entity_index, other_index = _ecx_storage_start_touch_flags.pop(
        stack_data.registers.esp.address.address)

    try:
        ctfplayer = ctfplayers[other_index]
    except ValueError:
        return

    if ctfplayer.team is None:
        return

    if time() - ctfplayer.dropped_flag_at < DROP_FLAG_COMMAND_DELAY:
        return

    for flag in _flags.values():
        if flag.entity_index != entity_index:
            continue

        if ctfplayer.team != flag.team:
            flag.steal(ctfplayer)

        elif config_manager['team_can_return_flag']:
            flag.return_(ctfplayer)

        break


# =============================================================================
# >> LISTENERS
# =============================================================================
@OnLevelInit
def listener_on_level_init(map_name):
    load_map_data(map_name)


# =============================================================================
# >> REPEATS
# =============================================================================
@Repeat
def repeat_flag_stat_display():
    if not _flags or not _team_points:
        return

    HudMsg(
        common_strings['flag_stats'].tokenized(
            red_points=_team_points[FlagTeam.RED.value],
            red_flag=_flags[FlagTeam.RED.value].state_string,
            blue_points=_team_points[FlagTeam.BLUE.value],
            blue_flag=_flags[FlagTeam.BLUE.value].state_string,
        ),
        color1=FLAGMSG_COLOR,
        x=FLAGMSG_X,
        y=FLAGMSG_Y,
        effect=FLAGMSG_EFFECT,
        fade_in=FLAGMSG_FADEIN,
        fade_out=FLAGMSG_FADEOUT,
        hold_time=FLAGMSG_HOLDTIME,
        fx_time=FLAGMSG_FXTIME,
        channel=FLAGMSG_CHANNEL
    ).send()

repeat_flag_stat_display.start(1.0)
