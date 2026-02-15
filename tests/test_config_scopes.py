"""Tests for config_scopes module."""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from skilz.config_scopes import (
    ConfigScope,
    MERGE_KEYS,
    SCALAR_KEYS,
    _load_json_file,
    _merge_lists,
    find_project_root,
    get_all_scope_configs,
    get_config_with_origins,
    get_scope_config,
    get_scope_config_path,
    resolve_config,
    save_scope_config,
    unset_scope_config_key,
)


class TestFindProjectRoot:
    """Tests for find_project_root function."""

    def test_finds_skilz_directory(self, tmp_path: Path) -> None:
        """Should find project root when .skilz directory exists."""
        project = tmp_path / "myproject"
        project.mkdir()
        (project / ".skilz").mkdir()
        subdir = project / "src" / "deep"
        subdir.mkdir(parents=True)

        result = find_project_root(subdir)
        assert result == project

    def test_finds_git_directory(self, tmp_path: Path) -> None:
        """Should find project root when .git directory exists."""
        project = tmp_path / "myproject"
        project.mkdir()
        (project / ".git").mkdir()
        subdir = project / "src"
        subdir.mkdir()

        result = find_project_root(subdir)
        assert result == project

    def test_skilz_takes_precedence_over_git(self, tmp_path: Path) -> None:
        """Should prefer .skilz over .git at same level."""
        project = tmp_path / "myproject"
        project.mkdir()
        (project / ".skilz").mkdir()
        (project / ".git").mkdir()

        result = find_project_root(project)
        assert result == project

    def test_returns_none_when_not_found(self, tmp_path: Path) -> None:
        """Should return None when no project markers found."""
        result = find_project_root(tmp_path)
        assert result is None

    def test_uses_cwd_when_no_start(self) -> None:
        """Should use current directory when start is None."""
        # This test just ensures the function doesn't crash
        result = find_project_root()
        # Result depends on actual cwd, so just check type
        assert result is None or isinstance(result, Path)


class TestLoadJsonFile:
    """Tests for _load_json_file helper."""

    def test_loads_valid_json(self, tmp_path: Path) -> None:
        """Should load valid JSON file."""
        path = tmp_path / "config.json"
        path.write_text('{"key": "value"}')

        result = _load_json_file(path)
        assert result == {"key": "value"}

    def test_returns_empty_for_missing_file(self, tmp_path: Path) -> None:
        """Should return empty dict for missing file."""
        path = tmp_path / "missing.json"

        result = _load_json_file(path)
        assert result == {}

    def test_returns_empty_for_invalid_json(self, tmp_path: Path) -> None:
        """Should return empty dict for invalid JSON."""
        path = tmp_path / "invalid.json"
        path.write_text("not valid json {")

        result = _load_json_file(path)
        assert result == {}

    def test_returns_empty_for_non_dict_json(self, tmp_path: Path) -> None:
        """Should return empty dict when JSON is not an object."""
        path = tmp_path / "array.json"
        path.write_text('["a", "b"]')

        result = _load_json_file(path)
        assert result == {}


class TestGetScopeConfigPath:
    """Tests for get_scope_config_path function."""

    def test_system_scope(self) -> None:
        """Should return system config path."""
        path = get_scope_config_path(ConfigScope.SYSTEM)
        assert path is not None
        assert "skilz" in str(path)
        assert path.name == "config.json"

    def test_user_scope(self) -> None:
        """Should return user config path."""
        path = get_scope_config_path(ConfigScope.USER)
        assert path is not None
        assert "skilz" in str(path)
        assert path.name == "settings.json"

    def test_project_scope_with_root(self, tmp_path: Path) -> None:
        """Should return project config path when root provided."""
        path = get_scope_config_path(ConfigScope.PROJECT, tmp_path)
        assert path == tmp_path / ".skilz" / "config.json"

    def test_project_scope_without_root(self) -> None:
        """Should return None for project scope without root."""
        path = get_scope_config_path(ConfigScope.PROJECT, None)
        assert path is None

    def test_local_scope_with_root(self, tmp_path: Path) -> None:
        """Should return local config path when root provided."""
        path = get_scope_config_path(ConfigScope.LOCAL, tmp_path)
        assert path == tmp_path / ".skilz" / "local.json"


class TestGetScopeConfig:
    """Tests for get_scope_config function."""

    def test_loads_user_config(self, tmp_path: Path) -> None:
        """Should load user config from XDG_CONFIG_HOME."""
        config_dir = tmp_path / "config" / "skilz"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "settings.json"
        config_file.write_text('{"agent_default": "claude"}')

        with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(tmp_path / "config")}):
            # Need to reimport to pick up patched env
            from skilz import config_scopes
            result = config_scopes.get_scope_config(ConfigScope.USER)
            assert result.get("agent_default") == "claude"

    def test_loads_project_config(self, tmp_path: Path) -> None:
        """Should load project config from .skilz directory."""
        skilz_dir = tmp_path / ".skilz"
        skilz_dir.mkdir()
        config_file = skilz_dir / "config.json"
        config_file.write_text('{"agent_default": "gemini"}')

        result = get_scope_config(ConfigScope.PROJECT, tmp_path)
        assert result == {"agent_default": "gemini"}

    def test_loads_local_config(self, tmp_path: Path) -> None:
        """Should load local config from .skilz directory."""
        skilz_dir = tmp_path / ".skilz"
        skilz_dir.mkdir()
        config_file = skilz_dir / "local.json"
        config_file.write_text('{"agent_default": "cursor"}')

        result = get_scope_config(ConfigScope.LOCAL, tmp_path)
        assert result == {"agent_default": "cursor"}

    def test_returns_empty_for_missing_config(self, tmp_path: Path) -> None:
        """Should return empty dict when config doesn't exist."""
        result = get_scope_config(ConfigScope.PROJECT, tmp_path)
        assert result == {}


class TestMergeLists:
    """Tests for _merge_lists function."""

    def test_merges_from_multiple_scopes(self) -> None:
        """Should combine lists from all scopes."""
        scopes = {
            ConfigScope.SYSTEM: {"skill_dirs": ["/system/skills"]},
            ConfigScope.USER: {"skill_dirs": ["/user/skills"]},
            ConfigScope.PROJECT: {"skill_dirs": ["./project/skills"]},
            ConfigScope.LOCAL: {"skill_dirs": ["./local/skills"]},
        }

        result = _merge_lists(scopes, "skill_dirs")
        assert result == [
            "/system/skills",
            "/user/skills",
            "./project/skills",
            "./local/skills",
        ]

    def test_removes_with_dash_prefix(self) -> None:
        """Should remove items with - prefix."""
        scopes = {
            ConfigScope.SYSTEM: {"skill_dirs": ["/system/skills", "/unwanted"]},
            ConfigScope.USER: {"skill_dirs": ["-/unwanted"]},
            ConfigScope.PROJECT: {},
            ConfigScope.LOCAL: {},
        }

        result = _merge_lists(scopes, "skill_dirs")
        assert result == ["/system/skills"]

    def test_deduplicates(self) -> None:
        """Should not add duplicates."""
        scopes = {
            ConfigScope.SYSTEM: {"skill_dirs": ["/shared"]},
            ConfigScope.USER: {"skill_dirs": ["/shared"]},
            ConfigScope.PROJECT: {},
            ConfigScope.LOCAL: {},
        }

        result = _merge_lists(scopes, "skill_dirs")
        assert result == ["/shared"]

    def test_handles_missing_key(self) -> None:
        """Should return empty list when key missing from all scopes."""
        scopes = {
            ConfigScope.SYSTEM: {},
            ConfigScope.USER: {},
            ConfigScope.PROJECT: {},
            ConfigScope.LOCAL: {},
        }

        result = _merge_lists(scopes, "skill_dirs")
        assert result == []


class TestResolveConfig:
    """Tests for resolve_config function."""

    def test_scalar_cascade(self, tmp_path: Path) -> None:
        """Should cascade scalars with most specific winning."""
        skilz_dir = tmp_path / ".skilz"
        skilz_dir.mkdir()

        # User config
        user_dir = tmp_path / "config" / "skilz"
        user_dir.mkdir(parents=True)
        (user_dir / "settings.json").write_text('{"agent_default": "claude"}')

        # Project config (should win)
        (skilz_dir / "config.json").write_text('{"agent_default": "gemini"}')

        with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(tmp_path / "config")}):
            result = resolve_config(tmp_path)
            assert result["agent_default"] == "gemini"

    def test_env_var_overrides_all(self, tmp_path: Path) -> None:
        """Should apply env var overrides over all scopes."""
        skilz_dir = tmp_path / ".skilz"
        skilz_dir.mkdir()
        (skilz_dir / "config.json").write_text('{"agent_default": "gemini"}')

        with patch.dict(os.environ, {"AGENT_DEFAULT": "cursor"}):
            result = resolve_config(tmp_path)
            assert result["agent_default"] == "cursor"

    def test_list_merge(self, tmp_path: Path) -> None:
        """Should merge list keys from all scopes."""
        skilz_dir = tmp_path / ".skilz"
        skilz_dir.mkdir()

        user_dir = tmp_path / "config" / "skilz"
        user_dir.mkdir(parents=True)
        (user_dir / "settings.json").write_text('{"skill_dirs": ["/user/skills"]}')
        (skilz_dir / "config.json").write_text('{"skill_dirs": ["./project/skills"]}')

        with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(tmp_path / "config")}):
            result = resolve_config(tmp_path)
            assert "/user/skills" in result["skill_dirs"]
            assert "./project/skills" in result["skill_dirs"]

    def test_list_override_with_bang(self, tmp_path: Path) -> None:
        """Should replace list entirely when using key! syntax."""
        skilz_dir = tmp_path / ".skilz"
        skilz_dir.mkdir()

        user_dir = tmp_path / "config" / "skilz"
        user_dir.mkdir(parents=True)
        (user_dir / "settings.json").write_text('{"skill_dirs": ["/user/skills"]}')
        (skilz_dir / "config.json").write_text('{"skill_dirs!": ["./only/this"]}')

        with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(tmp_path / "config")}):
            result = resolve_config(tmp_path)
            assert result["skill_dirs"] == ["./only/this"]


class TestGetConfigWithOrigins:
    """Tests for get_config_with_origins function."""

    def test_shows_default_origin(self, tmp_path: Path) -> None:
        """Should show 'default' for values from defaults."""
        result = get_config_with_origins(tmp_path)
        value, origin = result["claude_code_home"]
        assert origin == "default"

    def test_shows_user_origin(self, tmp_path: Path) -> None:
        """Should show 'user' for values from user config."""
        user_dir = tmp_path / "config" / "skilz"
        user_dir.mkdir(parents=True)
        (user_dir / "settings.json").write_text('{"agent_default": "claude"}')

        with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(tmp_path / "config")}):
            result = get_config_with_origins(tmp_path)
            value, origin = result["agent_default"]
            assert value == "claude"
            assert origin == "user"

    def test_shows_merged_origin(self, tmp_path: Path) -> None:
        """Should show merged scopes for list values."""
        skilz_dir = tmp_path / ".skilz"
        skilz_dir.mkdir()

        user_dir = tmp_path / "config" / "skilz"
        user_dir.mkdir(parents=True)
        (user_dir / "settings.json").write_text('{"skill_dirs": ["/a"]}')
        (skilz_dir / "config.json").write_text('{"skill_dirs": ["/b"]}')

        with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(tmp_path / "config")}):
            result = get_config_with_origins(tmp_path)
            value, origin = result["skill_dirs"]
            assert "merged" in origin
            assert "user" in origin
            assert "project" in origin


class TestSaveScopeConfig:
    """Tests for save_scope_config function."""

    def test_saves_to_project(self, tmp_path: Path) -> None:
        """Should save config to .skilz/config.json."""
        config = {"agent_default": "gemini"}
        path = save_scope_config(ConfigScope.PROJECT, config, tmp_path)

        assert path == tmp_path / ".skilz" / "config.json"
        assert path.exists()
        assert json.loads(path.read_text()) == config

    def test_saves_to_local(self, tmp_path: Path) -> None:
        """Should save config to .skilz/local.json."""
        config = {"agent_default": "cursor"}
        path = save_scope_config(ConfigScope.LOCAL, config, tmp_path)

        assert path == tmp_path / ".skilz" / "local.json"
        assert path.exists()

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        """Should create .skilz directory if needed."""
        config = {"key": "value"}
        path = save_scope_config(ConfigScope.PROJECT, config, tmp_path)

        assert (tmp_path / ".skilz").is_dir()
        assert path.exists()

    def test_raises_for_project_without_root(self) -> None:
        """Should raise ValueError for project scope without root."""
        with pytest.raises(ValueError, match="not in a project"):
            save_scope_config(ConfigScope.PROJECT, {}, None)


class TestUnsetScopeConfigKey:
    """Tests for unset_scope_config_key function."""

    def test_removes_existing_key(self, tmp_path: Path) -> None:
        """Should remove key and return True."""
        skilz_dir = tmp_path / ".skilz"
        skilz_dir.mkdir()
        config_file = skilz_dir / "config.json"
        config_file.write_text('{"agent_default": "gemini", "other": "value"}')

        result = unset_scope_config_key(ConfigScope.PROJECT, "agent_default", tmp_path)

        assert result is True
        saved = json.loads(config_file.read_text())
        assert "agent_default" not in saved
        assert saved["other"] == "value"

    def test_returns_false_for_missing_key(self, tmp_path: Path) -> None:
        """Should return False if key doesn't exist."""
        skilz_dir = tmp_path / ".skilz"
        skilz_dir.mkdir()
        (skilz_dir / "config.json").write_text('{"other": "value"}')

        result = unset_scope_config_key(ConfigScope.PROJECT, "agent_default", tmp_path)
        assert result is False

    def test_returns_false_for_missing_file(self, tmp_path: Path) -> None:
        """Should return False if config file doesn't exist."""
        result = unset_scope_config_key(ConfigScope.PROJECT, "agent_default", tmp_path)
        assert result is False


class TestXDGCompliance:
    """Tests for XDG Base Directory compliance."""

    def test_honors_xdg_config_home(self, tmp_path: Path) -> None:
        """Should use XDG_CONFIG_HOME when set."""
        custom_config = tmp_path / "custom_config"
        custom_config.mkdir()
        (custom_config / "skilz").mkdir()
        (custom_config / "skilz" / "settings.json").write_text('{"agent_default": "test"}')

        with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(custom_config)}):
            from skilz.config_scopes import get_scope_config
            config = get_scope_config(ConfigScope.USER)
            assert config.get("agent_default") == "test"

    def test_honors_xdg_config_dirs(self, tmp_path: Path) -> None:
        """Should search XDG_CONFIG_DIRS for system config."""
        # Create system config in custom location
        sys_config = tmp_path / "etc" / "skilz"
        sys_config.mkdir(parents=True)
        (sys_config / "config.json").write_text('{"agent_default": "system"}')

        with patch.dict(os.environ, {"XDG_CONFIG_DIRS": str(tmp_path / "etc")}):
            from skilz.config_scopes import get_scope_config
            config = get_scope_config(ConfigScope.SYSTEM)
            assert config.get("agent_default") == "system"
