# Langfuse (optional) observability

The proxy logs one JSON line per request to stdout. For a **UI and history**, use [Langfuse](https://langfuse.com) — either **hosted** or **self-hosted**. If both `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` are set (env or `.env`), the proxy sends traces automatically; no extra install.

## Using Langfuse Cloud (hosted)

1. Sign up at [langfuse.com](https://langfuse.com) and create a project.
2. In the project settings, copy the **Public** and **Secret** keys.
3. Set in your environment (or `.env`): `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`. The default `LANGFUSE_BASE_URL` is already `https://cloud.langfuse.com`.
4. Run the proxy (`uvx litelitellm` or `uv run python -m litelitellm`). Traces are sent when the keys are present.

## Self-hosting Langfuse

1. Run Langfuse (e.g. [Docker Compose](https://langfuse.com/docs/self-hosting/deployment/docker-compose)).
2. In the Langfuse UI, create a project and get **Public** and **Secret** keys.
3. Set `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and `LANGFUSE_BASE_URL` (e.g. `http://localhost:3000`).
4. Run the proxy. Traces are sent when the keys are present.

If you don’t set the Langfuse keys, the proxy still logs JSON to stdout; use your own aggregation or scripts.
