"""
FastAPI server: /v1/messages proxy to Anthropic with optional middleware from config.
"""

import json
import traceback
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from . import config
from . import observability as obs
from .anthropic_client import (
    AnthropicResponse,
    _request_api_key,
    _request_passthrough_headers,
    call_anthropic,
    stream_to_anthropic,
)

middleware: Any = None

app = FastAPI(title="litelitellm", docs_url=None, redoc_url=None)


def _extract_request_context(request: Request):
    api_key = request.headers.get("x-api-key") or config.ANTHROPIC_API_KEY
    anthropic_version = request.headers.get("anthropic-version", "2023-06-01")
    _skip_headers = {
        "host", "connection", "content-length", "transfer-encoding",
        "accept-encoding", "x-api-key", "anthropic-version", "content-type",
    }
    passthrough_headers: Dict[str, str] = {}
    for k, v in request.headers.items():
        if k.lower() not in _skip_headers:
            passthrough_headers[k] = v
    query_string = str(request.url.query) if request.url.query else ""
    return api_key, anthropic_version, passthrough_headers, query_string


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/v1/messages")
async def messages_endpoint(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": {"type": "invalid_request_error", "message": "Invalid JSON body"}}, status_code=400)

    client_api_key, anthropic_version, passthrough_headers, query_string = _extract_request_context(request)
    if not client_api_key:
        return JSONResponse(
            {"error": {"type": "authentication_error", "message": "No API key provided. Send x-api-key or set ANTHROPIC_API_KEY."}},
            status_code=401,
        )

    is_stream = body.get("stream", False)
    start_time = datetime.now(timezone.utc)
    orig_tool_count = len(body.get("tools", []))
    orig_system = body.get("system")
    data = dict(body)
    middleware_modified = False

    if middleware is not None:
        try:
            result = await middleware.async_pre_call_hook(
                user_api_key_dict=None,
                cache=None,
                data=data,
                call_type="anthropic_messages",
            )
            if result is not None:
                new_tool_count = len(result.get("tools", []))
                middleware_modified = (new_tool_count != orig_tool_count) or (result.get("system") is not orig_system)
                data = result
        except Exception as e:
            print(f"[litelitellm] Middleware pre_call_hook error: {e}")
            traceback.print_exc()

    if middleware_modified and config.ANTHROPIC_API_KEY:
        outbound_api_key = config.ANTHROPIC_API_KEY
        passthrough_headers = _strip_claude_code_headers(passthrough_headers)
    elif middleware_modified and not config.ANTHROPIC_API_KEY:
        print("[litelitellm] WARNING: Middleware modified request but no ANTHROPIC_API_KEY set.")
        outbound_api_key = client_api_key
    else:
        outbound_api_key = client_api_key

    _request_api_key.set(outbound_api_key)
    _request_passthrough_headers.set(passthrough_headers)
    request_id = data.pop("_skills_request_id", None)
    forward_data = {k: v for k, v in data.items() if k not in ("_skills_request_id",)}

    if is_stream:
        async def stream_with_logging():
            err = None
            try:
                async for chunk in stream_to_anthropic(forward_data, outbound_api_key, anthropic_version, passthrough_headers, query_string):
                    yield chunk
                end_time = datetime.now(timezone.utc)
                if middleware is not None and request_id:
                    try:
                        await middleware.async_log_success_event(
                            kwargs={"_skills_request_id": request_id},
                            response_obj=None,
                            start_time=start_time,
                            end_time=end_time,
                        )
                    except Exception:
                        pass
            except Exception as e:
                err = str(e)
                end_time = datetime.now(timezone.utc)
                if middleware is not None and request_id:
                    try:
                        await middleware.async_log_failure_event(
                            kwargs={"_skills_request_id": request_id},
                            response_obj=e,
                            start_time=start_time,
                            end_time=end_time,
                        )
                    except Exception:
                        pass
                yield f"event: error\ndata: {json.dumps({'error': {'type': 'server_error', 'message': err}})}\n\n".encode()
            finally:
                end = datetime.now(timezone.utc)
                obs.record_request(
                    "/v1/messages",
                    data.get("model", ""),
                    (end - start_time).total_seconds(),
                    middleware_modified=middleware_modified,
                    error=err,
                    request_body=data,
                )

        return StreamingResponse(stream_with_logging(), media_type="text/event-stream")

    try:
        raw_response = await call_anthropic(forward_data, outbound_api_key, anthropic_version, passthrough_headers, query_string)
    except Exception as e:
        end_time = datetime.now(timezone.utc)
        if middleware is not None and request_id:
            try:
                await middleware.async_log_failure_event(
                    kwargs={"_skills_request_id": request_id},
                    response_obj=e,
                    start_time=start_time,
                    end_time=end_time,
                )
            except Exception:
                pass
        obs.record_request(
            "/v1/messages",
            data.get("model", ""),
            (end_time - start_time).total_seconds(),
            middleware_modified=middleware_modified,
            error=str(e),
            request_body=data,
        )
        error_msg = str(e)
        status = 502
        if hasattr(e, "response") and hasattr(e.response, "status_code"):
            status = e.response.status_code
            try:
                error_msg = e.response.text
                return JSONResponse(json.loads(error_msg), status_code=status)
            except Exception:
                pass
        return JSONResponse({"error": {"type": "server_error", "message": error_msg}}, status_code=status)

    response_obj = AnthropicResponse(raw_response)

    if middleware is not None:
        try:
            should_run, loop_ctx = await middleware.async_should_run_agentic_loop(
                response=response_obj,
                model=data.get("model", ""),
                messages=data.get("messages", []),
                tools=data.get("tools"),
                stream=False,
                custom_llm_provider="anthropic",
                kwargs={},
            )
            if should_run:
                loop_response = await middleware.async_run_agentic_loop(
                    tools=loop_ctx,
                    model=data.get("model", ""),
                    messages=data.get("messages", []),
                    response=response_obj,
                    anthropic_messages_provider_config=None,
                    anthropic_messages_optional_request_params={k: v for k, v in data.items() if k not in ("messages", "model")},
                    logging_obj=None,
                    stream=False,
                    kwargs={},
                )
                if loop_response is not None:
                    if hasattr(loop_response, "_data"):
                        raw_response = loop_response._data
                    elif hasattr(loop_response, "model_dump"):
                        raw_response = loop_response.model_dump()
                    else:
                        raw_response = loop_response
        except Exception as e:
            print(f"[litelitellm] Agentic loop error: {e}")
            traceback.print_exc()

    end_time = datetime.now(timezone.utc)
    if middleware is not None and request_id:
        try:
            await middleware.async_log_success_event(
                kwargs={"_skills_request_id": request_id},
                response_obj=response_obj,
                start_time=start_time,
                end_time=end_time,
            )
        except Exception:
            pass

    usage = raw_response.get("usage") or {}
    obs.record_request(
        "/v1/messages",
        data.get("model", ""),
        (end_time - start_time).total_seconds(),
        input_tokens=usage.get("input_tokens"),
        output_tokens=usage.get("output_tokens"),
        middleware_modified=middleware_modified,
        request_body=data,
        response_body=raw_response,
    )
    return JSONResponse(raw_response)


@app.api_route("/v1/messages/{subpath:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def messages_subpath_passthrough(subpath: str, request: Request):
    client_api_key, anthropic_version, passthrough_headers, query_string = _extract_request_context(request)
    if not client_api_key:
        return JSONResponse(
            {"error": {"type": "authentication_error", "message": "No API key provided."}},
            status_code=401,
        )
    headers: Dict[str, str] = {}
    headers.update(passthrough_headers)
    headers["x-api-key"] = client_api_key
    headers["anthropic-version"] = anthropic_version
    headers["content-type"] = "application/json"
    url = f"{config.ANTHROPIC_API_URL}/v1/messages/{subpath}"
    if query_string:
        url = f"{url}?{query_string}"
    body = await request.body()
    from .anthropic_client import _get_client
    client = _get_client()
    resp = await client.request(method=request.method, url=url, headers=headers, content=body)
    return JSONResponse(resp.json(), status_code=resp.status_code)


def _strip_claude_code_headers(headers: Dict[str, str]) -> Dict[str, str]:
    cleaned: Dict[str, str] = {}
    for k, v in headers.items():
        lower = k.lower()
        if lower in ("x-app", "anthropic-dangerous-direct-browser-access"):
            continue
        if lower.startswith("x-stainless-"):
            continue
        if lower == "anthropic-beta":
            betas = [b.strip() for b in v.split(",")]
            betas = [b for b in betas if not b.startswith("claude-code-")]
            if betas:
                cleaned[k] = ", ".join(betas)
            continue
        if lower == "user-agent":
            cleaned[k] = "litelitellm/1.0"
            continue
        cleaned[k] = v
    return cleaned
