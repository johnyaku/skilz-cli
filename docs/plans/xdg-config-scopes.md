# Implementation Plan: XDG-Compliant Multi-Scope Configuration

## Overview

Implement a four-tier configuration system following XDG Base Directory Specification:
- **System**: `/etc/xdg/skilz/` (or `$XDG_CONFIG_DIRS`)
- **User**: `~/.config/skilz/` (or `$XDG_CONFIG_HOME`)
- **Project**: `.skilz/config.json` (git-tracked)
- **Local**: `.skilz/local.json` (git-ignored)

This enables shared skill configurations in HPC/enterprise environments while preserving individual customization.

## Motivation

1. **Multi-user platforms**: HPC environments need system-wide defaults
2. **Team collaboration**: Projects can define shared skill sets
3. **Personal experimentation**: Local overrides for testing without affecting team
4. **XDG compliance**: Honor standard environment variables (`XDG_CONFIG_HOME`, `XDG_CONFIG_DIRS`)

## Current State

Config lives in `~/.config/skilz/`:
- `settings.json` - Main config (`claude_code_home`, `open_code_home`, `agent_default`)
- `config.json` - Agent registry customizations

**Limitation**: Hardcoded `Path.home() / ".config" / "skilz"` ignores `XDG_CONFIG_HOME`.

## Design Decisions

### D1: Configuration Scope Hierarchy

| Scope | Location | Git-tracked | Use Case |
|-------|----------|-------------|----------|
| System | `$XDG_CONFIG_DIRS/skilz/config.json` | N/A | Enterprise/HPC defaults |
| User | `$XDG_CONFIG_HOME/skilz/settings.json` | No | Personal preferences |
| Project | `.skilz/config.json` | Yes | Team standards |
| Local | `.skilz/local.json` | No | Personal project overrides |

**Defaults:**
- `XDG_CONFIG_HOME` → `~/.config`
- `XDG_CONFIG_DIRS` → `/etc/xdg` (colon-separated, first match wins)

### D2: Merge Strategy (Hybrid)

Different config settings use different merge strategies:

| Config Key | Type | Strategy | Rationale |
|------------|------|----------|-----------|
| `agent_default` | scalar | cascade | Only one agent can be default |
| `claude_code_home` | scalar | cascade | Single path value |
| `open_code_home` | scalar | cascade | Single path value |
| `skill_dirs` | list | merge | Cumulative skill sources |
| `disabled_skills` | list | merge | Accumulate exclusions |
| `default_install_mode` | scalar | cascade | Single mode applies |

**Cascade**: Most specific wins (local > project > user > system)
**Merge**: All scopes combined, with optional `-prefix` to exclude

### D3: Collection Merge Syntax

For merged lists, support explicit removal:
```json
{
  "skill_dirs": [
    "/my/skills",
    "-/unwanted/parent/skills"
  ]
}
```

Prefix `-` removes that entry from the merged result.

For complete override (ignore parent scopes):
```json
{
  "skill_dirs!": ["/only/these"]
}
```

Suffix `!` on key name means "replace entirely, don't merge".

### D4: Project Directory Detection

Detect project root by walking up from `cwd` looking for:
1. `.skilz/` directory
2. `.git/` directory (fallback)

Cache result per process to avoid repeated filesystem walks.

### D5: Config File Format

All scopes use JSON format for consistency with existing `settings.json`.

```json
{
  "agent_default": "claude",
  "skill_dirs": ["~/.config/skilz/skills"],
  "disabled_skills": []
}
```

### D6: Backwards Compatibility

- Existing `~/.config/skilz/settings.json` continues to work unchanged
- New scopes are additive; users who don't create system/project/local configs see no difference
- Environment variables (`CLAUDE_CODE_HOME`, etc.) remain highest priority for scalars

## File Structure

### New/Modified Files

| File | Change |
|------|--------|
| `src/skilz/config.py` | Add `ConfigScope` enum, `get_scoped_config()`, `resolve_config()` |
| `src/skilz/config_scopes.py` | NEW: Scope resolution, path detection, merge logic |
| `tests/test_config_scopes.py` | NEW: Tests for multi-scope resolution |
| `docs/USER_MANUAL.md` | Update Configuration section |

### Project Config Location

```
project/
├── .skilz/
│   ├── config.json      # git-tracked team config
│   ├── local.json       # git-ignored personal overrides
│   └── skills/          # optional local skill storage
├── .gitignore           # should include .skilz/local.json
```

## Implementation

Implementation details moved to source code. See:
- [src/skilz/config.py](../../src/skilz/config.py) - XDG functions
- [src/skilz/config_scopes.py](../../src/skilz/config_scopes.py) - Scope resolution and merge logic
- [src/skilz/commands/config_cmd.py](../../src/skilz/commands/config_cmd.py) - CLI handlers
- [tests/test_config_scopes.py](../../tests/test_config_scopes.py) - 38 tests

### Phase 5: CLI Enhancements

#### CLI Pattern Research

The XDG spec defines file locations, not CLI patterns. The de facto standard is established by git and dvc:

| Tool | Scope Flags | Show Origin |
|------|-------------|-------------|
| `git config` | `--system`, `--global`, `--local` | `--show-origin` |
| `dvc config` | `--system`, `--global`, `--project`, `--local` | `--show-origin` |

We follow this pattern for consistency.

#### Scope Flag Names

| Our Scope | Flag | Alias | Rationale |
|-----------|------|-------|-----------|
| system | `--system` | — | Matches git/dvc |
| user | `--global` | `--user` | `--global` matches git/dvc; `--user` matches XDG terminology |
| project | `--project` | — | Matches dvc |
| local | `--local` | — | Matches git/dvc |

#### New CLI Commands

```bash
# Show all config (enhanced from current)
skilz config                         # Current behavior (backwards compatible)
skilz config --show-origin           # Show effective values with source scope
skilz config --show-origin -v        # Full audit: all values from all scopes
skilz config --files                 # Show config file paths and status

# Get a specific key
skilz config agent_default
skilz config agent_default --show-origin

# Set a key (defaults to user scope, like git)
skilz config agent_default claude
skilz config --global agent_default cursor
skilz config --project agent_default gemini
skilz config --local agent_default aider
skilz config --system agent_default claude  # requires sudo typically

# Init at specific scope
skilz config --init                  # Current behavior (user scope)
skilz config --init --project        # Creates .skilz/config.json
skilz config --init --local          # Creates .skilz/local.json

# Unset a key
skilz config --unset agent_default
skilz config --unset --local agent_default

# List specific scope only
skilz config --list --system
skilz config --list --local
```

#### `--show-origin` Output Format

By default, `--show-origin` shows **only effective values** with their source:

```
$ skilz config --show-origin
agent_default     = gemini             (project)
claude_code_home  = ~/.claude          (user)
open_code_home    = ~/.config/opencode (default)
skill_dirs        = /opt/shared-skills, ~/.config/skilz/skills  (merged: system, user)
```

For merged values, shows all contributing scopes.

#### `--files` Output Format

Use `--files` to show config file locations and their status:

```
$ skilz config --files
system:  /etc/xdg/skilz/config.json       (found)
user:    ~/.config/skilz/settings.json    (found)
project: .skilz/config.json               (not found)
local:   .skilz/local.json                (not found)
```

#### Verbose Mode (`-v` / `--verbose`)

Combine with `--show-origin` to show all values from all scopes (full audit):

```
$ skilz config --show-origin -v
system:  /etc/xdg/skilz/config.json
         skill_dirs = /opt/shared-skills

user:    ~/.config/skilz/settings.json
         agent_default = claude
         claude_code_home = ~/.claude

project: .skilz/config.json
         agent_default = gemini

local:   .skilz/local.json (not found)

effective:
  agent_default     = gemini             (project)
  claude_code_home  = ~/.claude          (user)
  skill_dirs        = /opt/shared-skills, ~/.config/skilz/skills  (merged: system, user)
```

## Testing Strategy

### Unit Tests

1. **XDG variable handling**: Mock `XDG_CONFIG_HOME`, `XDG_CONFIG_DIRS`
2. **Project root detection**: Various directory structures
3. **Cascade resolution**: Verify most-specific wins
4. **Merge resolution**: Verify all scopes combined
5. **Removal syntax**: Test `-prefix` exclusion
6. **Override syntax**: Test `key!` replacement
7. **Backwards compatibility**: Existing configs work unchanged

### Integration Tests

1. System + user config interaction
2. Project + local config interaction
3. Full four-tier resolution
4. Environment variable override

## Migration Notes

- No breaking changes; feature is purely additive
- Existing users see no difference unless they create new scope configs
- Document `.skilz/local.json` should be added to `.gitignore`
- Existing `skilz config` and `skilz config --init` work unchanged

## Resolved Design Decisions

1. **CLI scope flags**: Use `--system`, `--global`/`--user`, `--project`, `--local` matching git/dvc pattern
2. **Show origin**: Implement `--show-origin` flag showing source of each value
3. **Get/set syntax**: `skilz config key` to get, `skilz config key value` to set (git-style)

## Open Questions

1. **Config validation across scopes?**
   - Warn if local sets a value that shadows project?
   - Recommendation: No, keep it simple; users know what they're doing

## Implementation Order

1. ✅ Honor `XDG_CONFIG_HOME` for user config (minimal, safe)
2. ✅ Add `get_xdg_config_dirs()` for system scope
3. ✅ Add project root detection
4. ✅ Add project/local scope loading
5. ✅ Implement merge/cascade logic in new `config_scopes.py`
6. ✅ Add CLI scope flags (`--system`, `--global`, `--project`, `--local`)
7. ✅ Add `--show-origin` display
8. ✅ Add get/set by key (`skilz config key [value]`)
9. ✅ Add `--unset` support
10. ✅ Add tests for all new functionality (38 tests)
11. ✅ Update USER_MANUAL.md documentation

## Install Scopes (Extension)

Following the config scopes pattern, we extended `skilz install` with XDG-compliant installation scopes for team/enterprise sharing.

### Design Decision: Install Scope Hierarchy

| Scope | Flag | Location | Use Case |
|-------|------|----------|----------|
| Agent (default) | (none) | Agent's dir (`~/.claude/skills/`) | Normal installs |
| Project | `-p, --project` | Agent's project dir (`.claude/skills/`) | Project-specific skills |
| User | `--user, --global` | `$XDG_DATA_HOME/skilz/skills/` | User-level shared skills |
| System | `--system` | `$XDG_DATA_DIRS[0]/skilz/skills/` | Team/enterprise shared skills |

**XDG Data Defaults:**
- `XDG_DATA_HOME` → `~/.local/share`
- `XDG_DATA_DIRS` → `/usr/local/share:/usr/share`

### Rationale

1. **Agent installs** (default): Skills go directly to agent's expected location
2. **Scoped installs** (`--system`, `--user`): Skills go to skilz-managed directories, independent of any agent

Scoped installs require `skill_dirs` config to make skills visible to agents:

```bash
# Admin installs to system location
sudo skilz install --system plantuml

# Admin configures skill_dirs so all users see it
sudo skilz config --system skill_dirs '["/usr/local/share/skilz/skills"]'
```

### Implementation

| File | Change |
|------|--------|
| `src/skilz/config.py` | Added `get_xdg_data_home()`, `get_xdg_data_dirs()` |
| `src/skilz/config_scopes.py` | Added `InstallScope` enum, `get_install_scope_path()` |
| `src/skilz/cli.py` | Added `--system`, `--user/--global` flags to install command |
| `src/skilz/installer.py` | Added `install_scope` parameter, scope-aware installation |
| `src/skilz/git_install.py` | Added `install_scope` pass-through |

### CLI Examples

```bash
# Install to system location (requires sudo)
sudo skilz install --system anthropics_skills/theme-factory

# Install to user skilz directory
skilz install --user anthropics_skills/theme-factory

# Normal agent install (default behavior unchanged)
skilz install anthropics_skills/theme-factory
```

## Status

**Completed**: February 2026

All config scope features implemented and tested. Install scopes extension also implemented.

See branch `feature/xdg-config-scopes`:
- Config scopes: 38 tests
- Install scopes: CLI flags, installer support, documentation
