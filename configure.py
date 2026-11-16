#!/usr/bin/env python3
"""One-time AvalAI → OpenCode configuration helper.

This script uses only Python's standard library. It:
- reads an AvalAI key from .env, the shell environment, or a hidden prompt;
- asks the user to choose one official AvalAI API route;
- fetches AvalAI's authenticated GET /v1/models catalog;
- adds or refreshes only providers.avalai in OpenCode's global config;
- accepts existing JSON or JSONC config (comments and trailing commas);
- creates an exact-content backup before replacing the config.

Official documentation:
- https://docs.avalai.ir/en/api-reference/authentication
- https://docs.avalai.ir/en/api-reference/models
- https://docs.avalai.ir/en/news/2025-06-15-expanded-api-access-domains
- https://opencode.ai/docs/providers/
- https://opencode.ai/docs/config/
- https://opencode.ai/config.json
"""

from __future__ import annotations

import copy
import getpass
import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

PROJECT_DIR = Path(__file__).resolve().parent
DOTENV_PATH = PROJECT_DIR / ".env"
CONFIG_DIR = Path.home() / ".config" / "opencode"
SCHEMA_URL = "https://opencode.ai/config.json"
PROVIDER_ID = "avalai"
TIMEOUT_SECONDS = 20

# AvalAI's officially documented API routes.
OFFICIAL_ROUTES = {
    "1": ("Primary Iran route", "https://api.avalai.ir"),
    "2": ("Iran fallback route", "https://api.avalapis.ir"),
    "3": ("Cloudflare route", "https://api.avalai.org"),
}

PLACEHOLDER_VALUES = {
    "paste-your-avalai-api-key-here",
    "your-avalai-api-key",
    "your-api-key",
    "your-key",
    "changeme",
}


class SetupError(RuntimeError):
    """An expected, user-facing setup error."""


class DuplicateKeyError(ValueError):
    """Raised when a JSON/JSONC object contains the same key twice."""


class HttpStatusError(SetupError):
    def __init__(self, url: str, status: int, body: str) -> None:
        self.url = url
        self.status = status
        self.body = body
        super().__init__(f"HTTP {status} from {url}")


def parse_dotenv_value(raw: str, line_number: int) -> str:
    """Parse one small, predictable dotenv value without executing shell code."""
    value = raw.strip()
    if not value:
        return ""

    if value[0] in {"'", '"'}:
        quote = value[0]
        escaped = False
        closing_index: int | None = None
        for index in range(1, len(value)):
            char = value[index]
            if quote == '"' and char == "\\" and not escaped:
                escaped = True
                continue
            if char == quote and not escaped:
                closing_index = index
                break
            escaped = False

        if closing_index is None:
            raise SetupError(f"{DOTENV_PATH}:{line_number} has an unclosed quote")

        tail = value[closing_index + 1 :].strip()
        if tail and not tail.startswith("#"):
            raise SetupError(
                f"{DOTENV_PATH}:{line_number} has unexpected text after the value"
            )

        inner = value[1:closing_index]
        if quote == "'":
            return inner

        # Support the small escape set developers commonly use in .env files.
        replacements = {
            r"\\": "\\",
            r'\"': '"',
            r"\n": "\n",
            r"\r": "\r",
            r"\t": "\t",
        }
        for source, target in replacements.items():
            inner = inner.replace(source, target)
        return inner

    # Unquoted values may end with a whitespace-delimited comment.
    match = re.search(r"\s+#", value)
    if match:
        value = value[: match.start()].rstrip()
    return value


def read_dotenv_key(path: Path) -> str | None:
    if not path.exists():
        return None

    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as error:
        raise SetupError(f"Could not read {path}: {error}") from error

    found: str | None = None
    for line_number, original_line in enumerate(text.splitlines(), start=1):
        line = original_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue

        name, raw_value = line.split("=", 1)
        if name.strip() != "AVALAI_API_KEY":
            continue
        if found is not None:
            raise SetupError(f"{path} defines AVALAI_API_KEY more than once")
        found = parse_dotenv_value(raw_value, line_number)

    return found


def clean_api_key(value: str) -> str:
    # API keys are one-line credentials. Removing accidental surrounding
    # whitespace fixes the most common copy/paste issue without changing the key.
    return value.strip().lstrip("\ufeff")


def validate_api_key(api_key: str, source: str) -> None:
    if not api_key:
        raise SetupError(f"The API key from {source} is empty")
    if "\n" in api_key or "\r" in api_key:
        raise SetupError(f"The API key from {source} contains a newline")
    if api_key.lower() in PLACEHOLDER_VALUES or "paste-your" in api_key.lower():
        raise SetupError(
            f"{source} still contains the example placeholder, not a real AvalAI API key"
        )


def choose_api_key() -> tuple[str, str]:
    dotenv_key_raw = read_dotenv_key(DOTENV_PATH)
    shell_key_raw = os.environ.get("AVALAI_API_KEY")

    dotenv_key = clean_api_key(dotenv_key_raw) if dotenv_key_raw is not None else None
    shell_key = clean_api_key(shell_key_raw) if shell_key_raw is not None else None

    if dotenv_key and shell_key and dotenv_key != shell_key:
        print("\n⚠️  Two different AvalAI keys were found")
        print(f"  1) Project .env — {DOTENV_PATH} (default)")
        print("  2) Shell environment — AVALAI_API_KEY")
        choice = input("👉 Which key should this run use? [1]: ").strip() or "1"
        if choice == "1":
            api_key, source = dotenv_key, str(DOTENV_PATH)
        elif choice == "2":
            api_key, source = shell_key, "shell environment"
        else:
            raise SetupError("Please choose 1 or 2")
    elif dotenv_key:
        api_key, source = dotenv_key, str(DOTENV_PATH)
    elif shell_key:
        api_key, source = shell_key, "shell environment"
    else:
        api_key = clean_api_key(
            getpass.getpass("\n🔑 Paste your AvalAI API key (hidden): ")
        )
        source = "hidden prompt"

    validate_api_key(api_key, source)
    print(f"\n🔐 Using AVALAI_API_KEY from {source}")
    print(f"   Key length: {len(api_key)} characters (the key itself is never printed)")
    return api_key, source


def choose_route() -> tuple[str, str]:
    print("\n🌐 Choose an official AvalAI route")
    print("  1) Primary Iran route — api.avalai.ir (default)")
    print("  2) Iran fallback route — api.avalapis.ir")
    print("  3) Cloudflare route — api.avalai.org")
    choice = input("👉 Choice [1]: ").strip() or "1"

    if choice not in OFFICIAL_ROUTES:
        raise SetupError("Please choose 1, 2, or 3")

    label, root = OFFICIAL_ROUTES[choice]
    print(f"\n🚦 Using {label}: {root}/v1")
    return label, root


def safe_server_message(body: str) -> str | None:
    """Extract a short server error without ever including request credentials."""
    body = body.strip()
    if not body:
        return None

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return body[:300].replace("\n", " ")

    candidates: list[Any] = []
    if isinstance(payload, dict):
        candidates.extend([payload.get("message"), payload.get("detail")])
        error = payload.get("error")
        if isinstance(error, dict):
            candidates.extend([error.get("message"), error.get("detail"), error.get("code")])
        elif isinstance(error, str):
            candidates.append(error)

    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()[:300].replace("\n", " ")
    return None


def request_models(root: str, api_key: str) -> tuple[list[dict[str, Any]], float]:
    """Call AvalAI's documented OpenAI-format GET /v1/models endpoint."""
    url = f"{root.rstrip('/')}/v1/models"
    request = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "avalai-opencode-helper/1.1",
        },
    )
    started = time.monotonic()

    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            raw = response.read()
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")[:2000]
        raise HttpStatusError(url, error.code, body) from error
    except urllib.error.URLError as error:
        raise SetupError(f"Could not reach {url}: {error.reason}") from error
    except TimeoutError as error:
        raise SetupError(f"Timed out after {TIMEOUT_SECONDS}s while connecting to {url}") from error

    elapsed = time.monotonic() - started

    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SetupError(f"{url} did not return valid JSON") from error

    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise SetupError(f"{url} returned an unexpected model-list format")

    records = [item for item in payload["data"] if isinstance(item, dict)]
    return records, elapsed


def fetch_catalog(root: str, api_key: str, key_source: str) -> list[dict[str, Any]]:
    print("\n📡 Asking AvalAI for its authenticated model catalog…")
    try:
        records, elapsed = request_models(root, api_key)
    except HttpStatusError as error:
        message = safe_server_message(error.body)
        if error.status == 401:
            details = [
                "AvalAI returned HTTP 401 Unauthorized.",
                f"Key source: {key_source}",
                f"Endpoint: {error.url}",
                "The helper sent the key as an Authorization: Bearer header.",
                "Check that the key is active, complete, and not the example placeholder.",
            ]
            if message:
                details.append(f"AvalAI message: {message}")
            raise SetupError("\n".join(details)) from error
        if error.status == 403:
            details = [
                "AvalAI returned HTTP 403 Forbidden.",
                "The key was recognized, but this request is not allowed for the account/key.",
                f"Endpoint: {error.url}",
            ]
            if message:
                details.append(f"AvalAI message: {message}")
            raise SetupError("\n".join(details)) from error

        details = [f"AvalAI returned HTTP {error.status} from {error.url}."]
        if message:
            details.append(f"AvalAI message: {message}")
        raise SetupError("\n".join(details)) from error

    print(f"✅ Received {len(records)} catalog entries in {elapsed:.2f}s")
    return records


def positive_number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        return None
    return value


def record_metadata(record: dict[str, Any]) -> dict[str, Any]:
    """Use documented top-level metadata, with nested detail-response support."""
    extra = record.get("extra")
    if isinstance(extra, dict):
        metadata = extra.get("metadata")
        if isinstance(metadata, dict):
            merged = dict(record)
            merged.update(metadata)
            return merged
    return record


def build_model_map(records: list[dict[str, Any]]) -> tuple[dict[str, Any], int]:
    """Translate documented AvalAI chat metadata into OpenCode schema fields."""
    models: dict[str, Any] = {}
    skipped = 0

    for raw_record in sorted(records, key=lambda item: str(item.get("id", "")).lower()):
        record = record_metadata(raw_record)
        model_id = record.get("id")
        mode = record.get("mode")

        if not isinstance(model_id, str) or not model_id.strip():
            skipped += 1
            continue
        model_id = model_id.strip()

        # OpenCode is a coding/chat agent. Other AvalAI modes use different APIs.
        if mode != "chat":
            skipped += 1
            continue

        owner = record.get("owned_by")
        display_name = (
            model_id
            if not isinstance(owner, str) or not owner.strip()
            else f"{model_id} · {owner.strip()}"
        )
        model: dict[str, Any] = {"name": display_name}

        tool_call = record.get("supports_function_calling")
        if isinstance(tool_call, bool):
            model["capabilities"] = {"tools": tool_call}

        context = positive_number(record.get("max_input_tokens"))
        output = positive_number(record.get("max_output_tokens"))
        if context is not None and output is not None:
            model["limit"] = {"context": context, "output": output}

        pricing = record.get("pricing")
        if isinstance(pricing, dict):
            input_cost = positive_number(pricing.get("input"))
            output_cost = positive_number(pricing.get("output"))
            if input_cost is not None and output_cost is not None:
                cost: dict[str, Any] = {"input": input_cost, "output": output_cost}
                cache_read = positive_number(pricing.get("cached_input"))
                if cache_read is not None:
                    cost["cache"] = {"read": cache_read}
                model["cost"] = cost

        models[model_id] = model

    return models, skipped


def strip_jsonc_comments(text: str) -> str:
    """Remove // and /* */ comments while preserving strings and line numbers."""
    output: list[str] = []
    index = 0
    in_string = False
    escaped = False

    while index < len(text):
        char = text[index]

        if in_string:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue

        if char == '"':
            in_string = True
            output.append(char)
            index += 1
            continue

        if char == "/" and index + 1 < len(text):
            next_char = text[index + 1]
            if next_char == "/":
                output.extend("  ")
                index += 2
                while index < len(text) and text[index] not in "\r\n":
                    output.append(" ")
                    index += 1
                continue
            if next_char == "*":
                output.extend("  ")
                index += 2
                closed = False
                while index < len(text):
                    if index + 1 < len(text) and text[index] == "*" and text[index + 1] == "/":
                        output.extend("  ")
                        index += 2
                        closed = True
                        break
                    output.append(text[index] if text[index] in "\r\n" else " ")
                    index += 1
                if not closed:
                    raise SetupError("The OpenCode config contains an unclosed /* comment */")
                continue

        output.append(char)
        index += 1

    return "".join(output)


def strip_trailing_commas(text: str) -> str:
    """Remove commas immediately before } or ] outside JSON strings."""
    output: list[str] = []
    index = 0
    in_string = False
    escaped = False

    while index < len(text):
        char = text[index]

        if in_string:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue

        if char == '"':
            in_string = True
            output.append(char)
            index += 1
            continue

        if char == ",":
            lookahead = index + 1
            while lookahead < len(text) and text[lookahead].isspace():
                lookahead += 1
            if lookahead < len(text) and text[lookahead] in "}]":
                # Preserve character position approximately for useful parser locations.
                output.append(" ")
                index += 1
                continue

        output.append(char)
        index += 1

    return "".join(output)


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError(key)
        result[key] = value
    return result


def parse_json_or_jsonc(text: str, path: Path) -> dict[str, Any]:
    # An empty file is a common result of `touch opencode.json`, an interrupted
    # editor session, or a previous failed setup. Treat it as a blank config.
    # The same applies to a file that contains only JSONC comments.
    normalized = text.lstrip("\ufeff")
    if not normalized.strip():
        return {}

    normalized = strip_jsonc_comments(normalized)
    if not normalized.strip():
        return {}

    normalized = strip_trailing_commas(normalized)

    try:
        value = json.loads(
            normalized,
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=lambda constant: (_ for _ in ()).throw(
                ValueError(f"Unsupported JSON constant: {constant}")
            ),
        )
    except DuplicateKeyError as error:
        raise SetupError(
            f'{path} contains the duplicate key "{error.args[0]}". '
            "The helper will not guess which value should win."
        ) from error
    except (json.JSONDecodeError, ValueError) as error:
        if isinstance(error, json.JSONDecodeError):
            location = f"line {error.lineno}, column {error.colno}"
            reason = error.msg
        else:
            location = "an unknown location"
            reason = str(error)
        raise SetupError(
            f"{path} is not valid JSON/JSONC ({location}: {reason}). "
            "No config file was changed."
        ) from error

    if not isinstance(value, dict):
        raise SetupError(f"{path} must contain a JSON object at the top level")
    return value


def select_config_path(directory: Path) -> Path:
    """Update an existing config; prefer JSONC and use it for new setups."""
    jsonc = directory / "opencode.jsonc"
    if jsonc.exists():
        return jsonc
    json_path = directory / "opencode.json"
    return json_path if json_path.exists() else jsonc


def load_existing_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}

    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as error:
        raise SetupError(f"Could not read {path}: {error}") from error
    return parse_json_or_jsonc(text, path)


def config_without_avalai(config: dict[str, Any]) -> dict[str, Any]:
    """Return a comparison snapshot that ignores only providers.avalai.

    Adding the first provider necessarily creates the parent `providers` object.
    An empty parent object is therefore normalized away in the snapshot so a
    previously blank config still passes the unrelated-settings safety check.
    """
    snapshot = copy.deepcopy(config)
    providers = snapshot.get("providers")
    if isinstance(providers, dict):
        providers.pop(PROVIDER_ID, None)
        if not providers:
            snapshot.pop("providers", None)
    return snapshot


def choose_key_storage() -> str:
    print("\n🔐 How should OpenCode read the AvalAI key?")
    print("  1) Environment variable — {env:AVALAI_API_KEY} (recommended)")
    print("  2) Hard-code it in the OpenCode config (simpler, but less secure)")
    choice = input("👉 Choice [1]: ").strip() or "1"
    if choice not in {"1", "2"}:
        raise SetupError("Please choose 1 or 2")
    return "env" if choice == "1" else "hardcode"


def unique_backup_path(path: Path) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    candidate = path.with_name(f"{path.name}.backup-{stamp}")
    counter = 1
    while candidate.exists():
        candidate = path.with_name(f"{path.name}.backup-{stamp}-{counter}")
        counter += 1
    return candidate


def write_config(config: dict[str, Any], path: Path) -> Path | None:
    path.parent.mkdir(parents=True, exist_ok=True)
    backup: Path | None = None

    if path.exists():
        backup = unique_backup_path(path)
        shutil.copyfile(path, backup)
        os.chmod(backup, 0o600)

    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        temporary.write_text(
            json.dumps(config, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        os.chmod(temporary, 0o600)
        # Parse the exact bytes we are about to install before replacing anything.
        json.loads(temporary.read_text(encoding="utf-8"))
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        if temporary.exists():
            temporary.unlink()

    return backup


def main() -> int:
    print("👋 AvalAI → OpenCode one-time helper")
    print("   No package install. No daemon. No hard-coded model list.")

    api_key, key_source = choose_api_key()
    _, root = choose_route()
    catalog = fetch_catalog(root, api_key, key_source)
    models, skipped = build_model_map(catalog)

    if not models:
        raise SetupError("AvalAI returned no entries explicitly marked as mode=chat")

    print(f"\n📚 Preparing {len(models)} AvalAI chat models for OpenCode")
    if skipped:
        print(f"   ℹ️ Skipped {skipped} non-chat or incomplete catalog entries")

    key_storage = choose_key_storage()

    config_path = select_config_path(CONFIG_DIR)
    config_existed = config_path.exists()
    config = load_existing_config(config_path)
    if not config_existed:
        config["$schema"] = SCHEMA_URL
    preserved_before = config_without_avalai(config)

    providers = config.setdefault("providers", {})
    if not isinstance(providers, dict):
        raise SetupError('The existing "providers" setting is not a JSON object')

    api_key_setting = "{env:AVALAI_API_KEY}" if key_storage == "env" else api_key
    providers[PROVIDER_ID] = {
        "package": "@opencode/ai/providers/openai-compatible",
        "name": "AvalAI",
        "settings": {
            "baseURL": f"{root.rstrip('/')}/v1",
            "apiKey": api_key_setting,
        },
        "models": models,
    }

    # Defensive invariant: everything except providers.avalai must be identical.
    if config_without_avalai(config) != preserved_before:
        raise SetupError(
            "Internal safety check failed: an unrelated OpenCode setting changed. "
            "Nothing was written."
        )

    backup = write_config(config, config_path)

    print(f"\n✅ OpenCode configured: {config_path}")
    print("🧩 Only providers.avalai was added or replaced")
    print("🔒 The resulting config is readable only by your user (mode 0600)")
    if backup:
        print(f"💾 Exact original backup: {backup}")
    else:
        print("💾 No backup was needed because the config did not exist yet")

    if key_storage == "env":
        print("\n🌱 OpenCode now expects AVALAI_API_KEY in its environment")
        if DOTENV_PATH.exists():
            print("   From this project folder, launch it with:")
            print("   set -a; . ./.env; set +a; opencode")
        else:
            print("   Example:")
            print("   export AVALAI_API_KEY='your-real-key'")
            print("   opencode")
    else:
        print(f"\n⚠️  The AvalAI key is stored directly in {config_path.name}")
        print("   Keep that file and its backups private")

    print("\n🚀 In OpenCode:")
    print("   1. Run: /models")
    print("   2. Search for: AvalAI")
    print("\n🔁 Run ./run.sh again whenever you want to refresh the catalog")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n\n👋 Cancelled. No further changes were made", file=sys.stderr)
        raise SystemExit(130)
    except SetupError as error:
        print(f"\n❌ {error}", file=sys.stderr)
        raise SystemExit(1)
