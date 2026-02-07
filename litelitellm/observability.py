"""
Lightweight request metrics and optional Langfuse tracing.
"""

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional


def record_request(
    endpoint: str,
    model: str,
    latency_seconds: float,
    *,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    middleware_modified: bool = False,
    error: Optional[str] = None,
    request_body: Optional[Dict[str, Any]] = None,
    response_body: Optional[Dict[str, Any]] = None,
) -> None:
    payload: Dict[str, Any] = {
        "event": "proxy_request",
        "endpoint": endpoint,
        "model": model,
        "latency_seconds": round(latency_seconds, 4),
        "middleware_modified": middleware_modified,
    }
    if input_tokens is not None:
        payload["input_tokens"] = input_tokens
    if output_tokens is not None:
        payload["output_tokens"] = output_tokens
    if error:
        payload["error"] = error
    print(json.dumps(payload))

    _send_langfuse(
        endpoint=endpoint,
        model=model,
        latency_seconds=latency_seconds,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        middleware_modified=middleware_modified,
        error=error,
        request_body=request_body,
        response_body=response_body,
    )


def _send_langfuse(
    endpoint: str,
    model: str,
    latency_seconds: float,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    middleware_modified: bool = False,
    error: Optional[str] = None,
    request_body: Optional[Dict[str, Any]] = None,
    response_body: Optional[Dict[str, Any]] = None,
) -> None:
    from . import config
    if not config.LANGFUSE_SECRET_KEY or not config.LANGFUSE_PUBLIC_KEY:
        return
    host = (config.LANGFUSE_BASE_URL or "").rstrip("/")
    if not host:
        return

    metadata: Dict[str, str] = {
        "endpoint": endpoint,
        "model": model,
        "latency_seconds": str(round(latency_seconds, 4)),
        "middleware_modified": str(middleware_modified).lower(),
    }
    if input_tokens is not None:
        metadata["input_tokens"] = str(input_tokens)
    if output_tokens is not None:
        metadata["output_tokens"] = str(output_tokens)
    if error is not None:
        metadata["error"] = error

    trace_input: Any = request_body if request_body is not None else {"endpoint": endpoint, "model": model}
    trace_output_meta: Dict[str, Any] = {
        "latency_seconds": round(latency_seconds, 4),
        "middleware_modified": middleware_modified,
    }
    if input_tokens is not None:
        trace_output_meta["input_tokens"] = input_tokens
    if output_tokens is not None:
        trace_output_meta["output_tokens"] = output_tokens
    if error is not None:
        trace_output_meta["error"] = error
    trace_output: Any = response_body if response_body is not None else trace_output_meta

    try:
        import httpx
        trace_id = str(uuid.uuid4())
        event_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        ts = now.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        start_dt = now - timedelta(seconds=latency_seconds)
        start_ts = start_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")

        trace_event = {
            "type": "trace-create",
            "id": event_id,
            "timestamp": ts,
            "body": {
                "id": trace_id,
                "timestamp": ts,
                "name": "litelitellm_request",
                "metadata": metadata,
                "input": trace_input,
                "output": trace_output,
            },
        }

        gen_id = str(uuid.uuid4())
        gen_event_id = str(uuid.uuid4())
        gen_body: Dict[str, Any] = {
            "id": gen_id,
            "traceId": trace_id,
            "name": "litelitellm_request",
            "startTime": start_ts,
            "endTime": ts,
            "model": model,
            "input": trace_input,
            "output": trace_output,
        }
        if input_tokens is not None or output_tokens is not None:
            gen_body["usage"] = {
                "promptTokens": input_tokens or 0,
                "completionTokens": output_tokens or 0,
            }
        generation_event = {"type": "generation-create", "id": gen_event_id, "timestamp": ts, "body": gen_body}

        with httpx.Client(timeout=10.0) as client:
            resp = client.post(
                f"{host}/api/public/ingestion",
                json={"batch": [trace_event, generation_event]},
                auth=(config.LANGFUSE_PUBLIC_KEY, config.LANGFUSE_SECRET_KEY),
            )
            resp.raise_for_status()
    except Exception as e:
        print(f"[litelitellm] Langfuse trace failed: {e}", flush=True)
