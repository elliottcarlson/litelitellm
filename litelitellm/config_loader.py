"""
Load LiteLLM-style config file and resolve callbacks so litelitellm can run
from any project (e.g. uvx litelitellm) and load that project's local middleware.

Config format matches LiteLLM proxy:
  litellm_settings:
    callbacks: ["my_middleware_loader"]   # or "module.attribute"
"""

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml
except ImportError:
    yaml = None


def find_config_path() -> Optional[Path]:
    """Resolve config file path: env vars first, then standard names in cwd."""
    for env_key in ("LITELITELLM_CONFIG", "LITELLM_CONFIG_PATH", "LITELLM_CONFIG"):
        path = os.environ.get(env_key)
        if path and os.path.isfile(path):
            return Path(path).resolve()
    cwd = Path.cwd()
    for name in ("config.yaml", "config.yml", "proxy_config.yaml", "litellm_config.yaml"):
        p = cwd / name
        if p.is_file():
            return p.resolve()
    return None


def load_config(path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Load YAML config from path (or from find_config_path() if path is None)."""
    if path is None:
        path = find_config_path()
    if path is None or not path.is_file():
        return None
    if yaml is None:
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _get_callbacks(config: Dict[str, Any]) -> List[str]:
    """Return list of callback specifiers from litellm_settings.callbacks."""
    settings = config.get("litellm_settings") or {}
    raw = settings.get("callbacks")
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw]
    return [str(raw)]


def _resolve_callback(spec: str, project_root: Path) -> Optional[Any]:
    """
    Resolve one callback spec to a middleware instance.
    - "module_name.attr_name" -> import module_name, return getattr(module, attr_name)
    - "module_name" -> import module_name, return middleware attr or first with async_pre_call_hook
    """
    project_root_str = str(project_root.resolve())
    if project_root_str not in sys.path:
        sys.path.insert(0, project_root_str)

    if "." in spec:
        module_name, attr_name = spec.split(".", 1)
    else:
        module_name = spec
        attr_name = None

    try:
        import importlib.util
        mod_path = project_root / f"{module_name}.py"
        if not mod_path.is_file():
            return None
        spec_obj = importlib.util.spec_from_file_location(module_name, mod_path)
        if spec_obj is None or spec_obj.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec_obj)
        sys.modules[module_name] = mod
        spec_obj.loader.exec_module(mod)
        if attr_name is not None:
            return getattr(mod, attr_name, None)
        for name in ("skills_middleware", "middleware", module_name):
            obj = getattr(mod, name, None)
            if obj is not None and callable(getattr(obj, "async_pre_call_hook", None)):
                return obj
        for name in dir(mod):
            if name.startswith("_"):
                continue
            obj = getattr(mod, name, None)
            if obj is not None and callable(getattr(obj, "async_pre_call_hook", None)):
                return obj
        return None
    except Exception:
        return None


def load_middleware_from_config(
    config: Optional[Dict[str, Any]] = None,
    config_path: Optional[Path] = None,
    project_root: Optional[Path] = None,
) -> Optional[Any]:
    """
    Load middleware from LiteLLM-style config.
    Returns first successfully resolved callback that has async_pre_call_hook, or None.
    """
    path = config_path or find_config_path()
    if config is None:
        config = load_config(path)
    if not config:
        return None
    callbacks = _get_callbacks(config)
    if not callbacks:
        return None
    root = project_root if project_root is not None else (path.parent if path else Path.cwd())
    for spec in callbacks:
        spec = spec.strip()
        if not spec:
            continue
        middleware = _resolve_callback(spec, root)
        if middleware is not None:
            return middleware
    return None
