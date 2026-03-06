"""
Parser for Steam-style %command% launch options.

This module provides functionality to parse launch command strings that use
Steam's %command% placeholder syntax, extracting environment variables,
wrapper executables, and game arguments.
"""

import shlex
from dataclasses import dataclass, field


@dataclass
class ParsedLaunchCommand:
    """Parsed components of a Steam-style launch command.

    Attributes:
        env_vars: Dictionary of environment variable names to values
        wrapper_commands: List of wrapper executable names to prepend
        game_args: List of arguments to pass to the game executable
    """

    env_vars: dict[str, str] = field(default_factory=dict)
    wrapper_commands: list[str] = field(default_factory=list)
    game_args: list[str] = field(default_factory=list)


def parse_launch_command(command_string: str) -> ParsedLaunchCommand:
    """
    Parse Steam-style %command% syntax into components.

    The parser tokenizes the command string and separates it into three parts:
    - Environment variables (VAR=value tokens before %command%)
    - Wrapper executables (other tokens before %command%)
    - Game arguments (tokens after %command%)

    Examples:
        >>> parse_launch_command("PROTON_LOG=1 %command%")
        ParsedLaunchCommand(env_vars={'PROTON_LOG': '1'}, wrapper_commands=[], game_args=[])

        >>> parse_launch_command("gamemoderun %command%")
        ParsedLaunchCommand(env_vars={}, wrapper_commands=['gamemoderun'], game_args=[])

        >>> parse_launch_command("DXVK_HUD=1 gamemoderun %command% -logfile /tmp/log")
        ParsedLaunchCommand(
            env_vars={'DXVK_HUD': '1'},
            wrapper_commands=['gamemoderun'],
            game_args=['-logfile', '/tmp/log']
        )

        >>> parse_launch_command("%command% -logfile /tmp/log")
        ParsedLaunchCommand(env_vars={}, wrapper_commands=[], game_args=['-logfile', '/tmp/log'])

    Edge cases:
        - No %command%: All tokens treated as game_args (backwards compatible)
        - Multiple %command%: First occurrence used as placeholder, rest are literal args
        - Empty string: Returns empty ParsedLaunchCommand
        - Quoted values: Handled by shlex (VAR="value with spaces" works correctly)

    :param command_string: The raw command string from UI
    :return: ParsedLaunchCommand with separated components
    """
    if not command_string or not command_string.strip():
        return ParsedLaunchCommand()

    try:
        # Use shlex to tokenize - handles quotes, spaces, and escaping
        tokens = shlex.split(command_string)
    except ValueError:
        # If shlex fails (e.g., unclosed quotes), treat as game args
        return ParsedLaunchCommand(game_args=[command_string])

    if not tokens:
        return ParsedLaunchCommand()

    # Find the %command% placeholder
    try:
        command_index = tokens.index("%command%")
    except ValueError:
        # No %command% found - treat all tokens as game args for backwards compatibility
        return ParsedLaunchCommand(game_args=tokens)

    env_vars: dict[str, str] = {}
    wrapper_commands: list[str] = []

    # Parse tokens before %command%
    for token in tokens[:command_index]:
        if "=" in token:
            # This is an environment variable
            key, value = token.split("=", 1)  # Split on first '=' only
            env_vars[key] = value
        else:
            # This is a wrapper executable
            wrapper_commands.append(token)

    # Tokens after %command% are game arguments
    # If there are multiple %command% placeholders, subsequent ones become literal args
    game_args = tokens[command_index + 1 :]

    return ParsedLaunchCommand(
        env_vars=env_vars, wrapper_commands=wrapper_commands, game_args=game_args
    )
