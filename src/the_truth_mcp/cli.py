"""CLI: subcomandos del package.

`uv run the-truth-mcp` (sin args)        → corre el server MCP (default).
`uv run the-truth-mcp init <path>`       → crea una bóveda nueva en <path>.
`uv run the-truth-mcp install ...`       → all-in-one: crea vault si falta + registra
                                            el MCP en Claude Code (scope user).
`uv run the-truth-mcp run`               → alias explícito del server.
`uv run the-truth-mcp doctor [<path>]`   → verifica el setup (env vars, key, vault).
`uv run the-truth-mcp --version`         → imprime la versión.
"""

from __future__ import annotations

import argparse
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

    # Reemplazá el placeholder en .mcp.json (y en cualquier otro lugar que aparezca).
    target_str = str(target)
    for path in target.rglob("*"):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if _PLACEHOLDER in text:
            path.write_text(text.replace(_PLACEHOLDER, target_str), encoding="utf-8")

    _print_next_steps(target)


def _print_next_steps(target: Path) -> None:
    print()
    print(f"✓ Bóveda creada en: {target}")
    print()
    print("Próximos pasos:")
    print()
    print("  1. Sacá una API key de Gemini (free tier):")
    print("     https://aistudio.google.com/apikey")
    print()
    print("  2. Exportala en tu shell (o ponela en un .env del repo):")
    print("     export GEMINI_API_KEY=tu-key")
    print()
    print("  3. Abrí la bóveda con Claude Code:")
    print(f"     cd {target}")
    print("     claude")
    print()
    print("     Claude Code va a detectar .mcp.json y te va a preguntar si querés")
    print("     cargar el MCP `the-truth`. Decí que sí.")
    print()
    print("  4. Probá los slash commands:")
    print("     /ingest <url>     guardar info nueva")
    print("     /query <pregunta> consultar la bóveda")
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
        has_agents = (target / "AGENTS.md").is_file()
        has_claude = (target / "CLAUDE.md").is_file()
        all_ok &= _check(
            "AGENTS.md presente",
            has_agents or has_claude,
            detail="(usando CLAUDE.md como fallback)" if has_claude and not has_agents else "",
        )
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


def install(
    vault: Path,
    key: str,
    *,
    model: str = "gemini-2.5-flash",
    scope: str = "user",
    name: str = "the-truth",
    use_local_path: bool = False,
) -> int:
    """All-in-one: crea el vault si falta y registra el MCP en Claude Code.

    Si `use_local_path=True`, usa el código local en lugar de bajar del repo
    público (útil para desarrollo).
    """
    if shutil.which("claude") is None:
        print(
            "error: no se encuentra el ejecutable `claude` en el PATH. "
            "Instalá Claude Code primero: https://claude.com/claude-code",
            file=sys.stderr,
        )
        return 1

    target = vault.expanduser().resolve()

    # Crear el vault si todavía no existe
    if not target.exists() or _is_empty_dir(target):
        print(f"→ Creando bóveda en {target}")
        init_vault(target, force=False)
    else:
        # Validar que parece un vault del MCP (tiene AGENTS.md o CLAUDE.md)
        has_schema = (target / "AGENTS.md").is_file() or (target / "CLAUDE.md").is_file()
        if not has_schema:
            print(
                f"error: {target} existe pero no parece un vault de the-truth-mcp "
                "(falta AGENTS.md). Borralo o usá otro path.",
                file=sys.stderr,
            )
            return 1
        print(f"→ Bóveda existente detectada en {target}")

    # Quitar registro previo (si existe) para no duplicar
    subprocess.run(
        ["claude", "mcp", "remove", "--scope", scope, name],
        capture_output=True,
        check=False,
    )

    # Construir el JSON de config del MCP — usamos `claude mcp add-json` para
    # evitar el parsing ambiguo de `-e VAR=val` con nombres de servers.
    if use_local_path:
        repo_root = str(Path(__file__).resolve().parent.parent.parent)
        spawn_command = "uv"
        spawn_args = ["run", "--directory", repo_root, "the-truth-mcp"]
    else:
        spawn_command = "uvx"
        spawn_args = ["--from", _GIT_REPO, "the-truth-mcp"]

    config = {
        "command": spawn_command,
        "args": spawn_args,
        "env": {
            "VAULT_PATH": str(target),
            "GEMINI_API_KEY": key,
            "GEMINI_MODEL": model,
        },
    }

    print(f"→ Registrando MCP `{name}` en scope {scope}")
    result = subprocess.run(
        ["claude", "mcp", "add-json", "--scope", scope, name, _json.dumps(config)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"error: claude mcp add-json falló:\n{result.stderr}", file=sys.stderr)
        return result.returncode

    print()
    print(f"✓ MCP `{name}` instalado.")
    print(f"  vault: {target}")
    print(f"  modelo: {model}")
    print(f"  scope: {scope}")
    print()
    print("Probalo:")
    print(f"  cd {target}")
    print("  claude")
    print("  # luego dentro de Claude Code:")
    print("  /mcp                 # confirma que `the-truth` está conectado")
    print("  /ingest <url>        # guardar info nueva")
    print("  /query <pregunta>    # consultar la bóveda")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="the-truth-mcp",
        description="MCP server: bóveda LLM Wiki. Claude lee, Gemini ordena.",
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

    p_inst = sub.add_parser(
        "install",
        help="Crea el vault si falta y registra el MCP en Claude Code en un solo paso.",
    )
    p_inst.add_argument(
        "--vault",
        required=True,
        help="Ruta absoluta a la bóveda (ej: ~/Documents/my-vault). Se crea si no existe.",
    )
    p_inst.add_argument(
        "--key",
        required=True,
        help="API key de Gemini (https://aistudio.google.com/apikey). Tier gratis alcanza.",
    )
    p_inst.add_argument(
        "--model",
        default="gemini-2.5-flash",
        help="Modelo de Gemini para el bibliotecario (default: gemini-2.5-flash).",
    )
    p_inst.add_argument(
        "--scope",
        choices=["user", "local", "project"],
        default="user",
        help="Scope de Claude Code donde registrar el MCP (default: user).",
    )
    p_inst.add_argument(
        "--name",
        default="the-truth",
        help="Nombre del MCP server en Claude Code (default: the-truth).",
    )
    p_inst.add_argument(
        "--local",
        action="store_true",
        help="Usar el código local del repo en lugar de uvx desde GitHub (para desarrollo).",
    )
    p_inst.set_defaults(handler="install")

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
        return 0

    if handler == "run":
        from .server import run_server

        run_server()
        return 0

    if handler == "doctor":
        return doctor(Path(parsed.path) if parsed.path else None)

    if handler == "install":
        return install(
            vault=Path(parsed.vault),
            key=parsed.key,
            model=parsed.model,
            scope=parsed.scope,
            name=parsed.name,
            use_local_path=parsed.local,
        )

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
