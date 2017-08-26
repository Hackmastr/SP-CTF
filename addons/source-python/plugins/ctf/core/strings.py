# =============================================================================
# >> IMPORTS
# =============================================================================
# Source.Python
from colors import Color
from core import GAME_NAME
from translations.strings import LangStrings

# Map Cycle
from ..info import info


# =============================================================================
# >> FUNCTIONS
# =============================================================================
def tagged(message):
    return common_strings['chat_base'].tokenized(
        message=message, **COLOR_SCHEME)


def colorize(message):
    return message.tokenized(**message.tokens, **COLOR_SCHEME)


def strip_colors(message):
    return message.tokenized(
        **message.tokens, **{key: '' for key in COLOR_SCHEME.keys()}
    )


# =============================================================================
# >> GLOBAL VARIABLES
# =============================================================================
# Map color variables in translation files to actual Color instances
if GAME_NAME in ('csgo', ):
    COLOR_SCHEME = {
        'color_highlight': "\x10",
        'color_default': "\x01",
        'color_red': "\x0F",
        'color_blue': "\x0B",
    }
else:
    COLOR_SCHEME = {
        'color_highlight': Color(255, 205, 70),
        'color_default': Color(242, 242, 242),
        'color_red': Color(210, 80, 70),
        'color_blue': Color(0, 100, 255),
    }

common_strings = LangStrings(info.name + "/strings")
config_strings = LangStrings(info.name + "/config")
