"""Read CC Switch's saved usage scripts without modifying its database."""
import json
import errno
import hashlib
import math
import os
import re
import shutil
import sqlite3
import subprocess
import tomllib
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

APPS = ("claude", "codex")
DEFAULT_DB = Path.home() / ".cc-switch" / "cc-switch.db"
DIRECTORY = Path(__file__).resolve().parent
BEIJING = timezone(timedelta(hours=8))


class QueryError(Exception):
    pass


def list_providers(db_path):
    try:
        with closing(sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True, timeout=1)) as con:
            rows = con.execute("SELECT id,app_type,name,meta FROM providers WHERE app_type IN ('claude','codex') ORDER BY name,id").fetchall()
        result = {app: [] for app in APPS}
        for pid, app, name, raw in rows:
            try:
                script = json.loads(raw).get("usage_script", {})
                enabled = script.get("enabled") is True and bool(script.get("code"))
            except (ValueError, AttributeError, TypeError):
                enabled = False
            result[app].append({"id": pid, "name": name, "enabled": enabled})
        return result
    except Exception as exc:
        raise QueryError("Cannot read provider list; check database path, schema or lock") from exc


def load_provider(db_path, app, provider_id=None):
    if app not in APPS:
        raise QueryError("Unsupported application")
    try:
        with closing(sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True, timeout=1)) as con:
            rows = con.execute(
                "SELECT id, settings_config, meta FROM providers WHERE app_type=? AND "
                + ("id=?" if provider_id is not None else "name=?"),
                (app, provider_id if provider_id is not None else "OpenRouter ICU"),
            ).fetchall()
        if len(rows) != 1:
            raise QueryError("Provider missing or ambiguous; select a data source for " + app)
        pid, raw_settings, raw_meta = rows[0]
        settings, meta = json.loads(raw_settings), json.loads(raw_meta)
        script = meta.get("usage_script", {})
        if script.get("enabled") is not True or not isinstance(script.get("code"), str) or not script["code"].strip():
            raise QueryError("CC Switch usage script is disabled or missing")
        if script.get("language", "javascript").lower() != "javascript":
            raise QueryError("Only JavaScript usage scripts are supported")
        if app == "claude":
            env = settings.get("env", {})
            base = env.get("ANTHROPIC_BASE_URL", "")
            key = env.get("ANTHROPIC_AUTH_TOKEN") or env.get("ANTHROPIC_API_KEY", "")
        else:
            cfg = tomllib.loads(settings.get("config", ""))
            selected = cfg.get("model_provider", "")
            base = cfg.get("model_providers", {}).get(selected, {}).get("base_url", "") or cfg.get("base_url", "")
            key = settings.get("auth", {}).get("OPENAI_API_KEY", "")
        base = str(script.get("baseUrl") or script.get("base_url") or base).strip().rstrip("/")
        key = str(script.get("apiKey") or script.get("api_key") or key).strip()
        if not base or not key:
            raise QueryError("Missing provider endpoint or key")
        return {"provider_id": pid, "code": script["code"], "baseUrl": base, "apiKey": key,
                "accessToken": script.get("accessToken") or script.get("access_token"),
                "userId": script.get("userId") or script.get("user_id"),
                "timeout": max(1, min(30, int(script.get("timeout") or 10)))}
    except QueryError:
        raise
    except Exception as exc:
        raise QueryError("Could not read CC Switch provider configuration") from exc


def finite_amount(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def usd_remaining(data):
    if isinstance(data, list) and len(data) == 1:
        data = data[0]
    if not isinstance(data, dict) or str(data.get("unit", "")).upper() != "USD":
        raise QueryError("Expected one USD balance from CC Switch extractor")
    value = data.get("remaining")
    if not finite_amount(value):
        raise QueryError("Extractor returned no finite remaining balance")
    return float(value)


def query(app, db_path=DEFAULT_DB, provider_id=None):
    provider = load_provider(db_path, app, provider_id)
    node = shutil.which("node") or str(Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "nodejs/node.exe")
    try:
        result = subprocess.run(
            [node, str(DIRECTORY / "usage_runner.cjs")],
            input=json.dumps(provider), text=True, encoding="utf-8",
            capture_output=True, timeout=provider["timeout"] + 5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode:
            errors = {
                "ORIGIN": "Usage request must be same-origin HTTPS without redirects",
                "METHOD": "Only read-only GET usage requests are supported",
                "HTTP": "Usage request returned an HTTP error",
                "NETWORK": "Usage request failed or timed out",
                "SCRIPT": "Usage script or extractor is not compatible",
                "SIZE": "Usage response exceeded size limit",
            }
            raise QueryError(errors.get(result.stderr.strip(), "CC Switch usage query failed"))
        value = usd_remaining(json.loads(result.stdout))
        return {"value": value, "provider_id": provider["provider_id"]}
    except QueryError:
        raise
    except Exception as exc:
        raise QueryError("Usage runner unavailable or timed out") from exc


def query_all(db_path=DEFAULT_DB, providers=None):
    results = {}
    for app in APPS:
        try:
            results[app] = query(app, db_path, (providers or {}).get(app))
        except Exception as exc:
            results[app] = {"error": str(exc) if isinstance(exc, QueryError) else "Query failed"}
    return results


def merge_results(state, results):
    for app in APPS:
        result = results.get(app, {})
        if "value" in result:
            value = usd_remaining({"unit": "USD", "remaining": result["value"]})
            state["balances"][app] = value
            state.setdefault("last_success", {})[app] = datetime.now().isoformat(timespec="seconds")
            state.setdefault("provider_ids", {})[app] = result["provider_id"]
            if "sources" in state:
                state["sources"]["providers"][app] = result["provider_id"]
                key = cache_key(state["sources"], app)
                state.setdefault("cache", {})[key] = {
                    "value": value, "last_success": state["last_success"][app]}
        state.setdefault("errors", {})[app] = result.get("error")


def valid_reset(value):
    return isinstance(value, str) and re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d", value) is not None


def countdown(reset, now=None):
    now = now or datetime.now(BEIJING)
    now = now.replace(tzinfo=BEIJING) if now.tzinfo is None else now.astimezone(BEIJING)
    target = datetime.combine(now.date(), datetime.strptime(reset, "%H:%M:%S").time(), tzinfo=BEIJING)
    if target <= now:
        target += timedelta(days=1)
    seconds = math.ceil((target - now).total_seconds())
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def load_state(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            data = {}
    except (OSError, ValueError):
        data = {}
    state = default_state()
    if valid_reset(data.get("reset")):
        state["reset"] = data["reset"]
    color = data.get("color")
    state["color"] = color.lower() if isinstance(color, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", color) else "#ff3030"
    position = data.get("position")
    if not isinstance(position, list) or len(position) != 2 or not all(type(x) is int for x in position):
        position = None
    state["position"] = position
    state["topmost"] = data.get("topmost", True) is not False
    cache = data.get("cache") if isinstance(data.get("cache"), dict) else {}
    state["cache"] = {
        key: {"value": entry["value"], "last_success": entry.get("last_success", "")}
        for key, entry in cache.items()
        if isinstance(key, str) and re.fullmatch(r"[0-9a-f]{64}", key)
        and isinstance(entry, dict) and finite_amount(entry.get("value"))
        and isinstance(entry.get("last_success", ""), str)
    }
    set_sources(state, data.get("sources"))
    return state


def default_state():
    return {"version": 2, "reset": "00:00:00", "reset_timezone": "UTC+08:00",
            "color": "#ff3030", "position": None, "topmost": True,
            "sources": {"database": str(DEFAULT_DB), "providers": dict.fromkeys(APPS)},
            "balances": dict.fromkeys(APPS), "errors": {}, "last_success": {}, "cache": {}}


def normalized_sources(sources):
    sources = sources if isinstance(sources, dict) else {}
    path = sources.get("database")
    if not isinstance(path, str) or not path.strip():
        path = str(DEFAULT_DB)
    providers = sources.get("providers")
    providers = providers if isinstance(providers, dict) else {}
    return {"database": str(Path(path).expanduser().resolve()),
            "providers": {app: providers[app] if isinstance(providers.get(app), str)
                          and providers[app] else None for app in APPS}}


def cache_key(sources, app):
    identity = [os.path.normcase(str(Path(sources["database"]).resolve())),
                app, sources["providers"].get(app)]
    return hashlib.sha256(json.dumps(identity).encode("utf-8")).hexdigest()


def set_sources(state, sources):
    state["sources"] = normalized_sources(sources)
    state["balances"] = dict.fromkeys(APPS)
    state["last_success"] = {}
    state["errors"] = {}
    cache = state.setdefault("cache", {})
    for app in APPS:
        if state["sources"]["providers"][app] is None:
            continue
        entry = cache.get(cache_key(state["sources"], app), {})
        if not isinstance(entry, dict):
            continue
        value = entry.get("value")
        if finite_amount(value):
            state["balances"][app] = value
            if isinstance(entry.get("last_success"), str):
                state["last_success"][app] = entry["last_success"]


def save_state(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    try:
        os.replace(temp, path)
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise
        # Some Windows filesystem redirects put these paths on separate volumes.
        # Keep the complete temp copy available if the fallback is interrupted.
        shutil.copyfile(temp, path)
