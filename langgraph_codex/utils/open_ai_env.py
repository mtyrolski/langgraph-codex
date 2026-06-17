import dataclasses
import os
import pathlib
from collections.abc import MutableMapping

OPEN_AI_SECRET_KEY = "OPEN_AI_SECRET_KEY"
OPEN_AI_KEY_NAME = "OPEN_AI_KEY_NAME"
OPEN_AI_MODEL = "OPEN_AI_MODEL"
DEFAULT_OPENAI_KEY_NAME = "OPENAI_API_KEY"


@dataclasses.dataclass(frozen=True)
class OpenAIEnvironment:
    key_name: str | None
    model: str | None
    secret_key_present: bool
    openai_api_key_present: bool
    env_file_loaded: pathlib.Path | None

    @property
    def authorized(self) -> bool:
        return self.secret_key_present or self.openai_api_key_present


def configure_open_ai_environment(
    env_path: str | pathlib.Path | None = None,
    environ: MutableMapping[str, str] | None = None,
) -> OpenAIEnvironment:
    """Load optional .env values and expose the OpenAI authorization state."""
    target_environ = environ if environ is not None else os.environ
    loaded_path = _load_env_file(env_path=env_path, environ=target_environ)
    secret_value = target_environ.get(OPEN_AI_SECRET_KEY)
    if secret_value and not target_environ.get(DEFAULT_OPENAI_KEY_NAME):
        target_environ[DEFAULT_OPENAI_KEY_NAME] = secret_value

    return OpenAIEnvironment(
        key_name=_none_if_blank(target_environ.get(OPEN_AI_KEY_NAME)),
        model=_none_if_blank(target_environ.get(OPEN_AI_MODEL)),
        secret_key_present=bool(secret_value),
        openai_api_key_present=bool(target_environ.get(DEFAULT_OPENAI_KEY_NAME)),
        env_file_loaded=loaded_path,
    )


def _load_env_file(
    env_path: str | pathlib.Path | None,
    environ: MutableMapping[str, str],
) -> pathlib.Path | None:
    if env_path is None:
        return None

    resolved_path = pathlib.Path(env_path)
    if not resolved_path.exists():
        return None

    for raw_line in resolved_path.read_text(encoding="utf-8").splitlines():
        key, value = _parse_env_line(raw_line)
        if key:
            environ.setdefault(key, value)

    return resolved_path


def _parse_env_line(raw_line: str) -> tuple[str, str]:
    line = raw_line.strip()
    if not line or line.startswith("#") or "=" not in line:
        return "", ""

    key, value = line.split("=", 1)
    return key.strip(), value.strip().strip('"').strip("'")


def _none_if_blank(value: str | None) -> str | None:
    if value is None:
        return None
    stripped_value = value.strip()
    return stripped_value or None
