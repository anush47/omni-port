import os


def get_port() -> int:
    return int(os.getenv("OMNIPORT_PORT", "7890"))


def get_anthropic_api_key() -> str | None:
    return os.getenv("ANTHROPIC_API_KEY")


def get_env_for_agents() -> dict:
    """Collect all env vars the agent pipeline needs, resolved from process env."""
    env = {k: v for k, v in os.environ.items()}
    return env
