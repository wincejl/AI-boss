from __future__ import annotations

import base64
import os
import time
from io import BytesIO
from typing import Any

def ocr_provider_status() -> dict[str, Any]:
    provider = configured_provider()
    cloud_enabled = env_enabled("OCR_CLOUD_ENABLED")
    status: dict[str, Any] = {
        "provider": provider,
        "cloud_enabled": cloud_enabled,
        "region_only": env_enabled("OCR_REGION_ONLY", default=True),
        "save_images": env_enabled("OCR_SAVE_IMAGES"),
        "ready": False,
        "message": "OCR provider is disabled",
    }
    if provider == "none":
        return status
    if provider == "baidu_cloud":
        has_keys = bool(os.getenv("OCR_BAIDU_API_KEY") and os.getenv("OCR_BAIDU_SECRET_KEY"))
        status["ready"] = cloud_enabled and has_keys
        if not cloud_enabled:
            status["message"] = "Baidu cloud OCR configured but OCR_CLOUD_ENABLED is false"
        elif not has_keys:
            status["message"] = "Baidu cloud OCR requires OCR_BAIDU_API_KEY and OCR_BAIDU_SECRET_KEY"
        else:
            status["message"] = "Baidu cloud OCR is ready for explicit bounded-region tests"
        return status
    if provider == "paddle_cloud":
        has_token = bool(os.getenv("OCR_PADDLE_TOKEN"))
        status["ready"] = cloud_enabled and has_token
        status["model"] = paddle_model()
        if not cloud_enabled:
            status["message"] = "Paddle cloud OCR configured but OCR_CLOUD_ENABLED is false"
        elif not has_token:
            status["message"] = "Paddle cloud OCR requires OCR_PADDLE_TOKEN"
        else:
            status["message"] = "Paddle cloud OCR is ready for explicit bounded-region tests"
        return status
    status["message"] = f"unsupported OCR provider: {provider}"
    return status


def recognize_region(image) -> dict[str, Any]:
    provider = configured_provider()
    started = time.perf_counter()
    if provider == "none":
        return disabled_result(started, "OCR_PROVIDER is none")
    if provider == "baidu_cloud":
        if not env_enabled("OCR_CLOUD_ENABLED"):
            return disabled_result(started, "cloud OCR upload is disabled; set OCR_CLOUD_ENABLED=true for a supervised test")
        return baidu_cloud_ocr(image, started)
    if provider == "paddle_cloud":
        if not env_enabled("OCR_CLOUD_ENABLED"):
            return disabled_result(started, "cloud OCR upload is disabled; set OCR_CLOUD_ENABLED=true for a supervised test")
        return paddle_cloud_ocr(image, started)
    return disabled_result(started, f"unsupported OCR provider: {provider}")


def baidu_cloud_ocr(image, started: float) -> dict[str, Any]:
    try:
        import httpx
    except Exception:
        return disabled_result(started, "httpx is required for Baidu cloud OCR")
    api_key = os.getenv("OCR_BAIDU_API_KEY", "").strip()
    secret_key = os.getenv("OCR_BAIDU_SECRET_KEY", "").strip()
    if not api_key or not secret_key:
        return disabled_result(started, "Baidu cloud OCR credentials are not configured")
    token_url = "https://aip.baidubce.com/oauth/2.0/token"
    ocr_url = "https://aip.baidubce.com/rest/2.0/ocr/v1/general_basic"
    timeout = httpx.Timeout(15.0, connect=8.0)
    try:
        with httpx.Client(timeout=timeout) as client:
            token_resp = client.post(
                token_url,
                params={
                    "grant_type": "client_credentials",
                    "client_id": api_key,
                    "client_secret": secret_key,
                },
            )
            token_resp.raise_for_status()
            token_data = token_resp.json()
            access_token = token_data.get("access_token")
            if not access_token:
                return provider_error(started, "baidu_cloud", "Baidu token response did not include access_token")
            image_b64 = encode_image(image)
            ocr_resp = client.post(
                ocr_url,
                params={"access_token": access_token},
                data={"image": image_b64, "language_type": os.getenv("OCR_BAIDU_LANGUAGE_TYPE", "CHN_ENG")},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            ocr_resp.raise_for_status()
            data = ocr_resp.json()
    except Exception as exc:
        return provider_error(started, "baidu_cloud", str(exc))
    words = data.get("words_result") or []
    lines: list[str] = []
    boxes: list[dict[str, Any]] = []
    for item in words:
        if not isinstance(item, dict):
            continue
        text = str(item.get("words") or "").strip()
        if text:
            lines.append(text)
        location = item.get("location")
        if isinstance(location, dict):
            boxes.append({"text": text, "box": location})
    return {
        "ok": True,
        "provider": "baidu_cloud",
        "text": "\n".join(lines),
        "boxes": boxes,
        "confidence": None,
        "elapsed_ms": elapsed_ms(started),
        "message": "cloud OCR completed; image was not stored or returned",
    }


def paddle_cloud_ocr(image, started: float) -> dict[str, Any]:
    try:
        import httpx
    except Exception:
        return disabled_result(started, "httpx is required for Paddle cloud OCR")
    token = os.getenv("OCR_PADDLE_TOKEN", "").strip()
    if not token:
        return disabled_result(started, "Paddle cloud OCR token is not configured")
    job_url = os.getenv("OCR_PADDLE_JOB_URL", "https://paddleocr.aistudio-app.com/api/v2/ocr/jobs").strip()
    headers = {"Authorization": f"bearer {token}"}
    timeout = httpx.Timeout(float_env("OCR_PADDLE_HTTP_TIMEOUT_SECONDS", 30.0), connect=8.0)
    try:
        with httpx.Client(timeout=timeout) as client:
            image_bytes = image_png_bytes(image)
            job_resp = client.post(
                job_url,
                headers=headers,
                data={
                    "model": paddle_model(),
                    "optionalPayload": paddle_optional_payload_json(),
                },
                files={"file": ("boss-region.png", image_bytes, "image/png")},
            )
            job_resp.raise_for_status()
            job_id = (((job_resp.json() or {}).get("data") or {}).get("jobId") or "").strip()
            if not job_id:
                return provider_error(started, "paddle_cloud", "Paddle OCR job response did not include jobId")
            result = poll_paddle_job(client, job_url, job_id, headers)
            if not result.get("ok"):
                return provider_error(started, "paddle_cloud", str(result.get("error") or "Paddle OCR job failed"))
            jsonl_url = result.get("json_url", "")
            if not jsonl_url:
                return provider_error(started, "paddle_cloud", "Paddle OCR job completed without jsonUrl")
            jsonl_resp = client.get(str(jsonl_url))
            jsonl_resp.raise_for_status()
            text, blocks = parse_paddle_jsonl(jsonl_resp.text)
    except Exception as exc:
        return provider_error(started, "paddle_cloud", str(exc))
    return {
        "ok": True,
        "provider": "paddle_cloud",
        "text": truncate_text(text),
        "boxes": blocks,
        "confidence": None,
        "elapsed_ms": elapsed_ms(started),
        "message": "Paddle cloud OCR completed; image and output assets were not stored",
    }


def poll_paddle_job(client, job_url: str, job_id: str, headers: dict[str, str]) -> dict[str, Any]:
    deadline = time.perf_counter() + float_env("OCR_PADDLE_MAX_WAIT_SECONDS", 90.0)
    sleep_seconds = float_env("OCR_PADDLE_POLL_SECONDS", 2.0)
    while time.perf_counter() < deadline:
        resp = client.get(f"{job_url.rstrip('/')}/{job_id}", headers=headers)
        resp.raise_for_status()
        data = (resp.json() or {}).get("data") or {}
        state = data.get("state")
        if state == "done":
            result_url = data.get("resultUrl") or {}
            return {"ok": True, "json_url": result_url.get("jsonUrl") or ""}
        if state == "failed":
            return {"ok": False, "error": data.get("errorMsg") or "Paddle OCR job failed"}
        time.sleep(max(0.5, sleep_seconds))
    return {"ok": False, "error": "Paddle OCR job polling timed out"}


def parse_paddle_jsonl(raw: str) -> tuple[str, list[dict[str, Any]]]:
    texts: list[str] = []
    blocks: list[dict[str, Any]] = []
    for line_number, line in enumerate(raw.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            payload = json_loads(line)
        except Exception:
            continue
        result = payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(result, dict):
            continue
        blocks.append(paddle_debug_block("result", result, line_number))
        for item in result.get("layoutParsingResults") or []:
            if not isinstance(item, dict):
                continue
            blocks.append(paddle_debug_block("layout", item, line_number))
            for block in paddle_parsing_blocks(item):
                block_text = str(block.get("text") or "").strip()
                if block_text:
                    texts.append(block_text)
                blocks.append(block)
            markdown = item.get("markdown") or {}
            markdown_text = str(markdown.get("text") or "").strip()
            if markdown_text and not texts:
                texts.append(markdown_text)
                block = {"type": "markdown", "text": truncate_text(markdown_text)}
                if isinstance(markdown, dict):
                    block["keys"] = sorted(str(key) for key in markdown.keys())
                    coords = paddle_find_coordinate_like(markdown)
                    if coords:
                        block["coordinates"] = coords
                blocks.append(block)
        if not texts:
            text = str(result.get("text") or result.get("markdown") or "").strip()
            if text:
                texts.append(text)
    return "\n\n".join(texts), blocks


def paddle_parsing_blocks(item: dict[str, Any]) -> list[dict[str, Any]]:
    pruned = item.get("prunedResult")
    if not isinstance(pruned, dict):
        return []
    parsing = pruned.get("parsing_res_list")
    if not isinstance(parsing, list):
        return []
    blocks: list[dict[str, Any]] = []
    for index, entry in enumerate(parsing):
        if not isinstance(entry, dict):
            continue
        text = first_string_value(
            entry,
            (
                "block_content",
                "text",
                "content",
                "rec_text",
                "markdown",
            ),
        )
        bbox = first_value(entry, ("block_bbox", "bbox", "coordinate", "box"))
        polygon = first_value(entry, ("block_polygon_points", "polygon_points", "points", "poly"))
        block: dict[str, Any] = {
            "type": "paddle_block",
            "index": index,
            "keys": sorted(str(key) for key in entry.keys()),
        }
        if text:
            block["text"] = truncate_text(text)
        if bbox is not None:
            block["bbox"] = truncate_json_value(bbox)
        if polygon is not None:
            block["polygon"] = truncate_json_value(polygon)
        label = first_string_value(entry, ("block_label", "label", "type"))
        if label:
            block["label"] = label
        blocks.append(block)
    return blocks


def first_value(source: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in source:
            return source.get(key)
    return None


def first_string_value(source: dict[str, Any], keys: tuple[str, ...]) -> str:
    value = first_value(source, keys)
    if value is None:
        return ""
    return str(value).strip()


def paddle_debug_block(kind: str, value: dict[str, Any], line_number: int) -> dict[str, Any]:
    block: dict[str, Any] = {
        "type": f"paddle_{kind}",
        "line": line_number,
        "keys": sorted(str(key) for key in value.keys()),
    }
    coords = paddle_find_coordinate_like(value)
    if coords:
        block["coordinates"] = coords
    return block


def paddle_find_coordinate_like(value: Any, path: str = "", depth: int = 0) -> list[dict[str, Any]]:
    if depth > 4:
        return []
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            key_str = str(key)
            child_path = f"{path}.{key_str}" if path else key_str
            lower = key_str.lower()
            if any(token in lower for token in ("bbox", "box", "coord", "poly", "rect", "points")):
                found.append({"path": child_path, "value": truncate_json_value(child)})
            found.extend(paddle_find_coordinate_like(child, child_path, depth + 1))
    elif isinstance(value, list):
        for index, child in enumerate(value[:8]):
            found.extend(paddle_find_coordinate_like(child, f"{path}[{index}]", depth + 1))
    return found[:20]


def truncate_json_value(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [truncate_json_value(item) for item in value[:8]]
    if isinstance(value, dict):
        return {str(key): truncate_json_value(child) for key, child in list(value.items())[:12]}
    return str(value)[:200]


def image_png_bytes(image) -> bytes:
    buffer = BytesIO()
    image.convert("RGB").save(buffer, format="PNG")
    return buffer.getvalue()


def encode_image(image) -> str:
    return base64.b64encode(image_png_bytes(image)).decode("ascii")


def configured_provider() -> str:
    return os.getenv("OCR_PROVIDER", "none").strip().lower() or "none"


def paddle_model() -> str:
    return os.getenv("OCR_PADDLE_MODEL", "PaddleOCR-VL-1.6").strip() or "PaddleOCR-VL-1.6"


def paddle_optional_payload_json() -> str:
    payload = {
        "useDocOrientationClassify": env_enabled("OCR_PADDLE_USE_DOC_ORIENTATION_CLASSIFY"),
        "useDocUnwarping": env_enabled("OCR_PADDLE_USE_DOC_UNWARPING"),
        "useChartRecognition": env_enabled("OCR_PADDLE_USE_CHART_RECOGNITION"),
    }
    return json_dumps(payload)


def env_enabled(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def float_env(name: str, default: float) -> float:
    try:
        value = float(os.getenv(name, ""))
    except ValueError:
        return default
    return value if value > 0 else default


def truncate_text(value: str) -> str:
    limit = int(float_env("OCR_MAX_TEXT_CHARS", 20000))
    if len(value) <= limit:
        return value
    return value[:limit]


def json_dumps(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False)


def json_loads(value: str) -> Any:
    import json

    return json.loads(value)


def disabled_result(started: float, message: str) -> dict[str, Any]:
    return {
        "ok": False,
        "provider": configured_provider(),
        "text": "",
        "boxes": [],
        "confidence": None,
        "elapsed_ms": elapsed_ms(started),
        "message": message,
    }


def provider_error(started: float, provider: str, error: str) -> dict[str, Any]:
    return {
        "ok": False,
        "provider": provider,
        "text": "",
        "boxes": [],
        "confidence": None,
        "elapsed_ms": elapsed_ms(started),
        "message": "OCR provider request failed",
        "error": error,
    }
