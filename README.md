# litelitellm

A small, easy-to-run proxy for **LiteLLM local development**. No LiteLLM stack, no database — just a small FastAPI server that reads a **LiteLLM-style config** and loads **your project’s middleware** from the current directory using the same callbacks that LiteLLM provides. Optional **Langfuse** observability is built in.

Use it when you want the same callback/middleware contract as LiteLLM without running the full proxy. Run it from any repo via **uvx**.

## Quick start

**From a project that has a config and middleware:**

1. In your project, add a config file (same format as LiteLLM):

   **config.yaml** (or `proxy_config.yaml`, or set `LITELITELLM_CONFIG` / `LITELLM_CONFIG_PATH`):

   ```yaml
   litellm_settings:
     callbacks: ["my_middleware_loader"]
   ```

2. Ensure your project has a Python file `my_middleware_loader.py` (or whatever name you put in `callbacks`) that exports an object with an `async_pre_call_hook` method (LiteLLM `CustomLogger`-style).

3. From your project directory:

   ```bash
   uvx litelitellm
   ```

   Set `ANTHROPIC_API_KEY` (env or `.env`). Then point your client at the proxy, e.g.:

   ```bash
   ANTHROPIC_BASE_URL=http://localhost:4000 claude
   ```

**From this repo (no middleware):**

```bash
uv sync
cp .env.example .env   # set ANTHROPIC_API_KEY
uv run python -m litelitellm
```

Runs as passthrough only (no config callbacks in this repo).

**Local testing from another folder (before publishing):** From this repo run `uv tool install --editable .`. Then from any other directory you can run `litelitellm` and it will use your local code and that folder’s config. Uninstall when done: `uv tool uninstall litelitellm`.

## Config

Config is read from the **directory you run from** (your project). This repo does not ship a config.

- **Config path:** `LITELITELLM_CONFIG` or `LITELLM_CONFIG_PATH`, then `./config.yaml`, `./config.yml`, `./proxy_config.yaml`, or `./litellm_config.yaml`.
- **Callbacks:** `litellm_settings.callbacks` — list of strings. Each entry is a module name (e.g. `my_middleware_loader`) or `module.attribute`. The module is loaded from the **directory containing the config file** (project root when you run from the project). The first callback that has `async_pre_call_hook` is used as the middleware.

## Environment

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | (none) | Used for outbound requests when middleware modifies the body. |
| `LITELITELLM_PORT` | `4000` | Port the proxy listens on. |
| `ANTHROPIC_API_URL` | `https://api.anthropic.com` | Upstream API. |
| `LANGFUSE_PUBLIC_KEY` | (none) | With `LANGFUSE_SECRET_KEY`, send traces to Langfuse. |
| `LANGFUSE_SECRET_KEY` | (none) | Langfuse secret key. |
| `LANGFUSE_BASE_URL` | `https://cloud.langfuse.com` | Langfuse server (e.g. `http://localhost:3000` for self-hosted). |

## Observability

- One JSON line per request to stdout (latency, tokens, etc.).
- Optional **Langfuse:** set `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` (env or `.env`); if both are set, the proxy sends traces to Langfuse. No extra install. See [LANGFUSE.md](LANGFUSE.md) for setup with Langfuse Cloud or a self-hosted instance.

## License

Use and publish as you like.
