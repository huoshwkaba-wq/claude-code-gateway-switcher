"""Claude Code gateway profiles and checks for Windows."""

import base64
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen


APP_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "ClaudeGatewaySwitcher"
PROFILES_FILE = APP_DIR / "profiles.json"
CLAUDE_SETTINGS = Path.home() / ".claude" / "settings.json"
EFFORTS = ("auto", "low", "medium", "high", "xhigh", "max")
INKSTONE_PRICES = "https://discovery.intern-ai.org.cn/api/tokenplan/v1/public/models"
INKSTONE_BILLING = "https://discovery.intern-ai.org.cn/token-plan/home?tabIndex=3"
XF_MAAS_ROOT = "https://maas-api.cn-huabei-1.xf-yun.com"
XF_SPARK_MODELS = ("spark-x2.6", "spark-x2.6-4b", "spark-x2.6-preview",
                   "spark-x2.5", "spark-x2.5-4b", "spark-x2.5-1.7b")


class _Blob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_byte))]


def _crypt(value: bytes, protect: bool) -> bytes:
    source_buffer = ctypes.create_string_buffer(value)
    source = _Blob(len(value), ctypes.cast(source_buffer, ctypes.POINTER(ctypes.c_byte)))
    result = _Blob()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    function = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    function.argtypes = [ctypes.POINTER(_Blob), ctypes.c_wchar_p, ctypes.c_void_p,
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_Blob)]
    function.restype = wintypes.BOOL
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(result)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(result.data, result.size)
    finally:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p
        kernel32.LocalFree(result.data)


def encrypt_key(key: str) -> str:
    return base64.b64encode(_crypt(key.encode("utf-8"), True)).decode("ascii")


def decrypt_key(ciphertext: str) -> str:
    return _crypt(base64.b64decode(ciphertext), False).decode("utf-8")


def read_settings() -> dict:
    if not CLAUDE_SETTINGS.exists():
        return {}
    data = json.loads(CLAUDE_SETTINGS.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or not isinstance(data.get("env", {}), dict):
        raise ValueError("Claude Code settings.json 格式无效")
    return data


def save_profiles(profiles: list[dict]) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    _atomic_json(PROFILES_FILE, {"profiles": profiles})


def load_profiles() -> list[dict]:
    if PROFILES_FILE.exists():
        data = json.loads(PROFILES_FILE.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict) or not isinstance(data.get("profiles"), list):
            raise ValueError("配置列表格式无效")
        return data["profiles"]
    current = read_settings()
    env = current.get("env", {})
    if env.get("ANTHROPIC_BASE_URL") and env.get("ANTHROPIC_AUTH_TOKEN"):
        profiles = [{"name": "当前配置", "url": env["ANTHROPIC_BASE_URL"],
                     "key": encrypt_key(env["ANTHROPIC_AUTH_TOKEN"]),
                     "model": current.get("model", ""),
                     "effort": env.get("CLAUDE_CODE_EFFORT_LEVEL", "auto")}]
    else:
        profiles = []
    save_profiles(profiles)
    return profiles


def validate(name: str, url: str, key: str, model: str, effort: str,
             require_model: bool = True) -> tuple[str, str, str, str, str]:
    name, url, key, model = (x.strip() for x in (name, url, key, model))
    parsed = urlsplit(url)
    if not name or not key or (require_model and not model):
        raise ValueError("名称和 Key 不能为空；启用前还需选择模型")
    if parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("中转站地址应为 http(s) 地址，不含账号、查询参数或锚点")
    if parsed.path.rstrip("/").endswith(("/v1/messages", "/v1/responses", "/v2/chat/completions")):
        raise ValueError("请填写服务商提供的 Anthropic 协议 Base URL，不要填写以 /v1/messages 等结尾的完整接口地址")
    if effort not in EFFORTS:
        raise ValueError("不支持的推理档位")
    return name, url.rstrip("/"), key, model, effort


def make_profile(name: str, url: str, key: str, model: str, effort: str,
                 require_model: bool = True) -> dict:
    name, url, key, model, effort = validate(name, url, key, model, effort, require_model)
    return {"name": name, "url": url, "key": encrypt_key(key), "model": model, "effort": effort}


def _atomic_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(data, out, ensure_ascii=False, indent=2)
            out.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def activate(profile: dict) -> None:
    if not profile.get("model"):
        raise ValueError("请先选择一个当前模型")
    settings = read_settings()
    env = settings.setdefault("env", {})
    env["ANTHROPIC_BASE_URL"] = profile["url"]
    env["ANTHROPIC_AUTH_TOKEN"] = decrypt_key(profile["key"])
    if profile["effort"] == "auto":
        env.pop("CLAUDE_CODE_EFFORT_LEVEL", None)
    else:
        env["CLAUDE_CODE_EFFORT_LEVEL"] = profile["effort"]
    settings["model"] = profile["model"]
    _atomic_json(CLAUDE_SETTINGS, settings)


def is_active(profile: dict, settings: dict | None = None) -> bool:
    settings = settings if settings is not None else read_settings()
    env = settings.get("env", {})
    return (env.get("ANTHROPIC_BASE_URL", "").rstrip("/") == profile["url"]
            and env.get("ANTHROPIC_AUTH_TOKEN") == decrypt_key(profile["key"])
            and settings.get("model") == profile["model"]
            and env.get("CLAUDE_CODE_EFFORT_LEVEL", "auto") == profile["effort"])


def models_url(base_url: str) -> str:
    return base_url.rstrip("/") + ("/models" if base_url.rstrip("/").endswith("/v1") else "/v1/models")


def price_source(base_url: str) -> str | None:
    if urlsplit(base_url).hostname == "discovery-api.intern-ai.org.cn":
        return INKSTONE_BILLING
    return None


def get_model_prices(base_url: str) -> dict[str, tuple[int | float, int | float]]:
    """Read public InkStone prices in credits per million tokens; no API Key is sent."""
    if not price_source(base_url):
        return {}
    prices = {}
    page_number = 1
    while True:
        request = Request(INKSTONE_PRICES + "?" + urlencode({"page": page_number, "page_size": 100}),
                          headers={"Accept": "application/json"})
        try:
            with urlopen(request, timeout=15) as response:
                payload = json.load(response)
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            raise ValueError(f"无法读取官方价格：{error}") from error
        if not isinstance(payload, dict) or payload.get("code") != 0 or not isinstance(payload.get("data"), dict):
            raise ValueError("官方价格接口响应格式无效")
        data = payload["data"]
        rows = data.get("models")
        if not isinstance(rows, list) or not isinstance(data.get("total"), int):
            raise ValueError("官方价格列表格式无效")
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("id"), str):
                continue
            input_price, output_price = row.get("input_uncached_price"), row.get("output_price")
            if all(isinstance(value, (int, float)) and not isinstance(value, bool)
                   for value in (input_price, output_price)):
                prices[row["id"]] = (input_price, output_price)
        if len(prices) >= data["total"]:
            return prices
        if not rows:
            raise ValueError("官方价格分页不完整")
        page_number += 1


def check_connection(profile: dict) -> str:
    key = decrypt_key(profile["key"])
    request = Request(models_url(profile["url"]), headers={"Authorization": "Bearer " + key,
                                                        "anthropic-version": "2023-06-01"})
    started = time.monotonic()
    try:
        with urlopen(request, timeout=15) as response:
            status = response.status
        return f"基础接口 HTTP {status}，耗时 {time.monotonic() - started:.1f} 秒。模型是否可用请继续做模型测试。"
    except HTTPError as error:
        return f"基础接口 HTTP {error.code}，耗时 {time.monotonic() - started:.1f} 秒。该接口可能不支持模型列表；请继续做模型测试。"
    except (URLError, TimeoutError, OSError) as error:
        return f"基础接口连接失败：{str(error.reason if isinstance(error, URLError) else error)[:180]}"


def list_models(profile: dict) -> list[str]:
    """Read every page exposed by this gateway's /v1/models endpoint."""
    key = decrypt_key(profile["key"])
    url = models_url(profile["url"])
    models = []
    seen = set()
    cursor = None
    while True:
        page_url = url + ("?" + urlencode({"after_id": cursor}) if cursor else "")
        request = Request(page_url, headers={"Authorization": "Bearer " + key,
                                             "anthropic-version": "2023-06-01"})
        try:
            with urlopen(request, timeout=15) as response:
                page = json.load(response)
        except HTTPError as error:
            raise ValueError(f"模型列表接口返回 HTTP {error.code}") from error
        except (URLError, TimeoutError, OSError) as error:
            raise ValueError(f"无法读取模型列表：{error}") from error
        if not isinstance(page, dict):
            raise ValueError("模型列表响应格式无效")
        rows = page.get("data") or page.get("models") or []
        if not isinstance(rows, list):
            raise ValueError("模型列表响应格式无效")
        for row in rows:
            model_id = row.get("id") if isinstance(row, dict) else row
            if isinstance(model_id, str) and model_id and model_id not in seen:
                seen.add(model_id)
                models.append(model_id)
        if not page.get("has_more"):
            return models
        next_cursor = page.get("last_id")
        if not next_cursor or next_cursor == cursor:
            raise ValueError("模型列表分页信息无效，无法确认是否已读取全部模型")
        cursor = next_cursor


def model_candidates(profile: dict, favorites=()) -> tuple[list[str], str]:
    """Use listed models when available, otherwise offer only named candidates to test."""
    is_xf_maas = profile["url"].rstrip("/") == XF_MAAS_ROOT + "/anthropic"
    bases = [profile["url"]] + ([XF_MAAS_ROOT] if is_xf_maas else [])
    errors = []
    for base in bases:
        try:
            models = list_models(dict(profile, url=base))
            if models:
                return models, "接口模型列表"
            errors.append("模型列表为空")
        except ValueError as error:
            errors.append(str(error))
    candidates = list(dict.fromkeys(model for model in
                    [profile.get("model", ""), *favorites, *(XF_SPARK_MODELS if is_xf_maas else ())]
                    if model))
    if candidates:
        source = "预置及手动候选" if is_xf_maas else "手动候选"
        return candidates, f"{source}，非完整列表（模型接口：{'；'.join(errors)}）"
    raise ValueError("；".join(errors) + "；请先填写模型 ID，再用“单模型测试”验证。")


def model_status(message: str) -> str:
    lower = message.lower()
    if message.startswith("模型已实际回复"):
        return "可用"
    if "429" in lower or "rate limit" in lower or "503" in lower or "service unavailable" in lower:
        return "限流或拥塞"
    if "已停止" in message:
        return "已停止"
    if "超时" in message:
        return "超时"
    return "失败"


def find_claude() -> str | None:
    return shutil.which("claude.cmd") or shutil.which("claude.exe")


def launch_claude(folder: str) -> str:
    project = Path(folder).expanduser().resolve()
    if not project.is_dir():
        raise ValueError("项目文件夹不存在，请重新选择")
    executable = find_claude()
    if not executable:
        raise ValueError("未找到 Claude Code 命令，请检查安装")
    terminal = shutil.which("wt.exe")
    if terminal:
        command = [terminal, "-w", "0", "new-tab", "--title", "Claude Code",
                   "--suppressApplicationTitle", "-d", str(project),
                   f'cmd.exe /d /k call "{executable}"']
        try:
            subprocess.Popen(command, cwd=project)
            return "Windows Terminal"
        except OSError:
            pass
    subprocess.Popen(f'call "{executable}"', cwd=project, shell=True,
                     creationflags=subprocess.CREATE_NEW_CONSOLE)
    return "命令提示符"


def _stop_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    try:
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                       capture_output=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        process.kill()
    try:
        process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()


def check_model(profile: dict, stop_event=None, timeout: int = 120,
                require_model_match: bool = False) -> str:
    executable = find_claude()
    if not executable:
        return "未找到 Claude Code 命令 claude.cmd；请确认已安装并加入 PATH。"
    key = decrypt_key(profile["key"])
    env_settings = {"ANTHROPIC_BASE_URL": profile["url"], "ANTHROPIC_AUTH_TOKEN": key}
    if profile["effort"] != "auto":
        env_settings["CLAUDE_CODE_EFFORT_LEVEL"] = profile["effort"]
    started = time.monotonic()
    try:
        with tempfile.TemporaryDirectory(prefix="claude-check-", dir=APP_DIR) as folder:
            settings_path = Path(folder) / "settings.json"
            settings_path.write_text(json.dumps({"env": env_settings}, ensure_ascii=False), encoding="utf-8")
            command = [executable, "--safe-mode", "--settings", str(settings_path),
                       "--model", profile["model"], "-p", "请只回复：OK", "--max-turns", "1",
                       "--tools", "", "--disallowedTools", "mcp__*", "--no-session-persistence",
                       "--output-format", "json"]
            if profile["effort"] != "auto":
                command[4:4] = ["--effort", profile["effort"]]
            process = subprocess.Popen(command, cwd=APP_DIR, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, text=True, encoding="utf-8",
                                       errors="replace")
            while True:
                if stop_event is not None and stop_event.is_set():
                    _stop_process(process)
                    return "模型测试已停止。"
                if time.monotonic() - started >= timeout:
                    _stop_process(process)
                    return f"模型测试超时（{timeout} 秒），未取得模型回复。"
                try:
                    stdout, stderr = process.communicate(timeout=0.5)
                    break
                except subprocess.TimeoutExpired:
                    continue
        elapsed = time.monotonic() - started
        try:
            data = json.loads(stdout)
            answer = str(data.get("result") or "").strip()
            if process.returncode == 0 and answer and not data.get("is_error"):
                if require_model_match and profile["model"] not in (data.get("modelUsage") or {}):
                    actual = ", ".join((data.get("modelUsage") or {}).keys()) or "未知"
                    return f"模型测试未通过：收到回复，但实际使用模型为 {actual}，与请求的 {profile['model']} 不一致。"
                return f"模型已实际回复，耗时 {elapsed:.1f} 秒：{answer[:160]}"
            detail = answer or str(data.get("error") or stderr or "无模型回复")
            if data.get("api_error_status"):
                detail = f"HTTP {data['api_error_status']}：{detail}"
        except json.JSONDecodeError:
            detail = stderr or stdout or f"退出码 {process.returncode}，无输出"
        return f"模型测试未通过，耗时 {elapsed:.1f} 秒：{detail.replace(key, '[已隐藏Key]')[:350]}"
    except OSError as error:
        return f"无法运行 Claude Code：{error}"
