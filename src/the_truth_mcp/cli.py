"""CLI: subcomandos del package.

`uv run the-truth-mcp` (sin args)        → corre el server MCP (default).
`uv run the-truth-mcp init <path>`       → crea una bóveda nueva en <path>.
`uv run the-truth-mcp run`               → alias explícito del server.
`uv run the-truth-mcp doctor [<path>]`   → verifica el setup (env vars, key, vault).
`uv run the-truth-mcp --version`         → imprime la versión.
"""

from __future__ import annotations

import argparse
import os
import shutil
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
        all_ok &= _check(
            "CLAUDE.md presente", (target / "CLAUDE.md").is_file()
        )
        all_ok &= _check("raw/ presente", (target / "raw").is_dir())
        all_ok &= _check("wiki/ presente", (target / "wiki").is_dir())
        all_ok &= _check(
            "log.md presente", (target / "log.md").is_file()
        )
    else:
        env_vault = os.environ.get("LLM_WIKI_PATH")
        if env_vault:
            print(f"  ℹ  LLM_WIKI_PATH={env_vault} (re-corré con `doctor {env_vault}` para verificar el vault)")
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

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
