# =============================================================================
# >> IMPORTS
# =============================================================================
# Custom Package
from controlled_cvars import ControlledConfigManager, InvalidValue
from controlled_cvars.handlers import (
    bool_handler, float_handler, int_handler, sound_nullable_handler)

# Map Cycle
from ..info import info
from .strings import config_strings


def uint_handler(cvar):
    value = int_handler(cvar)
    if value < 0:
        raise InvalidValue
    return value


def ufloat_handler(cvar):
    value = float_handler(cvar)
    if value < 0:
        raise InvalidValue
    return value


config_manager = ControlledConfigManager(
    info.name + "/main", cvar_prefix='ctf_')

config_manager.section(config_strings['section gameplay'])
config_manager.controlled_cvar(
    float_handler,
    "dropped_flag_return_timeout",
    default=45.0,
    description=config_strings['dropped_flag_return_timeout'],
)
config_manager.controlled_cvar(
    bool_handler,
    "team_can_return_flag",
    default=0,
    description=config_strings['team_can_return_flag'],
)
config_manager.controlled_cvar(
    bool_handler,
    "capping_requires_flag_at_base",
    default=0,
    description=config_strings['capping_requires_flag_at_base'],
)
config_manager.controlled_cvar(
    bool_handler,
    "flags_glow",
    default=1,
    description=config_strings['flags_glow'],
)
config_manager.controlled_cvar(
    bool_handler,
    "players_glow",
    default=1,
    description=config_strings['players_glow'],
)
config_manager.controlled_cvar(
    int_handler,
    "caps_to_win",
    default=3,
    description=config_strings['caps_to_win'],
)
config_manager.section(config_strings['section sounds'])
config_manager.controlled_cvar(
    sound_nullable_handler,
    "team_flag_stolen_sound",
    default="ctf/sfx_ctf_grab_en.mp3",
    description=config_strings['team_flag_stolen_sound'],
)
config_manager.controlled_cvar(
    sound_nullable_handler,
    "enemy_flag_stolen_sound",
    default="ctf/sfx_ctf_grab_pl.mp3",
    description=config_strings['enemy_flag_stolen_sound'],
)
config_manager.controlled_cvar(
    sound_nullable_handler,
    "team_flag_dropped_sound",
    default="ctf/sfx_ctf_drop.mp3",
    description=config_strings['team_flag_dropped_sound'],
)
config_manager.controlled_cvar(
    sound_nullable_handler,
    "enemy_flag_dropped_sound",
    default="ctf/sfx_ctf_drop.mp3",
    description=config_strings['enemy_flag_dropped_sound'],
)
config_manager.controlled_cvar(
    sound_nullable_handler,
    "team_flag_returned_sound",
    default="ctf/sfx_ctf_rtn.mp3",
    description=config_strings['team_flag_returned_sound'],
)
config_manager.controlled_cvar(
    sound_nullable_handler,
    "enemy_flag_returned_sound",
    default="ctf/sfx_ctf_rtn.mp3",
    description=config_strings['enemy_flag_returned_sound'],
)
config_manager.controlled_cvar(
    sound_nullable_handler,
    "team_flag_captured_sound",
    default="ctf/sfx_ctf_cap_pl.mp3",
    description=config_strings['team_flag_captured_sound'],
)
config_manager.controlled_cvar(
    sound_nullable_handler,
    "enemy_flag_captured_sound",
    default="ctf/sfx_ctf_cap_pl.mp3",
    description=config_strings['enemy_flag_captured_sound'],
)
config_manager.section(config_strings['section misc'])
config_manager.controlled_cvar(
    bool_handler,
    "allow_drop_flag_command",
    default=1,
    description=config_strings['allow_drop_flag_command'],
)

config_manager.write()
config_manager.execute()
