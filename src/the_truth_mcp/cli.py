"""CLI: subcomandos del package.

`uv run the-truth-mcp` (sin args)         → corre el server MCP (default).
`uv run the-truth-mcp init <path>`        → crea una bóveda nueva en <path>.
`uv run the-truth-mcp install-claude ...` → all-in-one para Claude Code: vault +
                                             registro en `~/.claude.json`.
`uv run the-truth-mcp install-codex ...`  → mismo flujo, registra en Codex CLI
                                             (`~/.codex/config.toml`).
`uv run the-truth-mcp install-gemini ...` → mismo flujo, registra en Gemini CLI
                                             (`~/.gemini/settings.json`).
`uv run the-truth-mcp run`                → alias explícito del server.
`uv run the-truth-mcp doctor [<path>]`    → verifica el setup (env vars, key, vault).
`uv run the-truth-mcp --version`          → imprime la versión.
"""

from __future__ import annotations

import argparse
import getpass
import json as _json
import os
import shutil
import subprocess
import sys
from importlib import resources
from pathlib import Path

from . import __version__


_PLACEHOLDER = "__VAULT_PATH__"


def _template_root() -> Path:
    """Devuelve el path al template empaquetado (src/the_truth_mcp/vault_starter/)."""
    return Path(str(resources.files("the_truth_mcp").joinpath("vault_starter")))


def _substitute_vault_path(root: Path, target_str: str) -> None:
    """Reemplaza `_PLACEHOLDER` por `target_str` en cualquier archivo bajo `root`.

    Idempotente: si el placeholder no aparece en un archivo, no lo toca. Ignora
    archivos binarios (UnicodeDecodeError).
    """
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if _PLACEHOLDER in text:
            path.write_text(text.replace(_PLACEHOLDER, target_str), encoding="utf-8")


def _is_empty_dir(p: Path) -> bool:
    return p.is_dir() and not any(p.iterdir())


def init_vault(target: Path, *, force: bool = False) -> None:
    """Crea una bóveda nueva copiando el template a `target` y rellenando placeholders.

    Falla si target existe y no está vacío, salvo --force.
    """
    target = target.expanduser().resolve()
    src = _template_root()

    if not src.is_dir():
        raise RuntimeError(
            f"Template no encontrado en {src}. ¿Está corrupta la instalación del paquete?"
        )

    if target.exists():
        if not target.is_dir():
            raise RuntimeError(f"{target} existe y no es directorio")
        if not _is_empty_dir(target) and not force:
            raise RuntimeError(
                f"{target} no está vacío. Pasá --force para sobreescribir o "
                "elegí otra ruta."
            )
    else:
        target.mkdir(parents=True)

    # Copia recursiva. shutil.copytree no acepta destino existente sin
    # dirs_exist_ok; usamos esa variante.
    shutil.copytree(src, target, dirs_exist_ok=True)

    # Borrá los .gitkeep que solo existen para que el template viaje por git;
    # en el vault del usuario son ruido.
    for keep in target.rglob(".gitkeep"):
        keep.unlink()

    # Reemplazá el placeholder en cualquier archivo del template.
    _substitute_vault_path(target, str(target))


def _print_next_steps(target: Path) -> None:
    print()
    print(f"✓ Bóveda creada en: {target}")
    print()
    print("Próximos pasos:")
    print()
    print("  1. Sacá una API key de Gemini (free tier):")
    print("     https://aistudio.google.com/apikey")
    print()
    print("  2. Dejala disponible para el server. Cualquiera de estas opciones:")
    print()
    print("     a) Exportala en tu shell rc (~/.zshrc, ~/.bashrc):")
    print("        export GEMINI_API_KEY=tu-key")
    print()
    print("     b) Guardala en la config global del MCP (chmod 600):")
    print("        # se escribe automáticamente al correr cualquier `install*`")
    print("        # → ~/.config/the-truth-mcp/.env")
    print()
    print("  3. Registrá el MCP en tu cliente preferido:")
    print(f"     the-truth-mcp install-claude  --vault {target}   # Claude Code (Anthropic)")
    print(f"     the-truth-mcp install-codex   --vault {target}   # Codex CLI (OpenAI)")
    print(f"     the-truth-mcp install-gemini  --vault {target}   # Gemini CLI (Google)")
    print()
    print("  4. Abrí tu cliente apuntando al vault y empezá a usar el MCP:")
    print("     - tools de lectura: vault_search, vault_read_page, vault_list_pages")
    print("     - tool de escritura: save_info  (Gemini reorganiza la bóveda)")
    print()


_API_KEY_VARS = ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GEMINI_APIKEY", "GOOGLE_GENAI_API_KEY")


def _check(label: str, ok: bool, detail: str = "") -> bool:
    icon = "✓" if ok else "✗"
    line = f"  {icon} {label}"
    if detail:
        line += f": {detail}"
    print(line)
    return ok


def doctor(vault_path: Path | None) -> int:
    """Verifica el setup del usuario. Reporta y devuelve exit code."""
    from dotenv import load_dotenv

    print("the-truth-mcp doctor\n")

    load_dotenv()
    if vault_path:
        load_dotenv(vault_path.expanduser() / ".env", override=False)
    load_dotenv(Path.home() / ".config" / "the-truth-mcp" / ".env", override=False)

    all_ok = True

    # 1. API key
    found_var = next((v for v in _API_KEY_VARS if os.environ.get(v)), None)
    all_ok &= _check(
        "API key de Gemini",
        bool(found_var),
        detail=(found_var or f"falta — definí una de: {', '.join(_API_KEY_VARS)}"),
    )

    # 2. Vault path
    if vault_path:
        target = vault_path.expanduser().resolve()
        all_ok &= _check("vault existe", target.is_dir(), detail=str(target))
        all_ok &= _check("AGENTS.md presente", (target / "AGENTS.md").is_file())
        all_ok &= _check("raw/ presente", (target / "raw").is_dir())
        all_ok &= _check("wiki/ presente", (target / "wiki").is_dir())
        all_ok &= _check(
            "log.md presente", (target / "log.md").is_file()
        )
    else:
        env_vault = os.environ.get("VAULT_PATH") or os.environ.get("LLM_WIKI_PATH")
        if env_vault:
            print(f"  ℹ  VAULT_PATH={env_vault} (re-corré con `doctor {env_vault}` para verificar el vault)")
        else:
            print("  ℹ  pasame un path al vault para verificarlo: `the-truth-mcp doctor <path>`")

    # 3. Llamada de salud a Gemini (si hay key y se pidió)
    if found_var:
        try:
            from google import genai
            client = genai.Client(api_key=os.environ[found_var])
            model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
            response = client.models.generate_content(
                model=model, contents="Responde solo con 'ok'."
            )
            ok = "ok" in (response.text or "").lower()
            all_ok &= _check(f"Gemini responde ({model})", ok, detail=(response.text or "").strip()[:40])
        except Exception as e:
            all_ok &= _check("Gemini responde", False, detail=str(e)[:80])

    print()
    if all_ok:
        print("Todo en orden.")
        return 0
    print("Faltan cosas — ver errores arriba.")
    return 1


_GIT_REPO = "git+https://github.com/guilleheizen/the-truth-mcp"
_USER_CONFIG_DIR = Path.home() / ".config" / "the-truth-mcp"
_USER_ENV_FILE = _USER_CONFIG_DIR / ".env"


def _write_user_env(key: str | None, model: str | None) -> Path:
    """Escribe (upsert) la API key y el modelo en ~/.config/the-truth-mcp/.env.

    No pisa otras variables que el usuario haya puesto ahí. Si `key` o `model`
    son None, no se tocan los valores existentes. Permisos 600.
    """
    from dotenv import set_key

    _USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not _USER_ENV_FILE.exists():
        _USER_ENV_FILE.touch(mode=0o600)
    else:
        # Asegurar permisos restrictivos aunque el archivo ya existiera.
        os.chmod(_USER_ENV_FILE, 0o600)

    if key:
        # Usamos GEMINI_API_KEY como nombre canónico — el server acepta los
        # aliases (GEMINI_APIKEY, GOOGLE_API_KEY, GOOGLE_GENAI_API_KEY) si el
        # usuario los tiene exportados en su shell.
        set_key(str(_USER_ENV_FILE), "GEMINI_API_KEY", key, quote_mode="never")
    if model:
        set_key(str(_USER_ENV_FILE), "GEMINI_MODEL", model, quote_mode="never")

    return _USER_ENV_FILE


# ──────────────────────────────────────────────────────────────────────────────
# Helpers compartidos por todos los `install-*`
# ──────────────────────────────────────────────────────────────────────────────


def _resolve_spawn(use_local_path: bool) -> tuple[str, list[str]]:
    """Cómo arrancar el server. Local (uv run) en dev, uvx desde el repo en prod."""
    if use_local_path:
        repo_root = str(Path(__file__).resolve().parent.parent.parent)
        return "uv", ["run", "--directory", repo_root, "the-truth-mcp"]
    return "uvx", ["--from", _GIT_REPO, "the-truth-mcp"]


def _resolve_install_key(key: str | None) -> tuple[int, str | None]:
    """Resuelve la API key a usar para el install.

    Orden de precedencia:
      1. `--key` arg → usar y persistir.
      2. Variable de entorno (`_API_KEY_VARS`) → no devolver el valor, el server la
         lee directo del shell. Retornamos `(0, None)`.
      3. TTY → preguntar con `getpass` (input oculto). Si vacío, abortar.
      4. Sin TTY y sin key → error.

    Retorna `(exit_code, key_to_use_or_None)`.
    """
    if key:
        return 0, key

    env_key_var = next((v for v in _API_KEY_VARS if os.environ.get(v)), None)
    if env_key_var:
        return 0, None

    if sys.stdin.isatty():
        value = getpass.getpass(
            "API key de Gemini (input oculto, Enter para abortar): "
        )
        if value:
            return 0, value

    print(
        "error: no encuentro una API key de Gemini.\n"
        "  Opción A — pasala con --key <tu-key>\n"
        "  Opción B — exportala en tu shell antes de correr install:\n"
        "             export GEMINI_API_KEY=...\n"
        "  Sacá una key gratis en https://aistudio.google.com/apikey",
        file=sys.stderr,
    )
    return 1, None


def _ensure_vault(vault: Path) -> tuple[int, Path]:
    """Crea el vault si falta o valida que el existente es uno válido.

    Retorna (exit_code, target_path). exit_code != 0 → abortar.
    """
    target = vault.expanduser().resolve()
    if not target.exists() or _is_empty_dir(target):
        print(f"→ Creando bóveda en {target}")
        init_vault(target, force=False)
    else:
        if not (target / "AGENTS.md").is_file():
            print(
                f"error: {target} existe pero no parece un vault de the-truth-mcp "
                "(falta AGENTS.md). Borralo o usá otro path.",
                file=sys.stderr,
            )
            return 1, target
        print(f"→ Bóveda existente detectada en {target}")
    return 0, target


def _persist_key_and_model(key: str | None, model: str) -> Path:
    """Upserta la key (si vino) y el modelo en la config global del usuario.

    Si la key vino solo del shell, se imprime de dónde la tomamos.
    """
    if key:
        env_file = _write_user_env(key=key, model=model)
        print(f"→ Guardando API key en {env_file} (permisos 600)")
    else:
        shell_var = next(v for v in _API_KEY_VARS if os.environ.get(v))
        env_file = _write_user_env(key=None, model=model)
        print(f"→ Usando API key de tu shell (${shell_var}). Modelo guardado en {env_file}.")
    return env_file


def _client_extras_dir(client_name: str) -> Path | None:
    """Devuelve el path empaquetado a client_extras/<client_name>/ si existe."""
    p = Path(str(resources.files("the_truth_mcp").joinpath("client_extras", client_name)))
    return p if p.is_dir() else None


def _copy_client_extras(client_name: str, target: Path) -> None:
    """Copia client_extras/<client_name>/* sobre el vault. No-op si no hay extras.

    Idempotente: pisa nuestros archivos pero no toca lo que el usuario haya
    agregado por su cuenta en otros paths.
    """
    src = _client_extras_dir(client_name)
    if src is None:
        return
    shutil.copytree(src, target, dirs_exist_ok=True)
    for keep in target.rglob(".gitkeep"):
        keep.unlink(missing_ok=True)
    _substitute_vault_path(target, str(target))


# ──────────────────────────────────────────────────────────────────────────────
# Registrars por cliente — cada uno escribe en el archivo de config nativo
# del cliente correspondiente.
# ──────────────────────────────────────────────────────────────────────────────


def _register_claude_code(
    *,
    target: Path,
    name: str,
    scope: str,
    spawn_command: str,
    spawn_args: list[str],
) -> int:
    """Registra el MCP en Claude Code via `claude mcp add-json`."""
    if shutil.which("claude") is None:
        print(
            "error: no se encuentra el ejecutable `claude` en el PATH. "
            "Instalá Claude Code primero: https://claude.com/claude-code",
            file=sys.stderr,
        )
        return 1

    # Idempotente: borrá registro previo antes de reinstalar
    subprocess.run(
        ["claude", "mcp", "remove", "--scope", scope, name],
        capture_output=True,
        check=False,
    )

    config = {
        "command": spawn_command,
        "args": spawn_args,
        "env": {"VAULT_PATH": str(target)},
    }
    print(f"→ Registrando MCP `{name}` en Claude Code (scope {scope})")
    result = subprocess.run(
        ["claude", "mcp", "add-json", "--scope", scope, name, _json.dumps(config)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"error: claude mcp add-json falló:\n{result.stderr}", file=sys.stderr)
        return result.returncode

    # Extras específicos para Claude Code: slash commands, permisos, hooks.
    _copy_client_extras("claude-code", target)
    return 0


def _register_codex(
    *,
    target: Path,
    name: str,
    spawn_command: str,
    spawn_args: list[str],
) -> int:
    """Registra el MCP en Codex CLI (OpenAI) editando ~/.codex/config.toml.

    Codex usa una tabla TOML `[mcp_servers.<name>]` con `command`, `args`, `env`.
    """
    import tomlkit

    config_path = Path.home() / ".codex" / "config.toml"
    config_path.parent.mkdir(parents=True, exist_ok=True)

    if config_path.is_file():
        try:
            doc = tomlkit.parse(config_path.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            print(f"error: {config_path} tiene TOML inválido: {e}", file=sys.stderr)
            return 1
    else:
        doc = tomlkit.document()

    if "mcp_servers" not in doc:
        doc["mcp_servers"] = tomlkit.table(is_super_table=True)

    server_entry = tomlkit.table()
    server_entry["command"] = spawn_command
    server_entry["args"] = list(spawn_args)
    env_table = tomlkit.table()
    env_table["VAULT_PATH"] = str(target)
    server_entry["env"] = env_table
    doc["mcp_servers"][name] = server_entry  # type: ignore[index]

    config_path.write_text(tomlkit.dumps(doc), encoding="utf-8")
    print(f"→ Registrando MCP `{name}` en Codex CLI ({config_path})")
    return 0


def _register_gemini_cli(
    *,
    target: Path,
    name: str,
    spawn_command: str,
    spawn_args: list[str],
) -> int:
    """Registra el MCP en Gemini CLI (Google) editando ~/.gemini/settings.json.

    Gemini CLI usa el mismo schema que Claude Desktop / Cursor: un objeto
    top-level `mcpServers` con `command`, `args`, `env`.
    """
    config_path = Path.home() / ".gemini" / "settings.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)

    if config_path.is_file():
        raw = config_path.read_text(encoding="utf-8").strip() or "{}"
        try:
            doc = _json.loads(raw)
        except _json.JSONDecodeError as e:
            print(f"error: {config_path} tiene JSON inválido: {e}", file=sys.stderr)
            return 1
    else:
        doc = {}

    mcp_servers = doc.setdefault("mcpServers", {})
    mcp_servers[name] = {
        "command": spawn_command,
        "args": list(spawn_args),
        "env": {"VAULT_PATH": str(target)},
    }

    config_path.write_text(_json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(f"→ Registrando MCP `{name}` en Gemini CLI ({config_path})")
    return 0


# ──────────────────────────────────────────────────────────────────────────────
# Subcomandos `install`, `install-codex`, `install-gemini`
# ──────────────────────────────────────────────────────────────────────────────


_PROBE_HINTS = {
    "claude-code": (
        "  cd {target}",
        "  claude",
        "  # luego dentro de Claude Code:",
        "  /mcp                 # confirma que `the-truth` está conectado",
        "  /ingest <url>        # guardar info nueva",
        "  /query <pregunta>    # consultar la bóveda",
    ),
    "codex": (
        "  cd {target}",
        "  codex",
        "  # dentro de Codex, listá los MCPs activos para confirmar `the-truth`.",
    ),
    "gemini-cli": (
        "  cd {target}",
        "  gemini",
        "  # dentro de Gemini CLI: /mcp list debería mostrar `the-truth`.",
    ),
}


def _print_install_success(
    *, client: str, target: Path, model: str, env_file: Path, name: str, scope: str | None
) -> None:
    print()
    print(f"✓ MCP `{name}` instalado en {client}.")
    print(f"  vault:  {target}")
    print(f"  modelo: {model}")
    if scope is not None:
        print(f"  scope:  {scope}")
    print(f"  config: {env_file} (key + modelo del bibliotecario)")
    print()
    print("Probalo:")
    for line in _PROBE_HINTS[client]:
        print(line.format(target=target))


def install(
    vault: Path,
    key: str | None,
    *,
    model: str = "gemini-2.5-flash",
    scope: str = "user",
    name: str = "the-truth",
    use_local_path: bool = False,
) -> int:
    """Instala el MCP en Claude Code.

    Crea la bóveda si falta, persiste la API key en `~/.config/the-truth-mcp/.env`
    (chmod 600), y registra el MCP via `claude mcp add-json`. La key NUNCA va a
    parar a `~/.claude.json`.
    """
    rc, key = _resolve_install_key(key)
    if rc:
        return rc
    rc, target = _ensure_vault(vault)
    if rc:
        return rc
    spawn_command, spawn_args = _resolve_spawn(use_local_path)
    env_file = _persist_key_and_model(key, model)
    rc = _register_claude_code(
        target=target, name=name, scope=scope,
        spawn_command=spawn_command, spawn_args=spawn_args,
    )
    if rc:
        return rc
    _print_install_success(
        client="claude-code", target=target, model=model,
        env_file=env_file, name=name, scope=scope,
    )
    return 0


def install_codex(
    vault: Path,
    key: str | None,
    *,
    model: str = "gemini-2.5-flash",
    name: str = "the-truth",
    use_local_path: bool = False,
) -> int:
    """Instala el MCP en Codex CLI (OpenAI).

    Igual que `install` pero registra en `~/.codex/config.toml` (tabla
    `[mcp_servers.<name>]`). No requiere tener `codex` instalado al momento de
    correr este comando — solo edita el archivo de config.
    """
    rc, key = _resolve_install_key(key)
    if rc:
        return rc
    rc, target = _ensure_vault(vault)
    if rc:
        return rc
    spawn_command, spawn_args = _resolve_spawn(use_local_path)
    env_file = _persist_key_and_model(key, model)
    rc = _register_codex(
        target=target, name=name,
        spawn_command=spawn_command, spawn_args=spawn_args,
    )
    if rc:
        return rc
    _print_install_success(
        client="codex", target=target, model=model,
        env_file=env_file, name=name, scope=None,
    )
    return 0


def install_gemini(
    vault: Path,
    key: str | None,
    *,
    model: str = "gemini-2.5-flash",
    name: str = "the-truth",
    use_local_path: bool = False,
) -> int:
    """Instala el MCP en Gemini CLI (Google).

    Igual que `install` pero registra en `~/.gemini/settings.json` (objeto
    `mcpServers`). No requiere tener `gemini` instalado al momento de correr.
    """
    rc, key = _resolve_install_key(key)
    if rc:
        return rc
    rc, target = _ensure_vault(vault)
    if rc:
        return rc
    spawn_command, spawn_args = _resolve_spawn(use_local_path)
    env_file = _persist_key_and_model(key, model)
    rc = _register_gemini_cli(
        target=target, name=name,
        spawn_command=spawn_command, spawn_args=spawn_args,
    )
    if rc:
        return rc
    _print_install_success(
        client="gemini-cli", target=target, model=model,
        env_file=env_file, name=name, scope=None,
    )
    return 0


def _add_common_install_flags(p: argparse.ArgumentParser) -> None:
    """Flags compartidas por install / install-codex / install-gemini."""
    p.add_argument(
        "--vault",
        required=True,
        help="Ruta absoluta a la bóveda (ej: ~/Documents/my-vault). Se crea si no existe.",
    )
    p.add_argument(
        "--key",
        default=None,
        help=(
            "API key de Gemini (https://aistudio.google.com/apikey). "
            "Opcional si ya la tenés exportada en tu shell como GEMINI_API_KEY "
            "(o aliases: GOOGLE_API_KEY, GEMINI_APIKEY, GOOGLE_GENAI_API_KEY)."
        ),
    )
    p.add_argument(
        "--model",
        default="gemini-2.5-flash",
        help="Modelo de Gemini para el bibliotecario (default: gemini-2.5-flash).",
    )
    p.add_argument(
        "--name",
        default="the-truth",
        help="Nombre del MCP server (default: the-truth).",
    )
    p.add_argument(
        "--local",
        action="store_true",
        help="Usar el código local del repo en lugar de uvx desde GitHub (para desarrollo).",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="the-truth-mcp",
        description="MCP server: bóveda LLM Wiki agnóstica al cliente. Gemini ordena.",
    )
    parser.add_argument("--version", action="version", version=f"the-truth-mcp {__version__}")
    sub = parser.add_subparsers(dest="command")

    p_run = sub.add_parser("run", help="Corre el server MCP (stdio). Default si no se pasa subcomando.")
    p_run.set_defaults(handler="run")

    p_init = sub.add_parser("init", help="Crea una bóveda nueva en <path>.")
    p_init.add_argument("path", help="Ruta donde crear la bóveda (ej: ~/Documents/my-vault)")
    p_init.add_argument("--force", action="store_true", help="Sobreescribir si la ruta no está vacía")
    p_init.set_defaults(handler="init")

    p_doc = sub.add_parser("doctor", help="Verifica el setup (env vars, API key, vault).")
    p_doc.add_argument("path", nargs="?", help="Ruta del vault a verificar (opcional)")
    p_doc.set_defaults(handler="doctor")

    # install-claude — Anthropic Claude Code.
    p_inst = sub.add_parser(
        "install-claude",
        help="Crea el vault si falta y registra el MCP en Claude Code (Anthropic).",
    )
    _add_common_install_flags(p_inst)
    p_inst.add_argument(
        "--scope",
        choices=["user", "local", "project"],
        default="user",
        help="Scope de Claude Code donde registrar el MCP (default: user).",
    )
    p_inst.set_defaults(handler="install-claude")

    # install-codex — OpenAI Codex CLI.
    p_cdx = sub.add_parser(
        "install-codex",
        help="Crea el vault si falta y registra el MCP en Codex CLI (OpenAI).",
    )
    _add_common_install_flags(p_cdx)
    p_cdx.set_defaults(handler="install-codex")

    # install-gemini — Google Gemini CLI.
    p_gem = sub.add_parser(
        "install-gemini",
        help="Crea el vault si falta y registra el MCP en Gemini CLI (Google).",
    )
    _add_common_install_flags(p_gem)
    p_gem.set_defaults(handler="install-gemini")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()

    # Sin args → arrancar server (esto es lo que hace Claude Code al levantar el MCP).
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        from .server import run_server

        run_server()
        return 0

    parsed = parser.parse_args(args)
    handler = getattr(parsed, "handler", None)

    if handler == "init":
        try:
            init_vault(Path(parsed.path), force=parsed.force)
        except (RuntimeError, OSError) as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        _print_next_steps(Path(parsed.path))
        return 0

    if handler == "run":
        from .server import run_server

        run_server()
        return 0

    if handler == "doctor":
        return doctor(Path(parsed.path) if parsed.path else None)

    if handler == "install-claude":
        return install(
            vault=Path(parsed.vault),
            key=parsed.key,
            model=parsed.model,
            scope=parsed.scope,
            name=parsed.name,
            use_local_path=parsed.local,
        )

    if handler == "install-codex":
        return install_codex(
            vault=Path(parsed.vault),
            key=parsed.key,
            model=parsed.model,
            name=parsed.name,
            use_local_path=parsed.local,
        )

    if handler == "install-gemini":
        return install_gemini(
            vault=Path(parsed.vault),
            key=parsed.key,
            model=parsed.model,
            name=parsed.name,
            use_local_path=parsed.local,
        )

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
