# ⚡ `bye-ai-cache` v1.5 — WinDirStat + Winamp 2000s AI Cleaner

> **"Los agentes de IA y los modelos locales nos ayudan un montón, pero nos llenan el disco de cachés, logs y blobs huérfanos."**
> `bye-ai-cache` es una utilidad de escritorio ultra-liviana inspirada en **WinDirStat** y en la estética **Windows 2000 + Winamp 2.x (Y2K 3D Bevel)** diseñada para detectar, visualizar en un **Treemap 3D Cushion** y limpiar cachés de IA, descargas cortadas y artefactos pesados de desarrollo **sin riesgo de borrar tus skills, memorias, chats, workflows ni código fuente**.

---

## ✨ Características Principales

1. **Estética Y2K / Winamp 2.x + Windows 2000 3D:**
   * **4 Módulos acoplables** (`Main Deck`, `Equalizer / Radars`, `Playlist Editor` + `AVS 3D Cushion Visualizer`) con modo *WindowShade* (`_`) igual que Winamp.
   * **2 Skins intercambiables en vivo:**
     * ☀️ **Win2000 Classic Grey:** Gris clásico (`#D4D0C8`) con biseles 3D profundos y barra azul clásica de Windows 2000.
     * 🌙 **Winamp Dark Cyber Blue:** Gris grafito metálico + azul profundo con display LCD de matriz de puntos y analizador de espectro.

2. **Radares de IA & Dev Multi-Disco (`scanner/rules.json`):**
   * ⚡ **Hermes Agent:** Detecta cachés de escritorio y temporales (`Cache`, `Code Cache`, `GPUCache`, `blob_storage`), mientras protege con candado tus `skills`, `memory`, `active-profile.json` y `.hermes.md`.
   * 🛸 **Antigravity & Gemini:** Cachés de app, `daemon`, `crashes`, `sandbox` y sesiones pasadas (protegiendo automáticamente la sesión activa y las carpetas `builtin`, `knowledge` y `mcp`).
   * 🤖 **OpenAI Codex / Claude Code & Desktop / Cursor / Windsurf / Qwen / VS Code:** Detecta `CachedData`, `VSIXs`, `Crashpad`, `logs` y cachés Chromium; bloquea con candado `AGENTS.md`, `CLAUDE.md`, `.cursorrules`, `*.mdc`, `commands/`, `skills/`, `mcp.json` y `claude_desktop_config.json`.
   * 🎨 **ComfyUI Portable & Local GenAI (Auto-detección en todos los discos `C:`..`Z:`):** Encuentra automáticamente tu instalación de ComfyUI sin rutas fijas (`temp`, `output`, `input`, `checkpoints`, `unet`, `diffusion_models`, `loras`, `controlnet`, `text_encoders`, `vae`) y **bloquea tus `workflows` y `custom_nodes`**.
   * 🧠 **Hugging Face Hub / Ollama / Triton / Whisper / Playwright:** Traduce carpetas `models--org--repo`, cruza `manifests` de Ollama con sus `blobs` SHA256 y detecta **blobs huérfanos y descargas cortadas (`.incomplete`, `.part`, `.tmp`)**.
   * 📦 **Python / Node / Adobe Cache & Shaders:** `pip`, `conda`, `uv`, `npm-cache`, `pnpm-store`, **Adobe Media Cache** (`Media Cache Files` / `Temp\Adobe` en 🟢 Verde) y **NVIDIA `DXCache`/`GLCache`** en 🟡 Amarillo (opcional).

3. **Semáforo de Seguridad de 3 Niveles:**
   * 🟢 **VERDE (Caché Pura / 100% Seguro):** Cachés técnicas regenerables, temporales de +2h de antigüedad, logs, `CachedData` y descargas huérfanas.
   * 🟡 **AMARILLO (Modelos / Outputs / Shaders / Historiales):** Pesos `.safetensors`/`.gguf`, renders, sesiones antiguas, temporales recientes (`<2h`) y shaders DirectX (`DXCache`). Nunca se auto-seleccionan con el botón verde.
   * 🔴 **ROJO (Protegido / Bloqueado 🔒):** Skills, memorias, `.git`, workflows `.json`, `custom_nodes`, prompts, reglas y configs MCP. No tienen checkbox y están bloqueados a nivel backend.

---

## 🛡️ Arquitectura de Seguridad en 4 Capas (Anti-Borrado Accidental)

1. **Capa 1 — Reglas Estricas por Subcarpeta (`agent_smart_subfolders` & `dot_cache_smart`):**
   Nunca marca una carpeta raíz de un agente o de `.cache` como segura en bloque; clasifica subcarpeta por subcarpeta y evita que archivos sueltos en la raíz expongan a las subcarpetas padre a un borrado accidental.
2. **Capa 2 — Inspección Profunda de Contenido Protegido (`_fast_dir_stats_checked`):**
   Al escanear directorios arbitrarios o proyectos, inspecciona hasta 3 niveles internos: si encuentra `.git/`, `skills/`, `workflows/`, `memory/`, `.hermes.md`, `SKILL.md`, `CLAUDE.md`, `AGENTS.md`, `.cursorrules` o `*.mdc`, fuerza el semáforo de toda la carpeta a 🔴 **ROJO (`🔒`)**.
3. **Capa 3 — Deduplicación Jerárquica y Protección de Temporales Activos:**
   Ninguna carpeta padre puede tener un semáforo más permisivo que sus subcarpetas internas (`red > yellow > green`). Además, cualquier temporal modificado en las últimas **2 horas** baja automáticamente a 🟡 **AMARILLO** para no interferir con programas abiertos.
4. **Capa 4 — Guardián en el Limpiador + Papelera de Windows (`scanner/cleaner.py`):**
   Antes de ejecutar cualquier borrado (`execute_clean`), `is_critical_system_root()` vuelve a auditar la ruta en disco y el contenido de primer nivel (`.git`, `skills`, `memory`, `workflows`, archivos de reglas/MCP) rechazando la operación si detecta material crítico. Por defecto envía todo a la **Papelera de Reciclaje de Windows** vía `Shell32.SHFileOperationW` previa vista **Dry-Run**.

---

## 🚀 Cómo usarlo (0 dependencias externas)

Solo necesitás **Python 3.10+** en Windows. No hace falta instalar compiladores ni librerías pesadas.

1. Cloná o descargá el repositorio y hacé **doble clic en:**
   ```bat
   run_bye_ai_cache.bat
   ```
2. O desde la terminal:
   ```powershell
   git clone https://github.com/<tu-usuario>/bye-ai-cache.git
   cd bye-ai-cache
   python app.py
   ```
   La app levanta el servidor local y se abre automáticamente como una ventana de escritorio.

---

## 🛠️ Personalizar o sumar nuevos Radares

Editá [`scanner/rules.json`](scanner/rules.json) para agregar nuevas rutas, patrones protegidos o herramientas de IA. ¡Las contribuciones y PRs de la comunidad son bienvenidas!
