# litelitellm

<a href="https://pypi.python.org/pypi/litelitellm" target="_blank">
  <img src="https://img.shields.io/pypi/v/litelitellm.svg" alt="PyPi">
</a>

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

**Local testing (before PyPI):** From another folder you can run the GitHub version with `uvx --from git+https://github.com/elliottcarlson/litelitellm litelitellm`. For **editable local dev** (use your local code when you run `litelitellm` from any folder): run `uv tool uninstall litelitellm` (removes the PyPI-installed tool), then from this repo run `uv tool install --editable .`. After that, `litelitellm` uses your local code. When done, `uv tool uninstall litelitellm` and reinstall from PyPI if you like. **Alternative:** from this repo run `uv run litelitellm` (or `uv run python -m litelitellm`) to always run local code without touching the global tool.

## Example: instruction-injection middleware

Here’s a minimal project that injects an instruction so the model always responds like a pirate.

**1. Project layout**

```
my_project/
  config.yaml
  pirate_middleware.py
  .env          # ANTHROPIC_API_KEY=sk-ant-...
```

**2. config.yaml**

```yaml
litellm_settings:
  callbacks: ["pirate_middleware"]
```

**3. pirate_middleware.py**

The middleware must expose an object with `async_pre_call_hook(user_api_key_dict, cache, data, call_type)`. It receives the request `data` (e.g. `model`, `messages`, `system`, `max_tokens`) and returns the modified body.

```python
class PirateMiddleware:
    async def async_pre_call_hook(self, user_api_key_dict, cache, data, call_type):
        # Inject a system instruction so the model responds like a pirate
        prefix = "You are a pirate. Respond only in pirate speak, with 'arr' and nautical terms. "
        existing = data.get("system")
        if existing is None:
            data["system"] = prefix.strip()
        elif isinstance(existing, str):
            data["system"] = prefix + existing
        else:
            # Anthropic can send system as a list of content blocks
            data["system"] = [{"type": "text", "text": prefix}] + list(existing)
        return data

middleware = PirateMiddleware()
```

**4. Run**

```bash
cd my_project
uvx litelitellm
```

Then point your client at `http://localhost:4000` (e.g. `ANTHROPIC_BASE_URL=http://localhost:4000`). Every request will get the pirate instruction applied before being sent to the API.

## Config

Config is read from the **directory you run from** (your project). This repo does not ship a config.

- **Config path:** `LITELITELLM_CONFIG` or `LITELLM_CONFIG_PATH`, then `./config.yaml`, `./config.yml`, `./proxy_config.yaml`, or `./litellm_config.yaml`.
- **Callbacks:** `litellm_settings.callbacks` — list of strings. Each entry is a module name (e.g. `my_middleware_loader`) or `module.attribute`. The module is loaded from the **directory containing the config file** (project root when you run from the project). The first callback that has `async_pre_call_hook` is used as the middleware.

## Environment

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | (none) | Used for outbound requests when middleware modifies the body. |
| `LITELITELLM_HOST` | `0.0.0.0` | Host to bind the proxy to. |
| `LITELITELLM_PORT` | `4000` | Port the proxy listens on. |
| `ANTHROPIC_API_URL` | `https://api.anthropic.com` | Upstream API. |
| `LANGFUSE_PUBLIC_KEY` | (none) | With `LANGFUSE_SECRET_KEY`, send traces to Langfuse. |
| `LANGFUSE_SECRET_KEY` | (none) | Langfuse secret key. |
| `LANGFUSE_BASE_URL` | `https://cloud.langfuse.com` | Langfuse server (e.g. `http://localhost:3000` for self-hosted). |

## Observability

- One JSON line per request to stdout (latency, tokens, etc.).
- Optional **Langfuse:** set `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` (env or `.env`); if both are set, the proxy sends traces to Langfuse. No extra install. See [LANGFUSE.md](LANGFUSE.md) for setup with Langfuse Cloud or a self-hosted instance.

## Publishing (maintainers)

- **Manual:** Bump `version` in `pyproject.toml`, then run `uv build` and `uv publish` (set `UV_PUBLISH_TOKEN` or use `uv publish` and enter token when prompted).
- **GitHub Action:** The [Publish to PyPI](.github/workflows/publish.yml) workflow is manually triggerable (Actions → Publish to PyPI → Run workflow). Add a repository secret `PYPI_API_TOKEN` with your PyPI API token (pypi.org → Account → API tokens).

## License

MIT. See [LICENSE](LICENSE).
