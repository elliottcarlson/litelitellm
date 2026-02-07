"""
Minimal litellm shim so middleware (loaded from your project) can import CustomLogger and litellm.acompletion.

Must be installed via install_shim() BEFORE any middleware import.
"""

import sys
import types
from typing import Any


class CustomLogger:
    """Minimal CustomLogger stub matching litellm's interface."""

    def __init__(self, turn_off_message_logging=False, message_logging=True, **kwargs):
        self.message_logging = message_logging
        self.turn_off_message_logging = turn_off_message_logging

    def log_pre_api_call(self, model, messages, kwargs): pass
    def log_post_api_call(self, kwargs, response_obj, start_time, end_time): pass
    def log_stream_event(self, kwargs, response_obj, start_time, end_time): pass
    def log_success_event(self, kwargs, response_obj, start_time, end_time): pass
    def log_failure_event(self, kwargs, response_obj, start_time, end_time): pass

    async def async_log_stream_event(self, kwargs, response_obj, start_time, end_time): pass
    async def async_log_pre_api_call(self, model, messages, kwargs): pass
    async def async_log_success_event(self, kwargs, response_obj, start_time, end_time): pass
    async def async_log_failure_event(self, kwargs, response_obj, start_time, end_time): pass

    async def async_pre_call_hook(self, user_api_key_dict, cache, data, call_type):
        pass

    async def async_post_call_success_hook(self, data, user_api_key_dict, response):
        pass

    async def async_should_run_agentic_loop(self, response, model, messages, tools, stream, custom_llm_provider, kwargs):
        return False, {}

    async def async_run_agentic_loop(self, tools, model, messages, response, anthropic_messages_provider_config, anthropic_messages_optional_request_params, logging_obj, stream, kwargs):
        return response


_acompletion_impl = None


def set_acompletion_impl(fn):
    global _acompletion_impl
    _acompletion_impl = fn


async def acompletion(model, messages, tools=None, **kwargs):
    if _acompletion_impl is None:
        raise RuntimeError("acompletion shim not initialized")
    return await _acompletion_impl(model=model, messages=messages, tools=tools, **kwargs)


def install_shim():
    """Register fake litellm modules in sys.modules."""
    litellm_mod = types.ModuleType("litellm")
    litellm_mod.__path__ = []
    litellm_mod.__package__ = "litellm"
    litellm_mod.acompletion = acompletion

    integrations_mod = types.ModuleType("litellm.integrations")
    integrations_mod.__path__ = []
    integrations_mod.__package__ = "litellm.integrations"

    custom_logger_mod = types.ModuleType("litellm.integrations.custom_logger")
    custom_logger_mod.__package__ = "litellm.integrations"
    custom_logger_mod.CustomLogger = CustomLogger

    core_utils_mod = types.ModuleType("litellm.litellm_core_utils")
    core_utils_mod.__path__ = []
    core_utils_mod.__package__ = "litellm.litellm_core_utils"

    logging_mod = types.ModuleType("litellm.litellm_core_utils.litellm_logging")
    logging_mod.__package__ = "litellm.litellm_core_utils"
    logging_mod.Logging = Any

    sys.modules["litellm"] = litellm_mod
    sys.modules["litellm.integrations"] = integrations_mod
    sys.modules["litellm.integrations.custom_logger"] = custom_logger_mod
    sys.modules["litellm.litellm_core_utils"] = core_utils_mod
    sys.modules["litellm.litellm_core_utils.litellm_logging"] = logging_mod

    print("[litelitellm] Shim installed - litellm modules shimmed")
