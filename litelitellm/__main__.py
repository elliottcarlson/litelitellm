"""
litelitellm entry point.

Usage:
    ANTHROPIC_API_KEY=sk-ant-... python -m litelitellm
    # or from any project with a LiteLLM-style config:
    uvx litelitellm

When a config file is present (config.yaml, proxy_config.yaml, or LITELITELLM_CONFIG),
litelitellm loads callbacks from litellm_settings.callbacks and uses the project's
local middleware. No middleware is bundled; run with a config in your project to load yours.
"""


def main() -> None:
    from pathlib import Path

    from dotenv import load_dotenv

    from litelitellm.config_loader import find_config_path, load_middleware_from_config

    config_path = find_config_path()
    # Load .env from the directory we use for config (project root), so uv tool run from another folder picks it up
    project_dir = config_path.parent if config_path else Path.cwd()
    load_dotenv(project_dir / ".env")

    from litelitellm.shim import install_shim, set_acompletion_impl
    install_shim()
    middleware = load_middleware_from_config(config_path=config_path)
    if middleware is not None:
        print(f"[litelitellm] Middleware loaded from config: {config_path} -> {middleware}")
    else:
        print("[litelitellm] No config or callbacks found - running as passthrough only")
        middleware = None

    from litelitellm.anthropic_client import acompletion_anthropic
    set_acompletion_impl(acompletion_anthropic)

    from litelitellm.server import app
    from litelitellm import config
    import litelitellm.server as server_module

    server_module.middleware = middleware

    if not config.ANTHROPIC_API_KEY:
        print("[litelitellm] WARNING: ANTHROPIC_API_KEY not set!")
        print("[litelitellm]   Set ANTHROPIC_API_KEY for outbound requests (required when middleware modifies requests).")
        print()
        exit(1)

    print(f"[litelitellm] Starting on port {config.LITELITELLM_PORT}")
    print(f"[litelitellm] Anthropic API: {config.ANTHROPIC_API_URL}")
    print()
    print(f"  Set ANTHROPIC_BASE_URL=http://localhost:{config.LITELITELLM_PORT} to route traffic through this proxy")
    print()

    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=config.LITELITELLM_PORT, log_level="info")


if __name__ == "__main__":
    main()
