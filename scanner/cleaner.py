import os
import shutil
import ctypes
import subprocess
from ctypes import wintypes
from typing import List, Dict, Any
from .engine import format_bytes


# Windows Shell32 SHFileOperationW structures for Recycle Bin support without external dependencies
class SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("wFunc", wintypes.UINT),
        ("pFrom", wintypes.LPCWSTR),
        ("pTo", wintypes.LPCWSTR),
        ("fFlags", wintypes.WORD),
        ("fAnyOperationsAborted", wintypes.BOOL),
        ("hNameMappings", wintypes.LPVOID),
        ("lpszProgressTitle", wintypes.LPCWSTR),
    ]


FO_DELETE = 0x0003
FOF_ALLOWUNDO = 0x0040
FOF_NOCONFIRMATION = 0x0010
FOF_NOERRORUI = 0x0400
FOF_SILENT = 0x0004


def send_path_to_recycle_bin_win32(target_path: str) -> bool:
    """Sends a file or directory to the Windows Recycle Bin using native Shell32 API."""
    norm_path = os.path.abspath(target_path)
    if not os.path.exists(norm_path):
        return False

    # Try send2trash first if installed
    try:
        import send2trash  # type: ignore
        send2trash.send2trash(norm_path)
        return True
    except ImportError:
        pass

    # Native ctypes fallback via SHFileOperationW (requires double-null terminated string)
    p_from = norm_path + "\0\0"
    file_op = SHFILEOPSTRUCTW()
    file_op.hwnd = None
    file_op.wFunc = FO_DELETE
    file_op.pFrom = p_from
    file_op.pTo = None
    file_op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_NOERRORUI | FOF_SILENT
    file_op.fAnyOperationsAborted = False
    file_op.hNameMappings = None
    file_op.lpszProgressTitle = None

    res = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(file_op))
    return res == 0 and not file_op.fAnyOperationsAborted


def delete_path_permanently(target_path: str) -> bool:
    norm_path = os.path.abspath(target_path)
    if not os.path.exists(norm_path):
        return False
    if os.path.isdir(norm_path) and not os.path.islink(norm_path):
        shutil.rmtree(norm_path)
    else:
        os.remove(norm_path)
    return True


def is_critical_system_root(target_path: str) -> bool:
    norm = os.path.normcase(os.path.abspath(target_path)).rstrip("\\/")
    # Never allow deleting drive roots or user profile root
    if len(norm) <= 3:  # e.g., c: or e:
        return True
    forbidden = {
        os.path.normcase(os.path.expandvars("%USERPROFILE%")),
        os.path.normcase(os.path.expandvars("%WINDIR%")),
        os.path.normcase(os.path.expandvars("%APPDATA%")),
        os.path.normcase(os.path.expandvars("%LOCALAPPDATA%")),
        os.path.normcase(os.path.expandvars("%USERPROFILE%\\.cache")),
        os.path.normcase(os.path.expandvars("%USERPROFILE%\\.gemini")),
        os.path.normcase(os.path.expandvars("%USERPROFILE%\\.gemini\\antigravity")),
        os.path.normcase(os.path.expandvars("%USERPROFILE%\\.hermes")),
        os.path.normcase(os.path.expandvars("%USERPROFILE%\\.codex")),
        os.path.normcase(os.path.expandvars("%USERPROFILE%\\.claude")),
        os.path.normcase(os.path.expandvars("%USERPROFILE%\\.cursor")),
        os.path.normcase(os.path.expandvars("%APPDATA%\\Hermes")),
        os.path.normcase(os.path.expandvars("%APPDATA%\\Antigravity")),
        os.path.normcase(os.path.expandvars("%APPDATA%\\Claude")),
        os.path.normcase(os.path.expandvars("%APPDATA%\\Cursor")),
        os.path.normcase("e:\\ia-ai"),
        os.path.normcase("e:\\ia-ai\\.hermes.md"),
    }
    if norm in forbidden:
        return True

    # Never allow deleting skills, agent memories, rules, prompts, git repos, MCP configs, or ComfyUI workflows/custom_nodes
    parts = [p for p in norm.replace("/", "\\").split("\\") if p]
    protected_segments = {
        ".git", "skills", "skill", "commands", "memory", "memories", "knowledge",
        "rules", "rule", "prompts", "prompt", "instructions", "agents", "subagents",
        "personas", "profiles", "mcp", "plugins", "plugin", "plugin_data",
        "extensions", "custom_nodes", "builtin", "workflows", "clases", "docs",
        "config", "configs", "settings", "auth", "credentials"
    }
    if any(seg in protected_segments for seg in parts):
        return True

    protected_base_files = {
        ".hermes.md", "skill.md", "claude.md", "gemini.md", "agents.md",
        "instructions.md", ".cursorrules", ".windsurfrules", ".clinerules",
        "mcp_config.json", "claude_desktop_config.json", "mcp.json",
        "config.toml", "auth.json", "active-profile.json", "connections.json",
        "secure-token-storage.json"
    }
    base = os.path.basename(norm)
    if base in protected_base_files or base.endswith(".mdc"):
        return True

    # First-level directory content check: never delete a directory that contains protected subdirs/files inside
    abs_target = os.path.abspath(target_path)
    if os.path.isdir(abs_target) and not os.path.islink(abs_target):
        protected_child_dirs = {
            ".git", "skills", "skill", "memory", "memories", "workflows",
            "commands", "custom_nodes", "mcp", "knowledge", "builtin"
        }
        protected_child_files = {
            ".hermes.md", "claude.md", "agents.md", "skill.md", "gemini.md",
            "instructions.md", ".cursorrules", "mcp_config.json", "claude_desktop_config.json"
        }
        try:
            with os.scandir(abs_target) as it:
                for entry in it:
                    low_e = entry.name.lower()
                    if entry.is_dir(follow_symlinks=False) and low_e in protected_child_dirs:
                        return True
                    if entry.is_file(follow_symlinks=False) and (low_e in protected_child_files or low_e.endswith(".mdc")):
                        return True
        except (PermissionError, OSError):
            pass

    return False


def execute_clean(items: List[Dict[str, Any]], mode: str = "recycle", dry_run: bool = False) -> Dict[str, Any]:
    """
    mode: 'recycle' (Papelera de Windows) or 'permanent' (Borrado directo)
    dry_run: if True, only simulates and returns summary
    """
    results = []
    freed_bytes = 0
    errors = []

    for item in items:
        path = item.get("path", "")
        size = int(item.get("size_bytes", 0))
        safety = item.get("safety", "yellow")

        if safety == "red" or is_critical_system_root(path):
            errors.append({
                "path": path,
                "reason": "PROTEGIDO (Semáforo Rojo / Archivo Crítico bloqueado por seguridad)",
            })
            continue

        if not os.path.exists(path):
            errors.append({"path": path, "reason": "El archivo o carpeta ya no existe en disco"})
            continue

        if dry_run:
            freed_bytes += size
            results.append({
                "path": path,
                "size_bytes": size,
                "size_human": format_bytes(size),
                "action": "DRY_RUN_OK",
            })
            continue

        try:
            ok = False
            if mode == "permanent":
                ok = delete_path_permanently(path)
            else:
                ok = send_path_to_recycle_bin_win32(path)

            if ok:
                freed_bytes += size
                results.append({
                    "path": path,
                    "size_bytes": size,
                    "size_human": format_bytes(size),
                    "action": "RECYCLED" if mode != "permanent" else "DELETED_PERMANENTLY",
                })
            else:
                errors.append({"path": path, "reason": "No se pudo completar la operación (en uso o permisos)"})
        except Exception as exc:
            errors.append({"path": path, "reason": str(exc)})

    return {
        "dry_run": dry_run,
        "mode": mode,
        "cleaned_count": len(results),
        "freed_bytes": freed_bytes,
        "freed_human": format_bytes(freed_bytes),
        "results": results,
        "errors": errors,
    }


def reveal_in_explorer(target_path: str) -> bool:
    norm = os.path.abspath(target_path)
    if not os.path.exists(norm):
        return False
    try:
        subprocess.Popen(["explorer.exe", f"/select,{norm}"])
        return True
    except Exception:
        return False
