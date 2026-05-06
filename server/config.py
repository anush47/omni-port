import os
from typing import Any

# Mutable runtime config — updated via POST /api/v1/config without restarting the server.
# Values here take precedence over the .env file.
_runtime: dict[str, Any] = {}


def update_runtime_config(data: dict[str, Any]) -> None:
    """Apply config pushed from the extension panel and propagate into os.environ."""
    _runtime.update(data)

    provider = data.get("provider", "")
    if provider == "azure":
        if key := data.get("azure_api_key"):
            os.environ["AZURE_OPENAI_API_KEY"] = key
        if ep := data.get("azure_endpoint"):
            os.environ["AZURE_OPENAI_ENDPOINT"] = ep
        if ver := data.get("azure_api_version"):
            os.environ["OPENAI_API_VERSION"] = ver
        os.environ.pop("OPENAI_API_KEY", None)
    elif provider == "openai":
        if key := data.get("openai_api_key"):
            os.environ["OPENAI_API_KEY"] = key
        if base := data.get("openai_base_url"):
            os.environ["OPENAI_BASE_URL"] = base
        os.environ.pop("AZURE_OPENAI_API_KEY", None)
        os.environ.pop("AZURE_OPENAI_ENDPOINT", None)

    for env_var, field in [
        ("FAST_MODEL_NAME",      "fast_model"),
        ("BALANCED_MODEL_NAME",  "balanced_model"),
        ("REASONING_MODEL_NAME", "reasoning_model"),
    ]:
        if val := data.get(field):
            os.environ[env_var] = val

    if url := data.get("microservices_url"):
        os.environ["OMNIPORT_MICROSERVICES_URL"] = url


def get_microservices_url() -> str:
    return (
        _runtime.get("microservices_url")
        or os.getenv("OMNIPORT_MICROSERVICES_URL", "http://localhost:8080")
    )


def get_port() -> int:
    return int(os.getenv("OMNIPORT_PORT", "7890"))


def get_env_for_agents() -> dict:
    return {k: v for k, v in os.environ.items()}
