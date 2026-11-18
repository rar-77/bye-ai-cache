import os
import json
import time
import ctypes
import fnmatch
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Any, Optional, Tuple


PROTECTED_CONTENT_DIRS = {
    ".git",
    "skills",
    "skill",
    "workflows",
    "memory",
    "memories",
    "commands",
    "mcp",
    "knowledge",
    "custom_nodes",
}

PROTECTED_CONTENT_FILES = {
    ".hermes.md",
    "skill.md",
    "claude.md",
    "gemini.md",
    "agents.md",
    "instructions.md",
    ".cursorrules",
    ".windsurfrules",
    ".clinerules",
    "mcp_config.json",
    "claude_desktop_config.json",
}


def get_fixed_drive_roots() -> List[str]:
    """Quickly lists mounted local/removable Windows drives without stalling on optical/network drives."""
    drives: List[str] = []
    try:
        bitmask = ctypes.windll.kernel32.GetLogicalDrives()
        for idx in range(26):
            if bitmask & (1 << idx):
                letter = chr(ord("A") + idx)
                root = f"{letter}:\\"
                # 2=REMOVABLE, 3=FIXED, 6=RAMDISK (skip 5=CDROM, 4=REMOTE, 0/1=UNKNOWN)
                dtype = ctypes.windll.kernel32.GetDriveTypeW(root)
                if dtype in (2, 3, 6):
                    drives.append(root)
    except Exception:
        for letter in ("C", "D", "E", "F", "G", "H"):
            root = f"{letter}:\\"
            if os.path.isdir(root):
                drives.append(root)
    return drives


def discover_comfyui_roots() -> List[str]:
    """Auto-discovers ComfyUI installations across all mounted Windows drives and user profile."""
    candidates: List[str] = []
    for drv in get_fixed_drive_roots():
        candidates.extend([
            os.path.join(drv, "ComfyUI_windows_portable", "ComfyUI"),
            os.path.join(drv, "ComfyUI_portable", "ComfyUI"),
            os.path.join(drv, "ComfyUI"),
            os.path.join(drv, "AI", "ComfyUI_windows_portable", "ComfyUI"),
            os.path.join(drv, "AI", "ComfyUI"),
        ])

    for user_base in (
        "%USERPROFILE%\\ComfyUI_windows_portable\\ComfyUI",
        "%USERPROFILE%\\ComfyUI",
        "%USERPROFILE%\\Documents\\ComfyUI",
        "%USERPROFILE%\\Desktop\\ComfyUI_windows_portable\\ComfyUI",
        "%LOCALAPPDATA%\\Programs\\ComfyUI",
    ):
        candidates.append(os.path.expandvars(os.path.expanduser(user_base)))

    found: List[str] = []
    seen = set()
    for cand in candidates:
        norm = os.path.normpath(cand)
        key = os.path.normcase(norm)
        if key in seen:
            continue
        if os.path.isdir(norm) and (
            os.path.isdir(os.path.join(norm, "models"))
            or os.path.isfile(os.path.join(norm, "main.py"))
        ):
            seen.add(key)
            found.append(norm)
    return found


def expand_win_path(raw_path: str) -> str:
    cleaned = (raw_path or "").strip().strip('"').strip("'")
    # Handle bare drive letters like "C" or "C:" -> "C:\\"
    if len(cleaned) == 1 and cleaned.isalpha():
        return f"{cleaned.upper()}:\\"
    if len(cleaned) == 2 and cleaned[0].isalpha() and cleaned[1] == ":":
        return f"{cleaned[0].upper()}:\\"
    expanded = os.path.expandvars(os.path.expanduser(cleaned))
    norm = os.path.normpath(expanded)
    if len(norm) == 2 and norm[0].isalpha() and norm[1] == ":":
        return norm + "\\"
    return norm


def get_drive_letter(path_str: str) -> str:
    if len(path_str) >= 2 and path_str[1] == ":":
        return path_str[:2].upper()
    return "OTHER"


def format_bytes(size: int) -> str:
    if size <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    idx = 0
    val = float(size)
    while val >= 1024.0 and idx < len(units) - 1:
        val /= 1024.0
        idx += 1
    if idx <= 1:
        return f"{int(val)} {units[idx]}"
    return f"{val:.2f} {units[idx]}"


class ScannerEngine:
    def __init__(self, rules_path: Optional[str] = None):
        if rules_path is None:
            rules_path = os.path.join(os.path.dirname(__file__), "rules.json")
        self.rules_path = rules_path
        self.rules = self._load_rules()

    def _load_rules(self) -> Dict[str, Any]:
        with open(self.rules_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _fast_dir_stats_checked(
        self, root_path: str, max_depth: int = 10, check_depth: int = 3
    ) -> Tuple[int, int, float, Optional[str]]:
        """Returns (total_bytes, file_count, latest_mtime, protected_reason) using fast os.scandir."""
        total_size = 0
        file_count = 0
        latest_mtime = 0.0
        protected_reason: Optional[str] = None
        stack = [(root_path, 0)]

        while stack:
            current_dir, depth = stack.pop()
            try:
                with os.scandir(current_dir) as it:
                    for entry in it:
                        try:
                            if entry.is_symlink():
                                continue
                            low_name = entry.name.lower()
                            if entry.is_file(follow_symlinks=False):
                                if protected_reason is None and depth < check_depth:
                                    if low_name in PROTECTED_CONTENT_FILES or low_name.endswith(".mdc"):
                                        protected_reason = f"Contiene archivo protegido ({entry.name})"
                                st = entry.stat(follow_symlinks=False)
                                total_size += st.st_size
                                file_count += 1
                                if st.st_mtime > latest_mtime:
                                    latest_mtime = st.st_mtime
                            elif entry.is_dir(follow_symlinks=False):
                                if protected_reason is None and depth < check_depth:
                                    if low_name in PROTECTED_CONTENT_DIRS:
                                        protected_reason = f"Contiene carpeta protegida ({entry.name}/)"
                                if depth < max_depth:
                                    stack.append((entry.path, depth + 1))
                        except (PermissionError, OSError):
                            continue
            except (PermissionError, OSError):
                continue

        return total_size, file_count, latest_mtime, protected_reason

    def _fast_dir_stats(self, root_path: str, max_depth: int = 10) -> Tuple[int, int, float]:
        """Returns (total_bytes, file_count, latest_mtime) using fast os.scandir."""
        sz, fc, mt, _ = self._fast_dir_stats_checked(root_path, max_depth=max_depth)
        return sz, fc, mt

    def _is_protected_name(self, name: str, full_path: str) -> bool:
        low_name = name.lower()
        low_path = full_path.lower().replace("/", "\\")
        path_parts = [p for p in low_path.split("\\") if p]

        protected_dirs = set(d.lower() for d in self.rules.get("protected_dir_names", [
            "skills", "skill", "commands", "memory", "memories", "knowledge", "rules", "rule",
            "prompts", "prompt", "instructions", "agents", "subagents", "personas",
            "profiles", "mcp", "plugins", "plugin", "plugin_data", "extensions",
            "custom_nodes", "builtin", "workflows", "clases", "docs", "config",
            "configs", "settings", "auth", "credentials"
        ]))
        protected_dirs.add(".git")

        if low_name in protected_dirs:
            return True
        if any(part in protected_dirs for part in path_parts):
            return True

        for pat in self.rules.get("protected_patterns", []):
            if fnmatch.fnmatch(low_name, pat.lower()):
                return True

        if any(ag in low_path for ag in ("hermes", ".gemini", "antigravity", ".claude", "claude", ".cursor", "cursor", ".codex", "codex", "windsurf", ".codeium", ".continue", ".aider")):
            if low_name.endswith((".md", ".mdc", ".yaml", ".yml", ".toml", ".ini")):
                return True
            if any(k in low_name for k in ("skill", "command", "memory", "memor", "prompt", "rule", "profile", "config", "setting", "auth", "token", "secret", "mcp")):
                return True

        if "\\workflows\\" in low_path and low_name.endswith(".json"):
            return True
        return False

    def _classify_agent_subfolder(self, entry_path: str, name: str, is_dir: bool, radar_name: str) -> Tuple[str, str]:
        """Smartly classifies subfolders inside an agent directory like Hermes, Codex, Cursor or Claude."""
        low_name = name.lower()
        if self._is_protected_name(name, entry_path):
            return ("red", f"{radar_name} — PROTEGIDO: Skills / Memoria / Config ({name}) 🔒")

        pure_cache_dirs = set(d.lower() for d in self.rules.get("pure_cache_dir_names", [
            "cache", "code cache", "gpucache", "shadercache", "dawngraphitecache",
            "dawnwebgpucache", "cacheddata", "blob_storage",
            "logs", "crashes", "crashpad", "temp", "tmp", "statsig", "__pycache__"
        ]))

        if is_dir and (low_name in pure_cache_dirs or "cache" in low_name or "log" in low_name or "tmp" in low_name or "temp" in low_name):
            return ("green", f"{radar_name} — Caché / Logs Temporales ({name})")

        if not is_dir and os.path.splitext(low_name)[1] in (".log", ".tmp", ".temp", ".dmp", ".incomplete", ".part"):
            return ("green", f"{radar_name} — Log / Temporal Huérfano ({name})")

        return ("yellow", f"{radar_name} — Datos / Sesiones ({name})")

    def _classify_arbitrary_entry(self, entry_path: str, name: str, is_dir: bool) -> Tuple[str, str, str]:
        """Returns (safety, category, kind_description) for an arbitrary folder/file."""
        low_name = name.lower()
        ext = os.path.splitext(low_name)[1]

        if self._is_protected_name(name, entry_path):
            return ("red", "AGENTS", "Archivo Protegido (Skills / Memoria / Workflow / Config) 🔒")

        if is_dir:
            if low_name in ("dxcache", "glcache", "d3dscache"):
                return ("yellow", "DEVCACHE", f"Shaders de Juegos/3D ({name}) — Opcional: se recompilan al abrir juegos")
            if low_name in ("__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "temp", "tmp", "cache", "code cache", "gpucache", "dawngraphitecache", "dawnwebgpucache", "shadercache", "logs", "cacheddata", "crashes", "crashdumps"):
                return ("green", "DEVCACHE", f"Carpeta de caché temporal ({name})")
            if low_name in ("node_modules", ".venv", "venv", "env", "python_embeded", "conda"):
                return ("yellow", "DEVCACHE", f"Entorno / Dependencias ({name})")
            if low_name in ("models", "modelos", "checkpoints", "loras", "unet", "diffusion_models", "controlnet", "text_encoders", "clip", "vae"):
                return ("yellow", "MODELS", f"Carpeta de Modelos IA ({name})")
            if low_name in ("outputs", "output", "input"):
                return ("yellow", "COMFYUI", f"Carpeta de Media / Outputs ({name})")
            if low_name in ("workflows", "clases", "docs"):
                return ("red", "COMFYUI", f"Carpeta de Trabajo Protegida ({name})")
            if any(k in low_name for k in ("hermes", "antigravity", "gemini", "claude", "cursor", "codex", "windsurf", "qwen", "kling", "ollama")):
                return ("yellow", "AGENTS", f"Datos de Agente / App IA ({name})")
            return ("yellow", "CUSTOM", f"Directorio ({name})")
        else:
            if ext in (".incomplete", ".part", ".crdownload", ".aria2"):
                return ("green", "MODELS", f"Descarga Huérfana / Incompleta ({ext} — Seguro limpiar)")
            if ext in self.rules.get("model_extensions", []):
                return ("yellow", "MODELS", f"Peso de Modelo IA ({ext})")
            if ext in self.rules.get("cache_extensions", []):
                return ("green", "DEVCACHE", f"Archivo de Caché / Temporal ({ext})")
            if ext == ".json" and ("workflow" in low_name or "ltx" in low_name or "wan" in low_name or "flux" in low_name):
                return ("red", "COMFYUI", "Workflow de ComfyUI (.json Protegido)")
            if ext in self.rules.get("media_extensions", []):
                return ("yellow", "COMFYUI", f"Media / Output Generado ({ext})")
            return ("yellow", "CUSTOM", f"Archivo ({ext or 'sin ext'})")

    def _resolve_ollama_manifests(self) -> Dict[str, str]:
        """Maps sha256 blob filenames in ~/.ollama/models/blobs to human model names."""
        blob_to_model: Dict[str, str] = {}
        manifests_root = expand_win_path("%USERPROFILE%\\.ollama\\models\\manifests")
        if not os.path.isdir(manifests_root):
            return blob_to_model

        for root, _, files in os.walk(manifests_root):
            for fname in files:
                fpath = os.path.join(root, fname)
                rel = os.path.relpath(fpath, manifests_root)
                parts = rel.split(os.sep)
                model_label = ":".join(parts[-2:]) if len(parts) >= 2 else fname
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    layers = data.get("layers", [])
                    if isinstance(data.get("config"), dict):
                        layers.append(data["config"])
                    for layer in layers:
                        digest = layer.get("digest", "")
                        if digest.startswith("sha256:"):
                            blob_name = "sha256-" + digest.split(":", 1)[1]
                            blob_to_model[blob_name] = model_label
                except Exception:
                    continue
        return blob_to_model

    def _scan_target(self, radar: Dict[str, Any], target: Dict[str, Any], ollama_map: Dict[str, str], now: float) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        raw_path = target["path"]
        resolved_path = expand_win_path(raw_path)

        if not os.path.exists(resolved_path):
            return items

        base_safety = target.get("safety", "yellow")
        base_kind = target.get("kind", radar["name"])
        group_mode = target.get("group_mode", "root")
        category = radar.get("category", "OTHER")
        radar_id = radar.get("id", "custom")
        radar_name = radar.get("name", "Custom")
        icon = radar.get("icon", "📁")

        def make_item(path: str, display_name: str, size: int, fcount: int, mtime: float, is_dir: bool, safety_override: Optional[str] = None, kind_override: Optional[str] = None) -> Optional[Dict[str, Any]]:
            if size <= 0 and safety_override != "red" and base_safety != "red":
                return None
            eff_safety = safety_override or base_safety
            eff_kind = kind_override or base_kind

            if self._is_protected_name(os.path.basename(path), path):
                eff_safety = "red"
                if "PROTEGIDO" not in eff_kind.upper():
                    eff_kind = f"PROTEGIDO 🔒 (Skills / Memoria / Config) — {eff_kind}"

            days_inactive = max(0, int((now - mtime) / 86400.0)) if mtime > 0 else 0
            # Protect active Antigravity conversations modified in the last 20 minutes
            if radar_id == "antigravity_gemini" and (now - mtime) < 1200 and "brain" in path.lower():
                eff_safety = "red"
                eff_kind = "Sesión Activa de Antigravity (En uso ahora)"

            drive = get_drive_letter(path)
            return {
                "id": f"{radar_id}:{path}",
                "name": f"[{drive}] {display_name}",
                "path": path,
                "drive": drive,
                "is_dir": is_dir,
                "size_bytes": size,
                "size_human": format_bytes(size),
                "file_count": fcount,
                "mtime": mtime,
                "days_inactive": days_inactive,
                "safety": eff_safety,
                "category": category,
                "radar_id": radar_id,
                "radar_name": radar_name,
                "icon": icon,
                "kind": eff_kind,
            }

        try:
            if group_mode == "single_file" or os.path.isfile(resolved_path):
                st = os.stat(resolved_path)
                it = make_item(resolved_path, os.path.basename(resolved_path), st.st_size, 1, st.st_mtime, False)
                if it:
                    items.append(it)
                return items

            if group_mode == "root":
                sz, fc, mt, prot_reason = self._fast_dir_stats_checked(resolved_path)
                parent_name = os.path.basename(os.path.dirname(resolved_path))
                base_name = os.path.basename(resolved_path)
                label = f"{parent_name} / {base_name}" if parent_name else f"{radar_name} — {base_name}"
                safety_ov = "red" if prot_reason else None
                kind_ov = f"PROTEGIDO 🔒 ({prot_reason}) — {base_kind}" if prot_reason else None
                it = make_item(resolved_path, label, sz, fc, mt, True, safety_ov, kind_ov)
                if it:
                    items.append(it)
                return items

            if group_mode == "dot_cache_smart":
                hf_hub_exists = os.path.isdir(os.path.join(resolved_path, "huggingface", "hub"))
                model_cache_dirs = {
                    "whisper", "lm-studio", "gpt4all", "ms-playwright", "ultralytics",
                    "datalab", "ollama", "huggingface", "clip", "diffusers", "transformers"
                }
                pure_dot_cache_dirs = {
                    "gdown", "yt-dlp", "pip", "uv", "torch", "triton", "node", "npm",
                    "pnpm", "ruff", "mypy", "black", "pre-commit", "fontconfig",
                    "matplotlib", "pyinstaller", "werkzeug", "selenium", "puppeteer"
                }
                with os.scandir(resolved_path) as entries:
                    for entry in entries:
                        try:
                            if entry.is_symlink():
                                continue
                            low_n = entry.name.lower()
                            if entry.is_dir(follow_symlinks=False):
                                if low_n == "huggingface" and hf_hub_exists:
                                    # huggingface\hub is scanned separately; skip parent to prevent duplicates & accidental deletion
                                    continue
                                sz, fc, mt, prot_reason = self._fast_dir_stats_checked(entry.path)
                                if prot_reason or self._is_protected_name(entry.name, entry.path):
                                    safety_ov = "red"
                                    kind_ov = f"PROTEGIDO 🔒 ({prot_reason or entry.name}) en .cache"
                                elif low_n in model_cache_dirs:
                                    safety_ov = "yellow"
                                    kind_ov = f"Modelos / Pesos descargados en .cache ({entry.name})"
                                elif low_n in pure_dot_cache_dirs or "cache" in low_n:
                                    safety_ov = "green"
                                    kind_ov = f"Caché técnica regenerable en .cache ({entry.name})"
                                else:
                                    safety_ov = "yellow"
                                    kind_ov = f"Caché / Datos en .cache ({entry.name} — Revisar)"
                                it = make_item(entry.path, f".cache / {entry.name}", sz, fc, mt, True, safety_ov, kind_ov)
                                if it:
                                    items.append(it)
                            elif entry.is_file(follow_symlinks=False):
                                st = entry.stat(follow_symlinks=False)
                                ext = os.path.splitext(low_n)[1]
                                if self._is_protected_name(entry.name, entry.path):
                                    safety_ov = "red"
                                    kind_ov = f"PROTEGIDO 🔒 ({entry.name}) en .cache"
                                elif ext in (".log", ".tmp", ".temp", ".incomplete", ".part"):
                                    safety_ov = "green"
                                    kind_ov = f"Temporal en .cache ({entry.name})"
                                else:
                                    safety_ov = "yellow"
                                    kind_ov = f"Archivo en .cache ({entry.name})"
                                it = make_item(entry.path, f".cache / {entry.name}", st.st_size, 1, st.st_mtime, False, safety_ov, kind_ov)
                                if it:
                                    items.append(it)
                        except (PermissionError, OSError):
                            continue
                return items

            if group_mode == "huggingface":
                with os.scandir(resolved_path) as entries:
                    for entry in entries:
                        if entry.is_dir(follow_symlinks=False):
                            sz, fc, mt = self._fast_dir_stats(entry.path)
                            pretty = entry.name
                            if pretty.startswith("models--"):
                                pretty = "HF Model: " + pretty[len("models--"):].replace("--", "/")
                            elif pretty.startswith("datasets--"):
                                pretty = "HF Dataset: " + pretty[len("datasets--"):].replace("--", "/")
                            it = make_item(entry.path, pretty, sz, fc, mt, True)
                            if it:
                                items.append(it)
                            # Also check for orphaned .incomplete downloads inside blobs/
                            blobs_dir = os.path.join(entry.path, "blobs")
                            if os.path.isdir(blobs_dir):
                                try:
                                    with os.scandir(blobs_dir) as b_entries:
                                        for b_ent in b_entries:
                                            if b_ent.is_file(follow_symlinks=False) and b_ent.name.endswith((".incomplete", ".tmp", ".part")):
                                                bst = b_ent.stat(follow_symlinks=False)
                                                bit = make_item(
                                                    b_ent.path,
                                                    f"HF Blob Huérfano/Incompleto ({pretty})",
                                                    bst.st_size,
                                                    1,
                                                    bst.st_mtime,
                                                    False,
                                                    "green",
                                                    "Descarga incompleta/huérfana de Hugging Face (Seguro limpiar)",
                                                )
                                                if bit:
                                                    items.append(bit)
                                except (PermissionError, OSError):
                                    pass
                return items

            if group_mode == "temp_ai_only":
                ai_keywords = ("pip-", "uv-", "torch", "comfy", "gradio", "huggingface", "ollama", "whisper", "hermes", "gemini", "antigravity", "claude", "codex", "cursor", "npm-", "pyinstaller", "python", "electron", "node", "cuda", "triton", "onnx", "qwen")
                with os.scandir(resolved_path) as entries:
                    for entry in entries:
                        try:
                            low = entry.name.lower()
                            is_ai = any(k in low for k in ai_keywords)
                            if entry.is_dir(follow_symlinks=False):
                                sz, fc, mt, prot_reason = self._fast_dir_stats_checked(entry.path, max_depth=4)
                                if is_ai or sz >= 5 * 1024 * 1024:
                                    if prot_reason or self._is_protected_name(entry.name, entry.path):
                                        safety_ov = "red"
                                        kind_ov = f"PROTEGIDO 🔒 ({prot_reason or entry.name}) en Temp"
                                    elif mt > 0 and (now - mt) < 7200:
                                        safety_ov = "yellow"
                                        kind_ov = "Temporal reciente (<2h, posible app en uso) en AppData\\Local\\Temp"
                                    else:
                                        safety_ov = "green"
                                        kind_ov = "Carpeta Temporal en AppData\\Local\\Temp (Disco C:)"
                                    it = make_item(entry.path, f"Temp: {entry.name}", sz, fc, mt, True, safety_ov, kind_ov)
                                    if it:
                                        items.append(it)
                            elif entry.is_file(follow_symlinks=False):
                                st = entry.stat(follow_symlinks=False)
                                if is_ai or st.st_size >= 5 * 1024 * 1024:
                                    if self._is_protected_name(entry.name, entry.path):
                                        safety_ov = "red"
                                        kind_ov = f"PROTEGIDO 🔒 ({entry.name}) en Temp"
                                    elif st.st_mtime > 0 and (now - st.st_mtime) < 7200:
                                        safety_ov = "yellow"
                                        kind_ov = "Temporal reciente (<2h, posible app en uso) en AppData\\Local\\Temp"
                                    else:
                                        safety_ov = "green"
                                        kind_ov = "Archivo Temporal en AppData\\Local\\Temp (Disco C:)"
                                    it = make_item(entry.path, f"Temp: {entry.name}", st.st_size, 1, st.st_mtime, False, safety_ov, kind_ov)
                                    if it:
                                        items.append(it)
                        except (PermissionError, OSError):
                            continue
                return items

            # Generic subfolder / file modes
            sub_entries = list(os.scandir(resolved_path))
            if not sub_entries and group_mode == "subfolders_or_root":
                return items

            has_subdirs = False
            root_files_size = 0
            root_files_count = 0
            root_files_mtime = 0.0
            loose_files: List[Tuple[str, str, int, float]] = []

            for entry in sub_entries:
                try:
                    if entry.is_symlink():
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        has_subdirs = True
                        if group_mode == "files_only":
                            continue
                        sz, fc, mt, prot_reason = self._fast_dir_stats_checked(entry.path)
                        label = f"{os.path.basename(resolved_path)} / {entry.name}"
                        safety_ov = None
                        kind_ov = None
                        if group_mode == "agent_smart_subfolders":
                            safety_ov, kind_ov = self._classify_agent_subfolder(entry.path, entry.name, True, radar_name)
                        elif radar_id == "antigravity_gemini" and "brain" in resolved_path.lower():
                            label = f"Antigravity Brain Session [{entry.name[:8]}...]"
                        if prot_reason and safety_ov != "red":
                            safety_ov = "red"
                            kind_ov = f"PROTEGIDO 🔒 ({prot_reason}) — {kind_ov or base_kind}"
                        it = make_item(entry.path, label, sz, fc, mt, True, safety_ov, kind_ov)
                        if it:
                            items.append(it)
                    elif entry.is_file(follow_symlinks=False):
                        st = entry.stat(follow_symlinks=False)
                        if group_mode in ("files_and_subfolders", "subfolders_and_files", "files_only", "agent_smart_subfolders"):
                            display = entry.name
                            safety_ov = None
                            kind_ov = None
                            if group_mode == "agent_smart_subfolders":
                                display = f"{os.path.basename(resolved_path)} / {entry.name}"
                                safety_ov, kind_ov = self._classify_agent_subfolder(entry.path, entry.name, False, radar_name)
                            elif "ollama" in resolved_path.lower() and entry.name in ollama_map:
                                display = f"Ollama [{ollama_map[entry.name]}] ({entry.name[:15]}...)"
                            elif "ollama" in resolved_path.lower() and entry.name.startswith("sha256-"):
                                display = f"Ollama Blob Huérfano/Sin Tag ({entry.name[:19]}...)"
                                safety_ov = "green"
                                kind_ov = "Blob de Ollama sin manifest asociado (Seguro limpiar)"
                            elif entry.name.lower().endswith((".incomplete", ".part", ".tmp", ".temp", ".crdownload", ".aria2")):
                                display = f"Descarga Huérfana/Incompleta — {entry.name}"
                                safety_ov = "green"
                                kind_ov = "Archivo de descarga incompleta o huérfano (Seguro limpiar)"
                            it = make_item(entry.path, display, st.st_size, 1, st.st_mtime, False, safety_ov, kind_ov)
                            if it:
                                items.append(it)
                        else:
                            root_files_size += st.st_size
                            root_files_count += 1
                            if st.st_mtime > root_files_mtime:
                                root_files_mtime = st.st_mtime
                            loose_files.append((entry.path, entry.name, st.st_size, st.st_mtime))
                except (PermissionError, OSError):
                    continue

            if root_files_count > 0 and group_mode in ("subfolders_or_root", "subfolders"):
                has_protected_loose = any(self._is_protected_name(fn, fp) for fp, fn, _, _ in loose_files)
                if not has_subdirs and group_mode == "subfolders_or_root" and not has_protected_loose:
                    it = make_item(
                        resolved_path,
                        f"{radar_name} — {os.path.basename(resolved_path)} ({root_files_count} archivos)",
                        root_files_size,
                        root_files_count,
                        root_files_mtime,
                        True,
                    )
                    if it:
                        items.append(it)
                else:
                    # Never return the parent directory if subdirectories or protected loose files exist
                    for fpath, fname, fsize, fmtime in loose_files:
                        is_prot_loose = self._is_protected_name(fname, fpath)
                        if fsize >= 65536 or is_prot_loose:
                            safety_ov = "red" if is_prot_loose else None
                            it = make_item(
                                fpath,
                                f"{os.path.basename(resolved_path)} / {fname}",
                                fsize,
                                1,
                                fmtime,
                                False,
                                safety_ov,
                            )
                            if it:
                                items.append(it)

        except (PermissionError, OSError):
            pass

        return items

    def _deduplicate_hierarchy(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Ensures no ancestor directory item has weaker safety than any descendant item inside it."""
        strictness = {"green": 1, "yellow": 2, "red": 3}
        norm_paths = [
            os.path.normcase(os.path.normpath(it["path"])).rstrip("\\/")
            for it in items
        ]

        for idx, parent in enumerate(items):
            if not parent.get("is_dir"):
                continue
            p_prefix = norm_paths[idx] + os.sep
            p_level = strictness.get(parent.get("safety", "yellow"), 2)

            for jdx, child in enumerate(items):
                if idx == jdx:
                    continue
                if norm_paths[jdx].startswith(p_prefix):
                    c_safety = child.get("safety", "yellow")
                    c_level = strictness.get(c_safety, 2)
                    if c_level > p_level:
                        parent["safety"] = c_safety
                        p_level = c_level
                        if c_safety == "red" and "PROTEGIDO" not in parent.get("kind", "").upper():
                            parent["kind"] = f"PROTEGIDO 🔒 (Contiene elementos protegidos) — {parent.get('kind', '')}"
        return items

    def run_smart_scan(self, extra_paths: Optional[List[str]] = None) -> Dict[str, Any]:
        # Reload rules on each scan so edits to rules.json apply immediately
        self.rules = self._load_rules()
        t0 = time.perf_counter()
        now = time.time()
        ollama_map = self._resolve_ollama_manifests()
        comfy_roots = discover_comfyui_roots()
        all_items: List[Dict[str, Any]] = []
        seen_paths = set()

        tasks = []
        for radar in self.rules.get("radars", []):
            for target in radar.get("targets", []):
                raw_p = target.get("path", "")
                if "%COMFYUI_ROOT%" in raw_p:
                    for cr in comfy_roots:
                        expanded_target = dict(target)
                        expanded_target["path"] = raw_p.replace("%COMFYUI_ROOT%", cr)
                        tasks.append((radar, expanded_target))
                else:
                    tasks.append((radar, target))

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(self._scan_target, r, t, ollama_map, now) for r, t in tasks]
            for fut in as_completed(futures):
                try:
                    res = fut.result()
                    for item in res:
                        norm_p = os.path.normcase(os.path.normpath(item["path"]))
                        if norm_p not in seen_paths:
                            seen_paths.add(norm_p)
                            all_items.append(item)
                except Exception:
                    continue

        # Also scan workspace root (E:\ia-ai if present on this system) + any extra paths
        default_ws = "E:\\ia-ai"
        scan_dirs = ([default_ws] if os.path.isdir(default_ws) else []) + (extra_paths or [])
        for custom_dir in scan_dirs:
            resolved = expand_win_path(custom_dir)
            if os.path.isdir(resolved):
                custom_items = self._scan_directory_shallow(resolved, now, seen_paths)
                all_items.extend(custom_items)

        all_items = self._deduplicate_hierarchy(all_items)
        return self._build_response(all_items, t0, mode="SMART_HYBRID")

    def scan_custom_path(self, raw_path: str) -> Dict[str, Any]:
        self.rules = self._load_rules()
        t0 = time.perf_counter()
        now = time.time()
        resolved = expand_win_path(raw_path)
        if not os.path.exists(resolved):
            raise FileNotFoundError(f"La ruta no existe: {resolved}")

        # If the user scans C:\ root directly, do an optimized C:\ AI & User Profile scan
        # instead of hanging for 60s inside C:\Windows\System32!
        if os.path.normcase(resolved) in ("c:\\", "c:"):
            res = self.run_smart_scan()
            c_items = [i for i in res["items"] if i.get("drive") == "C:"]
            return self._build_response(c_items, t0, mode="SMART DISCO C:\\ (IA & CACHÉ)")

        seen_paths = set()
        items = self._scan_directory_shallow(resolved, now, seen_paths, include_all=True)
        return self._build_response(items, t0, mode=f"CUSTOM: {resolved}")

    def _scan_directory_shallow(self, root_dir: str, now: float, seen_paths: set, include_all: bool = False) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        try:
            entries = list(os.scandir(root_dir))
        except (PermissionError, OSError):
            return items

        def process_entry(entry) -> Optional[Dict[str, Any]]:
            try:
                if entry.is_symlink():
                    return None
                norm_p = os.path.normcase(os.path.normpath(entry.path))
                if norm_p in seen_paths:
                    return None
                if not include_all and entry.name.lower() == "bye-ai-cache":
                    return None

                is_dir = entry.is_dir(follow_symlinks=False)
                prot_reason = None
                if is_dir:
                    sz, fc, mt, prot_reason = self._fast_dir_stats_checked(entry.path, max_depth=6, check_depth=3)
                else:
                    st = entry.stat(follow_symlinks=False)
                    sz, fc, mt = st.st_size, 1, st.st_mtime

                if sz <= 0 and not prot_reason:
                    return None

                safety, category, kind = self._classify_arbitrary_entry(entry.path, entry.name, is_dir)
                if prot_reason:
                    safety = "red"
                    kind = f"PROTEGIDO 🔒 — Contiene Repo Git / Skills / Workflows ({prot_reason})"

                days_inactive = max(0, int((now - mt) / 86400.0)) if mt > 0 else 0
                drive = get_drive_letter(entry.path)
                return {
                    "id": f"custom:{entry.path}",
                    "name": f"[{drive}] {os.path.basename(root_dir) or root_dir} / {entry.name}",
                    "path": entry.path,
                    "drive": drive,
                    "is_dir": is_dir,
                    "size_bytes": sz,
                    "size_human": format_bytes(sz),
                    "file_count": fc,
                    "mtime": mt,
                    "days_inactive": days_inactive,
                    "safety": safety,
                    "category": category,
                    "radar_id": "workspace_custom",
                    "radar_name": f"Disco ({os.path.basename(root_dir) or root_dir})",
                    "icon": "💿",
                    "kind": kind,
                }
            except (PermissionError, OSError):
                return None

        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(process_entry, e) for e in entries]
            for fut in as_completed(futures):
                it = fut.result()
                if it:
                    norm_p = os.path.normcase(os.path.normpath(it["path"]))
                    if norm_p not in seen_paths:
                        seen_paths.add(norm_p)
                        items.append(it)

        return items

    def _build_response(self, items: List[Dict[str, Any]], t0: float, mode: str) -> Dict[str, Any]:
        items.sort(key=lambda x: x["size_bytes"], reverse=True)
        elapsed_ms = max(1, int((time.perf_counter() - t0) * 1000))

        total_bytes = sum(i["size_bytes"] for i in items)
        total_files = sum(i["file_count"] for i in items)
        files_per_sec = int((total_files / (elapsed_ms / 1000.0))) if elapsed_ms > 0 else total_files

        safety_totals = {"green": 0, "yellow": 0, "red": 0}
        category_totals = {
            "AGENTS": 0,
            "COMFYUI": 0,
            "MODELS": 0,
            "DEVCACHE": 0,
            "CUSTOM": 0,
        }
        drive_totals: Dict[str, int] = {}

        for i in items:
            s = i.get("safety", "yellow")
            safety_totals[s] = safety_totals.get(s, 0) + i["size_bytes"]
            c = i.get("category", "CUSTOM")
            category_totals[c] = category_totals.get(c, 0) + i["size_bytes"]
            drv = i.get("drive") or get_drive_letter(i.get("path", ""))
            drive_totals[drv] = drive_totals.get(drv, 0) + i["size_bytes"]

        sorted_drives = dict(sorted(drive_totals.items(), key=lambda kv: kv[0]))

        return {
            "mode": mode,
            "elapsed_ms": elapsed_ms,
            "files_scanned": total_files,
            "files_per_sec": files_per_sec,
            "total_bytes": total_bytes,
            "total_human": format_bytes(total_bytes),
            "safety_totals": {
                k: {"bytes": v, "human": format_bytes(v)} for k, v in safety_totals.items()
            },
            "category_totals": {
                k: {"bytes": v, "human": format_bytes(v)} for k, v in category_totals.items()
            },
            "drive_totals": {
                k: {"bytes": v, "human": format_bytes(v)} for k, v in sorted_drives.items()
            },
            "items": items,
        }
