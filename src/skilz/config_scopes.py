"""Multi-scope configuration management for Skilz.

This module provides XDG-compliant configuration with four scopes:
- system: /etc/xdg/skilz/ (or $XDG_CONFIG_DIRS)
- user: ~/.config/skilz/ (or $XDG_CONFIG_HOME)  
- project: .skilz/config.json (git-tracked)
- local: .skilz/local.json (git-ignored)

Scalar settings cascade (most-specific wins): local > project > user > system
List settings merge (all scopes combined), with "-prefix" to remove items.
"""

from __future__ import annotations

import json
import os
from enum import Enum
from pathlib import Path
from typing import Any

from skilz.config import (
    DEFAULTS,
    ENV_VARS,
    get_xdg_config_dirs,
    get_xdg_config_home,
    get_xdg_data_dirs,
    get_xdg_data_home,
)


class ConfigScope(Enum):
    """Configuration scope levels, from broadest to most specific."""

    SYSTEM = "system"
    USER = "user"
    PROJECT = "project"
    LOCAL = "local"


class InstallScope(Enum):
    """Install destination scope for skilz-managed skill locations.

    AGENT: Install to agent's directory (e.g., ~/.claude/skills/) - default
    SYSTEM: Install to /usr/local/share/skilz/skills/ (requires sudo)
    USER: Install to ~/.local/share/skilz/skills/
    PROJECT: Install to .skilz/skills/ in current project
    """

    AGENT = "agent"  # Default: use agent's skill directory
    SYSTEM = "system"  # XDG system data dir
    USER = "user"  # XDG user data dir
    PROJECT = "project"  # Project-local .skilz/skills/


def get_install_scope_path(scope: InstallScope, project_root: Path | None = None) -> Path:
    """
    Get the skill installation directory for a scope.

    Args:
        scope: The installation scope
        project_root: Project root for PROJECT scope

    Returns:
        Path to skills directory for the scope

    Raises:
        ValueError: If PROJECT scope requested without project_root
    """
    match scope:
        case InstallScope.SYSTEM:
            # First entry of XDG_DATA_DIRS (typically /usr/local/share)
            data_dirs = get_xdg_data_dirs()
            return data_dirs[0] / "skilz" / "skills"
        case InstallScope.USER:
            return get_xdg_data_home() / "skilz" / "skills"
        case InstallScope.PROJECT:
            if not project_root:
                project_root = find_project_root() or Path.cwd()
            return project_root / ".skilz" / "skills"
        case InstallScope.AGENT:
            raise ValueError("AGENT scope requires agent-specific path resolution")
    # Should never reach here, but satisfy type checker
    raise ValueError(f"Unknown scope: {scope}")


def get_registry_path_for_scope(scope: InstallScope, project_root: Path | None = None) -> Path:
    """
    Get the registry file path for recording installations at a scope.

    Args:
        scope: The installation scope
        project_root: Project root for PROJECT scope

    Returns:
        Path to registry YAML file for the scope
    """
    match scope:
        case InstallScope.SYSTEM:
            # System registry in XDG data location (alongside skills)
            data_dirs = get_xdg_data_dirs()
            return data_dirs[0] / "skilz" / "registry.yaml"
        case InstallScope.USER:
            return get_xdg_data_home() / "skilz" / "registry.yaml"
        case InstallScope.PROJECT:
            if not project_root:
                project_root = find_project_root() or Path.cwd()
            return project_root / ".skilz" / "registry.yaml"
        case InstallScope.AGENT:
            # Default to user registry for agent installs
            return get_xdg_data_home() / "skilz" / "registry.yaml"
    # Should never reach here
    return get_xdg_data_home() / "skilz" / "registry.yaml"


# Keys that use cascade (most-specific wins)
SCALAR_KEYS = {"agent_default", "claude_code_home", "open_code_home", "default_install_mode"}

# Keys that use merge (all scopes combined)
MERGE_KEYS = {"skill_dirs", "disabled_skills", "registry_sources"}


def find_project_root(start: Path | None = None) -> Path | None:
    """
    Find project root by walking up from start directory.

    Looks for:
    1. .skilz/ directory (highest priority)
    2. .git/ directory (fallback)

    Args:
        start: Starting directory (defaults to cwd)

    Returns:
        Project root path, or None if not found
    """
    start = start or Path.cwd()
    try:
        start = start.resolve()
    except OSError:
        return None

    for parent in [start] + list(start.parents):
        if (parent / ".skilz").is_dir():
            return parent
        if (parent / ".git").is_dir():
            return parent
    return None


def _load_json_file(path: Path) -> dict[str, Any]:
    """Load JSON file, returning empty dict on error or missing file."""
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def get_scope_config_path(scope: ConfigScope, project_root: Path | None = None) -> Path | None:
    """
    Get the config file path for a specific scope.

    Args:
        scope: The configuration scope
        project_root: Project root for project/local scopes

    Returns:
        Path to config file, or None if scope not applicable
    """
    match scope:
        case ConfigScope.SYSTEM:
            # Return first XDG_CONFIG_DIRS entry (primary system config location)
            dirs = get_xdg_config_dirs()
            return dirs[0] / "skilz" / "config.json" if dirs else None
        case ConfigScope.USER:
            return get_xdg_config_home() / "skilz" / "settings.json"
        case ConfigScope.PROJECT:
            if project_root:
                return project_root / ".skilz" / "config.json"
            return None
        case ConfigScope.LOCAL:
            if project_root:
                return project_root / ".skilz" / "local.json"
            return None
    return None


def get_scope_config(scope: ConfigScope, project_root: Path | None = None) -> dict[str, Any]:
    """
    Load configuration for a specific scope.

    For system scope, searches all XDG_CONFIG_DIRS and returns first found.

    Args:
        scope: The configuration scope
        project_root: Project root for project/local scopes

    Returns:
        Configuration dictionary (empty if not found)
    """
    match scope:
        case ConfigScope.SYSTEM:
            # Search all XDG_CONFIG_DIRS, return first found
            for config_dir in get_xdg_config_dirs():
                config_path = config_dir / "skilz" / "config.json"
                config = _load_json_file(config_path)
                if config:
                    return config
            return {}
        case ConfigScope.USER:
            path = get_xdg_config_home() / "skilz" / "settings.json"
            return _load_json_file(path)
        case ConfigScope.PROJECT:
            if project_root:
                path = project_root / ".skilz" / "config.json"
                return _load_json_file(path)
            return {}
        case ConfigScope.LOCAL:
            if project_root:
                path = project_root / ".skilz" / "local.json"
                return _load_json_file(path)
            return {}
    return {}


def _merge_lists(
    scopes: dict[ConfigScope, dict[str, Any]], key: str, defaults: list[str] | None = None
) -> list[str]:
    """
    Merge a list key across all scopes, starting with defaults.

    Supports:
    - Normal items: added to merged list
    - "-item": removes item from merged result
    - "key!": in scope config replaces entirely (checked by caller)

    Args:
        scopes: Dict mapping scope to its config
        key: The key to merge
        defaults: Default list values to include before scope values

    Returns:
        Merged list with removals applied
    """
    # Start with defaults
    merged: list[str] = list(defaults) if defaults else []
    removals: set[str] = set()

    # Process scopes from broadest to most specific
    for scope in [ConfigScope.SYSTEM, ConfigScope.USER, ConfigScope.PROJECT, ConfigScope.LOCAL]:
        items = scopes[scope].get(key, [])
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, str):
                if item.startswith("-"):
                    removals.add(item[1:])
                elif item not in merged:
                    merged.append(item)

    # Apply removals
    return [item for item in merged if item not in removals]


def resolve_config(project_root: Path | None = None) -> dict[str, Any]:
    """
    Resolve effective configuration by merging all scopes.

    Applies:
    - Cascade for scalar keys (most-specific wins)
    - Merge for list keys (all scopes combined)
    - Environment variables (highest priority for scalars)

    Args:
        project_root: Project root path (auto-detected if None)

    Returns:
        Effective configuration dictionary
    """
    if project_root is None:
        project_root = find_project_root()

    # Load all scopes
    scopes = {
        ConfigScope.SYSTEM: get_scope_config(ConfigScope.SYSTEM),
        ConfigScope.USER: get_scope_config(ConfigScope.USER),
        ConfigScope.PROJECT: get_scope_config(ConfigScope.PROJECT, project_root),
        ConfigScope.LOCAL: get_scope_config(ConfigScope.LOCAL, project_root),
    }

    result: dict[str, Any] = dict(DEFAULTS)

    # Cascade scalars (system -> user -> project -> local)
    for key in SCALAR_KEYS:
        for scope in [ConfigScope.SYSTEM, ConfigScope.USER, ConfigScope.PROJECT, ConfigScope.LOCAL]:
            if key in scopes[scope]:
                result[key] = scopes[scope][key]

    # Merge lists
    for key in MERGE_KEYS:
        # Check for override (key!) - most specific scope wins
        override_key = f"{key}!"
        override_found = False
        for scope in reversed(
            [ConfigScope.SYSTEM, ConfigScope.USER, ConfigScope.PROJECT, ConfigScope.LOCAL]
        ):
            if override_key in scopes[scope]:
                result[key] = scopes[scope][override_key]
                override_found = True
                break

        if not override_found:
            # Get defaults for merge keys (e.g., skill_dirs has XDG data dirs)
            default_list = DEFAULTS.get(key) if isinstance(DEFAULTS.get(key), list) else None
            result[key] = _merge_lists(scopes, key, default_list)

    # Apply environment variable overrides (highest priority for scalars)
    for key, env_var in ENV_VARS.items():
        env_value = os.environ.get(env_var)
        if env_value is not None:
            result[key] = env_value

    return result


def get_config_with_origins(
    project_root: Path | None = None,
) -> dict[str, tuple[Any, str]]:
    """
    Get effective config values with their source scope.

    Args:
        project_root: Project root path (auto-detected if None)

    Returns:
        Dict mapping keys to (value, source) tuples.
        Source is one of: "default", "system", "user", "project", "local", "env"
        For merged lists, source shows all contributing scopes.
    """
    if project_root is None:
        project_root = find_project_root()

    # Load all scopes
    scopes = {
        ConfigScope.SYSTEM: get_scope_config(ConfigScope.SYSTEM),
        ConfigScope.USER: get_scope_config(ConfigScope.USER),
        ConfigScope.PROJECT: get_scope_config(ConfigScope.PROJECT, project_root),
        ConfigScope.LOCAL: get_scope_config(ConfigScope.LOCAL, project_root),
    }

    result: dict[str, tuple[Any, str]] = {}

    # Cascade scalars - track which scope provided the value
    for key in SCALAR_KEYS:
        value = DEFAULTS.get(key)
        source = "default"

        for scope in [ConfigScope.SYSTEM, ConfigScope.USER, ConfigScope.PROJECT, ConfigScope.LOCAL]:
            if key in scopes[scope]:
                value = scopes[scope][key]
                source = scope.value

        # Check env override
        env_var = ENV_VARS.get(key)
        if env_var:
            env_value = os.environ.get(env_var)
            if env_value is not None:
                value = env_value
                source = "env"

        result[key] = (value, source)

    # Merge lists - track all contributing scopes
    for key in MERGE_KEYS:
        # Check for override
        override_key = f"{key}!"
        override_found = False
        for scope in reversed(
            [ConfigScope.SYSTEM, ConfigScope.USER, ConfigScope.PROJECT, ConfigScope.LOCAL]
        ):
            if override_key in scopes[scope]:
                result[key] = (scopes[scope][override_key], f"{scope.value} (override)")
                override_found = True
                break

        if not override_found:
            # Get defaults for merge keys (e.g., skill_dirs has XDG data dirs)
            default_list = DEFAULTS.get(key) if isinstance(DEFAULTS.get(key), list) else None
            merged_value = _merge_lists(scopes, key, default_list)
            # Find contributing scopes
            contributing = []
            has_defaults = bool(default_list)
            for scope in [
                ConfigScope.SYSTEM,
                ConfigScope.USER,
                ConfigScope.PROJECT,
                ConfigScope.LOCAL,
            ]:
                if scopes[scope].get(key):
                    contributing.append(scope.value)

            if contributing and has_defaults:
                source = f"merged: default, {', '.join(contributing)}"
            elif contributing:
                source = f"merged: {', '.join(contributing)}"
            else:
                source = "default"
            result[key] = (merged_value, source)

    return result


def get_all_scope_configs(
    project_root: Path | None = None,
) -> dict[ConfigScope, tuple[Path | None, dict[str, Any]]]:
    """
    Get config from all scopes with their file paths.

    Args:
        project_root: Project root path (auto-detected if None)

    Returns:
        Dict mapping scope to (path, config) tuples.
        Path is None if scope not applicable.
    """
    if project_root is None:
        project_root = find_project_root()

    result = {}
    for scope in ConfigScope:
        path = get_scope_config_path(scope, project_root)
        config = get_scope_config(scope, project_root)
        result[scope] = (path, config)

    return result


def save_scope_config(
    scope: ConfigScope,
    config: dict[str, Any],
    project_root: Path | None = None,
) -> Path:
    """
    Save configuration to a specific scope's config file.

    Args:
        scope: The scope to save to
        config: Configuration to save
        project_root: Project root for project/local scopes

    Returns:
        Path to saved config file

    Raises:
        ValueError: If scope is not writable (e.g., project/local without project_root)
        OSError: If unable to write file
    """
    path = get_scope_config_path(scope, project_root)
    if path is None:
        if scope in (ConfigScope.PROJECT, ConfigScope.LOCAL):
            raise ValueError(f"Cannot write {scope.value} config: not in a project directory")
        raise ValueError(f"Cannot determine config path for {scope.value}")

    # Create parent directory
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w") as f:
        json.dump(config, f, indent=2)

    return path


def unset_scope_config_key(
    scope: ConfigScope,
    key: str,
    project_root: Path | None = None,
) -> bool:
    """
    Remove a key from a scope's config file.

    Args:
        scope: The scope to modify
        key: The key to remove
        project_root: Project root for project/local scopes

    Returns:
        True if key was removed, False if key didn't exist

    Raises:
        ValueError: If scope is not writable
        OSError: If unable to write file
    """
    path = get_scope_config_path(scope, project_root)
    if path is None or not path.exists():
        return False

    config = _load_json_file(path)
    if key not in config:
        return False

    del config[key]
    save_scope_config(scope, config, project_root)
    return True
