"""Template-method lifecycle for projecting Modus onto coding-agent hosts.

Concrete adapters declare a :class:`~modus.platforms.models.PlatformLayout`
and render one host-facing instruction index. This base class owns the safety
invariants shared by every host:

* only the canonical public surface is projected;
* every write is deterministic and recorded in the install manifest;
* shared instruction files are merged non-destructively; and
* uninstall removes only assets covered by the adapter's ownership contract.

Compatibility imports in this module intentionally preserve the original
``modus.platforms.base`` helper surface for downstream callers.
"""

from __future__ import annotations

import os
import stat
from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar

from ..legacy_hooks import LEGACY_HOOK_PATHS, clean_legacy_hook_config
from ..manifest import ManagedFile, ManagedSection, Manifest
from ..paths import ModusPaths
from ..surface import (
    CORE_SKILLS,
    EXPLICIT_COMMANDS,
    EXPLICIT_SKILLS,
    MODEL_INVOCABLE_SKILLS,
    command_invocation,
)
from .models import Command, PlatformLayout, Skill, validate_relative_path
from .sections import (
    inject_section,
    remove_section,
    render_section,
    section_block,
    section_markers,
)

__all__ = [
    "Command",
    "PlatformAdapter",
    "Skill",
    "inject_section",
    "is_executable_asset",
    "remove_section",
    "render_section",
    "section_block",
    "section_markers",
]


def is_model_invocable_skill(name: str) -> bool:
    """Return whether a host may select ``name`` without explicit user invocation."""

    return name in MODEL_INVOCABLE_SKILLS


def is_user_invocable_skill(name: str) -> bool:
    """Return whether ``name`` belongs to the explicit public workflow surface."""

    return name in EXPLICIT_SKILLS


def is_executable_asset(relative_path: str) -> bool:
    """Return whether a projected asset must carry executable permission bits."""

    return "/scripts/" in relative_path or relative_path.endswith((".sh", ".cmd"))


def _ensure_executable(path: Path, relative_path: str) -> None:
    if not is_executable_asset(relative_path):
        return
    mode = os.stat(path).st_mode
    path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


class PlatformAdapter(ABC):
    """Project the neutral Modus surface through one host-specific layout.

    Subclasses supply declarative layout data and instruction rendering only.
    The orchestration sequence is deliberately uniform: skills, optional native
    commands, then instructions. New adapters therefore align
    with manifest and uninstall semantics by construction.
    """

    name: ClassVar[str]
    layout: ClassVar[PlatformLayout]

    def project(
        self,
        paths: ModusPaths,
        skills: list[Skill],
        commands: list[Command],
        manifest: Manifest,
    ) -> None:
        """Project the canonical public surface and record every owned artifact."""

        public_skills = self._select_public_skills(skills)
        public_commands = (
            self._select_public_commands(commands) if self.layout.commands_root is not None else []
        )

        self._write_skill_bundles(paths, public_skills, manifest)
        self._write_command_documents(paths, public_commands, manifest)
        self._write_instruction_file(
            paths,
            self._render_instructions(public_skills, public_commands),
            manifest,
        )

    def uninstall(self, paths: ModusPaths, manifest: Manifest) -> None:
        """Remove this platform, retaining sections still used by other platforms."""

        files, sections = self._collect_managed(manifest)
        for file_entry in files:
            target = paths.root / file_entry.path
            if file_entry.is_legacy_hook_config:
                if not clean_legacy_hook_config(target):
                    continue
            elif target.exists():
                target.unlink()
            manifest.files.remove(file_entry)

        for section_entry in sections:
            remove_section(paths.root / section_entry.path, section_entry.marker)
            manifest.sections.remove(section_entry)
        if self.name in manifest.platforms:
            manifest.platforms.remove(self.name)

    @abstractmethod
    def _render_instructions(
        self,
        skills: list[Skill],
        commands: list[Command],
    ) -> str:
        """Render the contents of this host's Modus-owned instruction section."""

        raise NotImplementedError

    def _post_process_skill_md(
        self,
        content: str,
        *,
        model_invocable: bool = True,
        user_invocable: bool = False,
    ) -> str:
        """Apply host-specific metadata to a projected ``SKILL.md`` document."""

        return content

    @staticmethod
    def _select_public_skills(skills: list[Skill]) -> list[Skill]:
        """Select canonical public skills in stable presentation order."""

        by_name = {skill.name: skill for skill in skills}
        return [by_name[name] for name in CORE_SKILLS if name in by_name]

    @staticmethod
    def _select_public_commands(commands: list[Command]) -> list[Command]:
        """Select explicit native commands in stable presentation order."""

        by_name = {command.name: command for command in commands}
        return [by_name[name] for name in EXPLICIT_COMMANDS if name in by_name]

    def _write_skill_bundles(
        self,
        paths: ModusPaths,
        skills: list[Skill],
        manifest: Manifest,
    ) -> None:
        for skill in skills:
            self._write_skill_bundle(paths, skill, manifest)

    def _write_skill_bundle(
        self,
        paths: ModusPaths,
        skill: Skill,
        manifest: Manifest,
    ) -> None:
        """Project a complete skill directory, including deterministic support files."""

        target_root = f"{self.layout.skills_root}/{skill.name}"
        self._write_file(
            paths,
            f"{target_root}/SKILL.md",
            self._post_process_skill_md(
                skill.body,
                model_invocable=is_model_invocable_skill(skill.name),
                user_invocable=is_user_invocable_skill(skill.name),
            ),
            template=f"skills/{skill.name}/SKILL.md",
            manifest=manifest,
        )
        for relative_path, content in sorted(skill.support_files.items()):
            self._write_file(
                paths,
                f"{target_root}/{relative_path}",
                content,
                template=f"skills/{skill.name}/{relative_path}",
                manifest=manifest,
            )

    def _write_command_documents(
        self,
        paths: ModusPaths,
        commands: list[Command],
        manifest: Manifest,
    ) -> None:
        commands_root = self.layout.commands_root
        if commands_root is None:
            return
        for command in commands:
            self._write_file(
                paths,
                f"{commands_root}/{command_invocation(command.name)}.md",
                command.body,
                template=f"commands/{command.name}.md",
                manifest=manifest,
            )

    @staticmethod
    def _write_file(
        paths: ModusPaths,
        relative_path: str,
        content: str,
        template: str,
        manifest: Manifest,
    ) -> None:
        """Write one owned file and register the exact bytes in the manifest."""

        validate_relative_path(relative_path)
        target = paths.root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="")
        _ensure_executable(target, relative_path)
        manifest.add_file(relative_path, content, template)

    def _write_instruction_file(
        self,
        paths: ModusPaths,
        content: str,
        manifest: Manifest,
    ) -> None:
        target_spec = self.layout.instructions
        target = paths.root / target_spec.path
        if target_spec.preamble and (
            not target.exists() or not target.read_text(encoding="utf-8").strip()
        ):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(target_spec.preamble, encoding="utf-8", newline="")
        block = inject_section(target, target_spec.marker, content)
        manifest.add_section(target_spec.path, target_spec.marker, block)

    def _collect_managed(
        self,
        manifest: Manifest,
    ) -> tuple[list[ManagedFile], list[ManagedSection]]:
        """Return the exact manifest entries covered by this adapter's ownership."""

        prefixes = self.layout.owned_file_prefixes
        instructions = self.layout.instructions
        files = [
            entry
            for entry in manifest.files
            if (entry.is_legacy_hook_config and entry.path in LEGACY_HOOK_PATHS.get(self.name, ()))
            or entry.path.startswith(prefixes)
        ]
        sections = [
            entry
            for entry in manifest.sections
            if entry.path == instructions.path and entry.marker == instructions.marker
        ]
        if sections:
            from .registry import get_adapters

            remaining = get_adapters([name for name in manifest.platforms if name != self.name])
            if any(
                (adapter.layout.instructions.path, adapter.layout.instructions.marker)
                == (instructions.path, instructions.marker)
                for adapter in remaining
            ):
                sections = []
        return files, sections

    def preview_uninstall(
        self,
        manifest: Manifest,
    ) -> tuple[list[ManagedFile], list[ManagedSection]]:
        """Return the same ownership set as :meth:`uninstall` without filesystem I/O."""

        return self._collect_managed(manifest)
