"""Config command implementation."""

import argparse
import sys
from collections.abc import Callable
from typing import Any

from skilz.completion import get_shell_type, install_completion
from skilz.config import (
    CONFIG_PATH,
    DEFAULTS,
    VALID_AGENTS,
    config_exists,
    get_config_sources,
    get_effective_config,
    save_config,
)
from skilz.config_scopes import (
    ConfigScope,
    MERGE_KEYS,
    SCALAR_KEYS,
    find_project_root,
    get_all_scope_configs,
    get_config_with_origins,
    get_scope_config,
    get_scope_config_path,
    resolve_config,
    save_scope_config,
    unset_scope_config_key,
)


def format_value(value: Any, max_len: int = 30) -> str:
    """Format a value for display, truncating if needed."""
    if value is None:
        return "(not set)"
    if isinstance(value, list):
        if not value:
            return "[]"
        val_str = ", ".join(str(v) for v in value)
    else:
        val_str = str(value)
    if len(val_str) > max_len:
        return val_str[: max_len - 3] + "..."
    return val_str


def _get_selected_scope(args: argparse.Namespace) -> ConfigScope | None:
    """Get the scope selected by CLI flags, or None if no scope specified."""
    if getattr(args, "system", False):
        return ConfigScope.SYSTEM
    if getattr(args, "user_scope", False):
        return ConfigScope.USER
    if getattr(args, "project", False):
        return ConfigScope.PROJECT
    if getattr(args, "local", False):
        return ConfigScope.LOCAL
    return None


def cmd_config_files(args: argparse.Namespace) -> int:
    """Show config file paths and their status."""
    project_root = find_project_root()

    print("Configuration files:")
    print()

    for scope in ConfigScope:
        path = get_scope_config_path(scope, project_root)
        if path is None:
            status = "(not applicable)"
            path_str = "-"
        elif path.exists():
            status = "(found)"
            path_str = str(path)
        else:
            status = "(not found)"
            path_str = str(path)

        print(f"  {scope.value:<8} {path_str:<50} {status}")

    return 0


def cmd_config_show_origin(args: argparse.Namespace) -> int:
    """Show effective config values with their source scope."""
    verbose = getattr(args, "verbose", False)
    project_root = find_project_root()

    if verbose:
        # Full audit: show all values from all scopes
        scope_configs = get_all_scope_configs(project_root)

        for scope in ConfigScope:
            path, config = scope_configs[scope]
            if path is None:
                print(f"{scope.value}:  (not applicable)")
            elif not path.exists():
                print(f"{scope.value}:  {path} (not found)")
            else:
                print(f"{scope.value}:  {path}")
                for key, value in config.items():
                    print(f"         {key} = {format_value(value, 50)}")
            print()

        print("effective:")

    # Show effective values with origins
    origins = get_config_with_origins(project_root)

    # Get all known keys
    all_keys = set(SCALAR_KEYS) | set(MERGE_KEYS)

    for key in sorted(all_keys):
        if key in origins:
            value, source = origins[key]
            value_str = format_value(value, 40)
            print(f"  {key:<20} = {value_str:<40} ({source})")

    return 0


def cmd_config_list_scope(args: argparse.Namespace) -> int:
    """List config values for a specific scope."""
    scope = _get_selected_scope(args)
    project_root = find_project_root()

    if scope is None:
        # List all effective config
        config = resolve_config(project_root)
        print("Effective configuration:")
        for key, value in sorted(config.items()):
            print(f"  {key} = {format_value(value, 50)}")
    else:
        # List specific scope
        path = get_scope_config_path(scope, project_root)
        config = get_scope_config(scope, project_root)

        if path:
            print(f"{scope.value} config: {path}")
        else:
            print(f"{scope.value} config: (not applicable)")

        if config:
            for key, value in sorted(config.items()):
                print(f"  {key} = {format_value(value, 50)}")
        else:
            print("  (empty)")

    return 0


def cmd_config_get(args: argparse.Namespace) -> int:
    """Get a specific config key's value."""
    key = args.key
    show_origin = getattr(args, "show_origin", False)
    scope = _get_selected_scope(args)
    project_root = find_project_root()

    if scope is not None:
        # Get from specific scope
        config = get_scope_config(scope, project_root)
        if key in config:
            print(config[key])
        else:
            print(f"Key '{key}' not set in {scope.value} config", file=sys.stderr)
            return 1
    else:
        # Get effective value
        if show_origin:
            origins = get_config_with_origins(project_root)
            if key in origins:
                value, source = origins[key]
                print(f"{value}  ({source})")
            else:
                print(f"Unknown key: {key}", file=sys.stderr)
                return 1
        else:
            config = resolve_config(project_root)
            if key in config:
                value = config[key]
                if isinstance(value, list):
                    for item in value:
                        print(item)
                else:
                    print(value if value is not None else "")
            else:
                print(f"Unknown key: {key}", file=sys.stderr)
                return 1

    return 0


def cmd_config_set(args: argparse.Namespace) -> int:
    """Set a config key's value."""
    key = args.key
    value = args.value
    scope = _get_selected_scope(args) or ConfigScope.USER  # Default to user scope
    project_root = find_project_root()

    # Validate key
    all_keys = set(SCALAR_KEYS) | set(MERGE_KEYS) | {f"{k}!" for k in MERGE_KEYS}
    base_key = key.rstrip("!")
    if base_key not in (SCALAR_KEYS | MERGE_KEYS):
        print(f"Unknown config key: {key}", file=sys.stderr)
        print(f"Valid keys: {', '.join(sorted(SCALAR_KEYS | MERGE_KEYS))}", file=sys.stderr)
        return 1

    # Check project root for project/local scopes
    if scope in (ConfigScope.PROJECT, ConfigScope.LOCAL) and project_root is None:
        print(f"Cannot set {scope.value} config: not in a project directory", file=sys.stderr)
        return 1

    # Load existing config for this scope
    config = get_scope_config(scope, project_root)

    # Parse value for list keys
    if base_key in MERGE_KEYS and not key.endswith("!"):
        # For merge keys, append to existing list unless using override syntax
        existing = config.get(key, [])
        if not isinstance(existing, list):
            existing = []
        if value not in existing:
            existing.append(value)
        config[key] = existing
    else:
        config[key] = value

    # Save
    try:
        path = save_scope_config(scope, config, project_root)
        print(f"Set {key} = {value} in {path}")
    except (ValueError, OSError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    return 0


def cmd_config_unset(args: argparse.Namespace) -> int:
    """Remove a config key."""
    key = args.key
    scope = _get_selected_scope(args) or ConfigScope.USER  # Default to user scope
    project_root = find_project_root()

    if scope in (ConfigScope.PROJECT, ConfigScope.LOCAL) and project_root is None:
        print(f"Cannot unset {scope.value} config: not in a project directory", file=sys.stderr)
        return 1

    try:
        removed = unset_scope_config_key(scope, key, project_root)
        if removed:
            path = get_scope_config_path(scope, project_root)
            print(f"Removed {key} from {path}")
        else:
            print(f"Key '{key}' not found in {scope.value} config")
            return 1
    except (ValueError, OSError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    return 0


def cmd_config_show(args: argparse.Namespace) -> int:
    """
    Show current configuration (legacy format for backwards compatibility).

    Displays all configuration values with their sources (default, file, env).
    """
    verbose = getattr(args, "verbose", False)

    # Get config sources for detailed display
    sources = get_config_sources()

    # Header
    if config_exists():
        print(f"Configuration: {CONFIG_PATH}")
    else:
        print(f"Configuration: {CONFIG_PATH} (not created)")

    print()

    # Column headers
    print(f"{'Setting':<20} {'Config File':<18} {'Env Override':<18} {'Effective':<20}")
    print("-" * 76)

    # Display each setting
    for key in DEFAULTS:
        source = sources[key]
        file_val = format_value(source["file"], 16)
        env_val = format_value(source["env"], 16)
        effective_val = format_value(source["effective"], 18)

        # Show env var name in verbose mode
        if verbose and source["env_var"]:
            env_val = f"{env_val} ({source['env_var']})"

        print(f"{key:<20} {file_val:<18} {env_val:<18} {effective_val:<20}")

    print()
    print("Use 'skilz config --init' to create or modify configuration.")

    return 0


def prompt_value(
    prompt: str, default: str | None, validator: Callable[[str], bool] | None = None
) -> str | None:
    """
    Prompt user for a value with a default.

    Args:
        prompt: The prompt to display.
        default: Default value (shown in brackets).
        validator: Optional function to validate input.

    Returns:
        The entered value, or default if empty.
    """
    default_display = default if default else "none"
    try:
        value = input(f"{prompt} [{default_display}]: ").strip()
        if not value:
            return default
        if validator and not validator(value):
            print("Invalid value, using default.")
            return default
        return value
    except (EOFError, KeyboardInterrupt):
        print()
        return None


def prompt_choice(prompt: str, choices: list[str], default: str) -> str | None:
    """
    Prompt user to select from choices.

    Args:
        prompt: The prompt to display.
        choices: List of valid choices.
        default: Default choice.

    Returns:
        The selected choice.
    """
    choices_str = "/".join(choices)
    try:
        value = input(f"{prompt} ({choices_str}) [{default}]: ").strip().lower()
        if not value:
            return default
        if value in choices:
            return value
        print(f"Invalid choice. Using default: {default}")
        return default
    except (EOFError, KeyboardInterrupt):
        print()
        return None


def prompt_shell_completion() -> str | None:
    """
    Prompt user to install shell completion.

    Returns:
        Shell type to install ('zsh', 'bash') or None to skip.
    """
    detected_shell = get_shell_type()

    print()
    print("Install shell completion?")
    print("  [1] zsh (~/.zshrc)")
    print("  [2] bash (~/.bashrc)")
    print("  [3] Skip")
    print()

    default = "3"
    if detected_shell == "zsh":
        default = "1"
    elif detected_shell == "bash":
        default = "2"

    try:
        choice = input(f"Choice [{default}]: ").strip() or default
        if choice == "1":
            return "zsh"
        elif choice == "2":
            return "bash"
        return None
    except (EOFError, KeyboardInterrupt):
        print()
        return None


def cmd_config_init(args: argparse.Namespace) -> int:
    """
    Initialize or modify configuration interactively.

    With -y flag, uses defaults without prompting.
    """
    verbose = getattr(args, "verbose", False)
    yes_flag = getattr(args, "yes", False) or getattr(args, "yes_all", False)

    current_config = get_effective_config()

    print()
    print("Skilz Configuration Setup")
    print("-" * 26)
    print()

    if yes_flag:
        # Non-interactive: use defaults
        new_config = DEFAULTS.copy()
        print("Using default configuration...")
    else:
        # Interactive mode
        new_config = {}

        # Claude Code home
        claude_default = current_config.get("claude_code_home") or DEFAULTS["claude_code_home"]
        claude_home = prompt_value("Claude Code home", claude_default)
        if claude_home is None:
            print("Cancelled.")
            return 0
        new_config["claude_code_home"] = claude_home

        # OpenCode home
        opencode_default = current_config.get("open_code_home") or DEFAULTS["open_code_home"]
        opencode_home = prompt_value("OpenCode home", opencode_default)
        if opencode_home is None:
            print("Cancelled.")
            return 0
        new_config["open_code_home"] = opencode_home

        # Default agent
        agent_choices = ["claude", "opencode", "auto"]
        current_agent = current_config.get("agent_default")
        agent_default = current_agent if current_agent in VALID_AGENTS else "auto"
        agent = prompt_choice("Default agent", agent_choices, agent_default)
        if agent is None:
            print("Cancelled.")
            return 0
        new_config["agent_default"] = None if agent == "auto" else agent

    # Save configuration
    try:
        save_config(new_config)
        print()
        print(f"Configuration saved to {CONFIG_PATH}")

        if verbose:
            print()
            print("Saved values:")
            for key, value in new_config.items():
                if value != DEFAULTS.get(key):
                    print(f"  {key}: {value}")

    except OSError as e:
        print(f"Error saving configuration: {e}", file=sys.stderr)
        return 1

    # Offer shell completion (only in interactive mode)
    if not yes_flag:
        shell = prompt_shell_completion()
        if shell:
            success, message = install_completion(shell)
            if success:
                print(message)
            else:
                print(f"Warning: {message}", file=sys.stderr)

    return 0


def cmd_config(args: argparse.Namespace) -> int:
    """
    Handle the config command.

    Supports:
    - skilz config                        # Show legacy format
    - skilz config --show-origin          # Show effective with sources
    - skilz config --files                # Show file paths
    - skilz config --list [--scope]       # List values
    - skilz config key                    # Get key
    - skilz config key value              # Set key
    - skilz config --unset key            # Unset key
    - skilz config --init                 # Interactive setup

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code (0 for success, non-zero for error).
    """
    init_flag = getattr(args, "init", False)
    show_origin = getattr(args, "show_origin", False)
    files_flag = getattr(args, "files", False)
    list_flag = getattr(args, "list_scope", False)
    unset_flag = getattr(args, "unset", False)
    key = getattr(args, "key", None)
    value = getattr(args, "value", None)

    # Route to appropriate handler
    if init_flag:
        return cmd_config_init(args)
    elif files_flag:
        return cmd_config_files(args)
    elif show_origin:
        return cmd_config_show_origin(args)
    elif list_flag:
        return cmd_config_list_scope(args)
    elif unset_flag:
        if not key:
            print("Error: --unset requires a key", file=sys.stderr)
            return 1
        return cmd_config_unset(args)
    elif key is not None:
        if value is not None:
            return cmd_config_set(args)
        else:
            return cmd_config_get(args)
    else:
        # Default: show legacy format
        return cmd_config_show(args)
