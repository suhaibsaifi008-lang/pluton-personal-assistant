"""
PLUTON V2 — Filesystem Domain Handler & Security Boundary
Implements canonical filesystem capabilities:
filesystem.list, filesystem.read, filesystem.write, filesystem.create, filesystem.move,
filesystem.copy, filesystem.rename, filesystem.delete, filesystem.search, filesystem.exists, filesystem.metadata.
Enforces workspace boundaries and postcondition mutation verification.
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from app.core.contracts import ExecutionContext, VerificationStrategy
from app.kernel.control_kernel import KERNEL
from app.verification.verification_engine import VERIFICATION_ENGINE

logger = logging.getLogger("pluton.computer.filesystem")


class FilesystemSecurityPolicy:
    """Policy engine enforcing filesystem path boundaries and write/delete protections."""

    def __init__(self, approved_roots: list[Path] | None = None) -> None:
        self.approved_roots: list[Path] = approved_roots or [
            Path.cwd().resolve(),
            Path(tempfile.gettempdir()).resolve(),
            Path(os.path.expanduser("~")).resolve(),
        ]

    def add_approved_root(self, root_path: str | Path) -> None:
        """Add an approved directory root to the policy."""
        p = Path(root_path).resolve()
        if p not in self.approved_roots:
            self.approved_roots.append(p)

    def validate_path(self, path_str: str, allow_system_read: bool = False) -> tuple[bool, Path | None, str | None]:
        """Validate if a path resolves safely within approved directory roots."""
        if not path_str or not path_str.strip():
            return False, None, "EMPTY_PATH: Path cannot be empty."

        try:
            resolved = Path(path_str).resolve()
        except Exception as e:
            return False, None, f"INVALID_PATH: Could not resolve path '{path_str}': {e}"

        if allow_system_read:
            return True, resolved, None

        for root in self.approved_roots:
            try:
                if resolved == root or root in resolved.parents or resolved.is_relative_to(root):
                    return True, resolved, None
            except AttributeError:
                if str(resolved).startswith(str(root)):
                    return True, resolved, None

        return False, resolved, f"PATH_POLICY_DENIED: Path '{resolved}' escapes approved workspace boundaries."


class FilesystemDomainHandler:
    """Canonical handler for verified file and directory operations with workspace boundary enforcement."""

    def __init__(self, policy: FilesystemSecurityPolicy | None = None) -> None:
        self.policy = policy or FilesystemSecurityPolicy()

    def list(self, path: str = ".", context: ExecutionContext | None = None) -> dict[str, Any]:
        """List contents of a directory."""
        KERNEL.assert_authorized(context.task_id if context else None)
        valid, resolved, err = self.policy.validate_path(path, allow_system_read=True)
        if not valid or not resolved:
            return {"success": False, "error": err}

        if not resolved.exists() or not resolved.is_dir():
            return {"success": False, "error": f"Directory not found: '{path}'"}

        entries = []
        try:
            for item in resolved.iterdir():
                entries.append({
                    "name": item.name,
                    "path": str(item),
                    "is_dir": item.is_dir(),
                    "size_bytes": item.stat().st_size if item.is_file() else 0,
                })
            return {"success": True, "path": str(resolved), "entries": entries, "count": len(entries)}
        except Exception as e:
            return {"success": False, "error": f"Failed to list directory '{path}': {e}"}

    def exists(self, path: str, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Check if path exists."""
        KERNEL.assert_authorized(context.task_id if context else None)
        valid, resolved, err = self.policy.validate_path(path, allow_system_read=True)
        if not valid or not resolved:
            return {"success": False, "error": err}
        return {"success": True, "path": str(resolved), "exists": resolved.exists(), "is_file": resolved.is_file(), "is_dir": resolved.is_dir()}

    def metadata(self, path: str, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Get file/directory metadata."""
        KERNEL.assert_authorized(context.task_id if context else None)
        valid, resolved, err = self.policy.validate_path(path, allow_system_read=True)
        if not valid or not resolved:
            return {"success": False, "error": err}

        if not resolved.exists():
            return {"success": False, "error": f"Path not found: '{path}'"}

        stat = resolved.stat()
        return {
            "success": True,
            "path": str(resolved),
            "size_bytes": stat.st_size,
            "created_at": stat.st_ctime,
            "modified_at": stat.st_mtime,
            "is_dir": resolved.is_dir(),
            "is_file": resolved.is_file(),
        }

    def create(self, path: str, is_dir: bool = False, content: str = "", context: ExecutionContext | None = None) -> dict[str, Any]:
        """Create a new file or directory."""
        KERNEL.assert_authorized(context.task_id if context else None)
        valid, resolved, err = self.policy.validate_path(path, allow_system_read=False)
        if not valid or not resolved:
            return {"success": False, "error": err}

        try:
            if is_dir:
                resolved.mkdir(parents=True, exist_ok=True)
            else:
                resolved.parent.mkdir(parents=True, exist_ok=True)
                resolved.write_text(content, encoding="utf-8")

            ver = VERIFICATION_ENGINE.verify_action(
                strategy=VerificationStrategy.FILESYSTEM_CHECK,
                target=str(resolved),
                expected_state="present",
            )
            return {"success": ver.verified, "path": str(resolved), "is_dir": is_dir, "verification": ver.__dict__}
        except Exception as e:
            return {"success": False, "error": f"Failed to create '{path}': {e}"}

    def read(self, path: str, context: ExecutionContext | None = None, allow_system_read: bool = False) -> dict[str, Any]:
        """Read content of a file within approved workspace boundaries."""
        KERNEL.assert_authorized(context.task_id if context else None)
        valid, resolved, err = self.policy.validate_path(path, allow_system_read=allow_system_read)
        if not valid or not resolved:
            return {"success": False, "error": err}

        if not resolved.exists() or not resolved.is_file():
            return {"success": False, "error": f"File not found: '{path}'"}

        try:
            content = resolved.read_text(encoding="utf-8", errors="replace")
            return {"success": True, "path": str(resolved), "content": content, "size_bytes": len(content)}
        except Exception as e:
            return {"success": False, "error": f"Failed to read '{path}': {e}"}

    def write(self, path: str, content: str, overwrite: bool = True, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Write content to a file with workspace boundary enforcement and verification."""
        KERNEL.assert_authorized(context.task_id if context else None)
        valid, resolved, err = self.policy.validate_path(path, allow_system_read=False)
        if not valid or not resolved:
            return {"success": False, "error": err}

        if resolved.exists() and not overwrite:
            return {"success": False, "error": f"File already exists: '{path}'"}

        try:
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_text(content, encoding="utf-8")
            ver = VERIFICATION_ENGINE.verify_action(
                strategy=VerificationStrategy.FILESYSTEM_CHECK,
                target=str(resolved),
                expected_state="present",
                metadata={"expected_min_bytes": len(content.encode("utf-8")), "expected_content": content},
            )
            return {"success": ver.verified, "path": str(resolved), "size_bytes": len(content), "verification": ver.__dict__}
        except Exception as e:
            return {"success": False, "error": f"Failed to write '{path}': {e}"}

    def move(self, source: str, destination: str, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Move / rename a file or directory with workspace boundary enforcement."""
        KERNEL.assert_authorized(context.task_id if context else None)
        valid_src, resolved_src, err_src = self.policy.validate_path(source, allow_system_read=False)
        if not valid_src or not resolved_src:
            return {"success": False, "error": err_src}

        valid_dst, resolved_dst, err_dst = self.policy.validate_path(destination, allow_system_read=False)
        if not valid_dst or not resolved_dst:
            return {"success": False, "error": err_dst}

        if not resolved_src.exists():
            return {"success": False, "error": f"Source not found: '{source}'"}

        try:
            resolved_dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(resolved_src), str(resolved_dst))
            ver_dst = VERIFICATION_ENGINE.verify_action(
                strategy=VerificationStrategy.FILESYSTEM_CHECK,
                target=str(resolved_dst),
                expected_state="present",
            )
            return {
                "success": ver_dst.verified and not resolved_src.exists(),
                "source": str(resolved_src),
                "destination": str(resolved_dst),
                "verification": ver_dst.__dict__,
            }
        except Exception as e:
            return {"success": False, "error": f"Failed to move '{source}' to '{destination}': {e}"}

    def rename(self, source: str, new_name: str, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Rename a file or directory in place."""
        KERNEL.assert_authorized(context.task_id if context else None)
        p = Path(source)
        dest = str(p.parent / new_name)
        return self.move(source, dest, context=context)

    def copy(self, source: str, destination: str, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Copy a file or directory."""
        KERNEL.assert_authorized(context.task_id if context else None)
        valid_src, resolved_src, err_src = self.policy.validate_path(source, allow_system_read=False)
        if not valid_src or not resolved_src:
            return {"success": False, "error": err_src}

        valid_dst, resolved_dst, err_dst = self.policy.validate_path(destination, allow_system_read=False)
        if not valid_dst or not resolved_dst:
            return {"success": False, "error": err_dst}

        if not resolved_src.exists():
            return {"success": False, "error": f"Source not found: '{source}'"}

        try:
            resolved_dst.parent.mkdir(parents=True, exist_ok=True)
            if resolved_src.is_dir():
                shutil.copytree(str(resolved_src), str(resolved_dst))
            else:
                shutil.copy2(str(resolved_src), str(resolved_dst))
            ver = VERIFICATION_ENGINE.verify_action(
                strategy=VerificationStrategy.FILESYSTEM_CHECK,
                target=str(resolved_dst),
                expected_state="present",
            )
            return {"success": ver.verified, "source": str(resolved_src), "destination": str(resolved_dst)}
        except Exception as e:
            return {"success": False, "error": f"Failed to copy '{source}' to '{destination}': {e}"}

    def delete(self, path: str, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Delete a file or directory with workspace boundary enforcement."""
        KERNEL.assert_authorized(context.task_id if context else None)
        valid, resolved, err = self.policy.validate_path(path, allow_system_read=False)
        if not valid or not resolved:
            return {"success": False, "error": err}

        if not resolved.exists():
            return {"success": True, "message": f"Path '{path}' does not exist (already absent)."}

        if resolved in self.policy.approved_roots:
            return {"success": False, "error": f"POLICY_DENIED: Cannot delete approved root directory '{resolved}' directly."}

        try:
            if resolved.is_dir():
                shutil.rmtree(str(resolved))
            else:
                resolved.unlink()

            ver = VERIFICATION_ENGINE.verify_action(
                strategy=VerificationStrategy.FILESYSTEM_CHECK,
                target=str(resolved),
                expected_state="absent",
            )
            return {"success": ver.verified, "path": str(resolved), "verification": ver.__dict__}
        except Exception as e:
            return {"success": False, "error": f"Failed to delete '{path}': {e}"}

    def search(self, pattern: str, root: str = ".", context: ExecutionContext | None = None) -> dict[str, Any]:
        """Search files matching glob pattern."""
        KERNEL.assert_authorized(context.task_id if context else None)
        valid, resolved, err = self.policy.validate_path(root, allow_system_read=True)
        if not valid or not resolved:
            return {"success": False, "error": err}

        matches = []
        try:
            for p in resolved.rglob(pattern):
                matches.append(str(p))
                if len(matches) >= 50:
                    break
            return {"success": True, "pattern": pattern, "matches": matches, "count": len(matches)}
        except Exception as e:
            return {"success": False, "error": f"Search failed: {e}"}


FILESYSTEM_DOMAIN = FilesystemDomainHandler()
