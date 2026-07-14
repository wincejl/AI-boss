from __future__ import annotations

import importlib.util
import json
import os
import platform
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

from .ocr_provider import ocr_provider_status, recognize_region


VISUAL_SAFETY = {
    "read_only": True,
    "no_clicks": True,
    "no_text_input": True,
    "no_messages": True,
    "no_fullscreen_capture_by_default": True,
    "no_ocr_by_default": True,
    "no_image_storage": True,
}

BOSS_DESKTOP_SAFETY = {
    "capture_api": "Windows.Graphics.Capture",
    "no_private_api": True,
    "no_hooks": True,
    "no_memory_reading": True,
    "no_network_sniffing": True,
    "no_text_input": True,
    "no_messages": True,
    "clicks_limited_to_chat_list": True,
    "requires_screenshot_opt_in": True,
    "requires_click_opt_in_for_scan": True,
}


def probe_visual_capabilities() -> dict[str, Any]:
    """Report whether visual automation dependencies are available.

    The default probe does not capture screenshots. Screenshots and OCR can
    expose private candidate/chat data, so they require explicit opt-in envs.
    """
    dependencies = {
        "pyautogui": has_module("pyautogui"),
        "PIL": has_module("PIL"),
        "mss": has_module("mss"),
        "cv2": has_module("cv2"),
        "pytesseract": has_module("pytesseract"),
        "numpy": has_module("numpy"),
    }
    tesseract_path = shutil.which("tesseract")
    screenshot_opt_in = env_enabled("BOSS_VISUAL_SCREENSHOT_PROBE")
    ocr_opt_in = env_enabled("BOSS_VISUAL_OCR_PROBE")

    screen = probe_screen_size() if screenshot_opt_in else None
    process_snapshot = find_boss_processes()
    has_visual_stack = dependencies["pyautogui"] and dependencies["PIL"]
    has_template_stack = has_visual_stack and dependencies["cv2"] and dependencies["numpy"]
    has_ocr_stack = has_visual_stack and dependencies["pytesseract"] and bool(tesseract_path)
    provider_status = ocr_provider_status()
    provider_ocr_ready = bool(provider_status.get("ready"))

    recommendations = []
    if not has_visual_stack:
        recommendations.append("install pyautogui and pillow before testing visual control")
    if not dependencies["mss"]:
        recommendations.append("install mss for faster bounded screenshots")
    if dependencies["pytesseract"] and not tesseract_path:
        recommendations.append("install the Tesseract OCR engine before enabling OCR")
    if process_snapshot and not screenshot_opt_in:
        recommendations.append("BOSS process is running; enable BOSS_VISUAL_SCREENSHOT_PROBE only during a supervised test")

    return {
        "ok": True,
        "mode": "visual_capability_probe",
        "platform": platform.system(),
        "detected": bool(process_snapshot),
        "process_count": len(process_snapshot),
        "dependencies": dependencies,
        "tesseract_path": tesseract_path or "",
        "screenshot_probe_enabled": screenshot_opt_in,
        "ocr_probe_enabled": ocr_opt_in,
        "screen": screen,
        "supported": has_visual_stack,
        "template_matching_supported": has_template_stack,
        "ocr_supported": has_ocr_stack or provider_ocr_ready,
        "ocr_provider": provider_status,
        "safety": VISUAL_SAFETY,
        "recommendations": recommendations,
        "message": visual_probe_message(has_visual_stack, has_template_stack, has_ocr_stack or provider_ocr_ready),
    }


def probe_region(x: int, y: int, width: int, height: int) -> dict[str, Any]:
    if not env_enabled("BOSS_VISUAL_SCREENSHOT_PROBE"):
        return {
            "ok": False,
            "mode": "visual_region_probe",
            "safety": VISUAL_SAFETY,
            "message": "bounded screenshot probe is disabled; set BOSS_VISUAL_SCREENSHOT_PROBE=true for a supervised test",
        }
    if not has_module("pyautogui") or not has_module("PIL"):
        return {
            "ok": False,
            "mode": "visual_region_probe",
            "safety": VISUAL_SAFETY,
            "message": "pyautogui and pillow are required for bounded screenshot probing",
        }
    x = max(0, int(x))
    y = max(0, int(y))
    width = max(1, min(1200, int(width)))
    height = max(1, min(900, int(height)))
    started = time.perf_counter()
    try:
        image = capture_region_image(x, y, width, height)
        rgb = image.convert("RGB")
        pixels = list(rgb.resize((1, 1)).getdata())
        average = pixels[0] if pixels else (0, 0, 0)
    except Exception as exc:
        return {
            "ok": False,
            "mode": "visual_region_probe",
            "safety": VISUAL_SAFETY,
            "message": "bounded screenshot probe failed",
            "error": str(exc),
        }
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return {
        "ok": True,
        "mode": "visual_region_probe",
        "region": {"x": x, "y": y, "width": width, "height": height},
        "average_rgb": {"r": average[0], "g": average[1], "b": average[2]},
        "elapsed_ms": elapsed_ms,
        "safety": VISUAL_SAFETY,
        "message": "bounded screenshot probe completed without storing or returning an image",
    }


def ocr_region(x: int, y: int, width: int, height: int) -> dict[str, Any]:
    if not env_enabled("BOSS_VISUAL_SCREENSHOT_PROBE"):
        return {
            "ok": False,
            "mode": "visual_ocr_region",
            "safety": VISUAL_SAFETY,
            "message": "bounded screenshot probe is disabled; set BOSS_VISUAL_SCREENSHOT_PROBE=true for a supervised OCR test",
        }
    if not env_enabled("BOSS_VISUAL_OCR_PROBE"):
        return {
            "ok": False,
            "mode": "visual_ocr_region",
            "safety": VISUAL_SAFETY,
            "message": "OCR probe is disabled; set BOSS_VISUAL_OCR_PROBE=true for a supervised OCR test",
        }
    provider_status = ocr_provider_status()
    if not provider_status.get("ready"):
        return {
            "ok": False,
            "mode": "visual_ocr_region",
            "ocr_provider": provider_status,
            "safety": VISUAL_SAFETY,
            "message": provider_status.get("message") or "OCR provider is not ready",
        }
    if not has_module("pyautogui") or not has_module("PIL"):
        return {
            "ok": False,
            "mode": "visual_ocr_region",
            "ocr_provider": provider_status,
            "safety": VISUAL_SAFETY,
            "message": "pyautogui and pillow are required for bounded OCR probing",
        }
    x = max(0, int(x))
    y = max(0, int(y))
    width = max(1, min(1200, int(width)))
    height = max(1, min(900, int(height)))
    try:
        image = capture_region_image(x, y, width, height)
    except Exception as exc:
        return {
            "ok": False,
            "mode": "visual_ocr_region",
            "ocr_provider": provider_status,
            "safety": VISUAL_SAFETY,
            "message": "bounded screenshot for OCR failed",
            "error": str(exc),
        }
    result = recognize_region(image)
    result.update(
        {
            "mode": "visual_ocr_region",
            "region": {"x": x, "y": y, "width": width, "height": height},
            "ocr_provider": provider_status,
            "safety": VISUAL_SAFETY,
        }
    )
    return result


def wgc_status() -> dict[str, Any]:
    tool = wgc_tool_path()
    return {
        "ok": platform.system() == "Windows" and tool.exists(),
        "mode": "boss_desktop_wgc_status",
        "platform": platform.system(),
        "tool_path": str(tool),
        "tool_exists": tool.exists(),
        "screenshot_probe_enabled": env_enabled("BOSS_VISUAL_SCREENSHOT_PROBE"),
        "click_probe_enabled": env_enabled("BOSS_DESKTOP_CLICK_PROBE"),
        "safety": BOSS_DESKTOP_SAFETY,
        "message": "WGC helper is available" if tool.exists() else "WGC helper executable is missing; build tools/wgc-capture first",
    }


def capture_boss_window() -> dict[str, Any]:
    if not env_enabled("BOSS_VISUAL_SCREENSHOT_PROBE"):
        return {
            "ok": False,
            "mode": "boss_desktop_wgc_capture",
            "safety": BOSS_DESKTOP_SAFETY,
            "message": "desktop WGC capture is disabled; set BOSS_VISUAL_SCREENSHOT_PROBE=true for a supervised test",
        }
    output_dir = desktop_capture_dir("boss-desktop-captures")
    output_path = output_dir / f"boss-{timestamp_id()}.png"
    result = run_wgc(["--auto-boss", str(output_path)], timeout=60)
    payload = wgc_command_result("boss_desktop_wgc_capture", result, [output_path])
    cleanup = cleanup_image_paths([output_path])
    payload["deleted_images"] = cleanup
    payload["image_retention"] = False
    return payload


def scan_boss_chats(count: int, run_ocr: bool = False) -> dict[str, Any]:
    if not env_enabled("BOSS_VISUAL_SCREENSHOT_PROBE"):
        return {
            "ok": False,
            "mode": "boss_desktop_wgc_scan",
            "safety": BOSS_DESKTOP_SAFETY,
            "message": "desktop WGC scan is disabled; set BOSS_VISUAL_SCREENSHOT_PROBE=true for a supervised test",
        }
    if not env_enabled("BOSS_DESKTOP_CLICK_PROBE"):
        return {
            "ok": False,
            "mode": "boss_desktop_wgc_scan",
            "safety": BOSS_DESKTOP_SAFETY,
            "message": "desktop click scan is disabled; set BOSS_DESKTOP_CLICK_PROBE=true for a supervised test",
        }
    safe_count = max(1, min(10, int(count)))
    output_dir = desktop_capture_dir("boss-desktop-scans") / f"scan-{timestamp_id()}-{uuid.uuid4().hex[:8]}"
    result = run_wgc(["--scan", str(output_dir), str(safe_count)], timeout=30 + safe_count * 15)
    images = sorted(output_dir.glob("*.png")) if output_dir.exists() else []
    extra: dict[str, Any] = {"requested_count": safe_count, "ocr_requested": run_ocr}
    if run_ocr:
        extra["ocr_results"] = ocr_wgc_chat_images(images)
    payload = wgc_command_result("boss_desktop_wgc_scan", result, images, extra=extra)
    cleanup = cleanup_image_paths(images)
    cleanup_dir(output_dir)
    payload["deleted_images"] = cleanup
    payload["image_retention"] = False
    return payload


def draft_from_ocr_text(payload) -> dict[str, Any]:
    from .recruitment_agent import run_recruitment_agent
    from .schemas import RecruitmentAgentRequest, RecruitmentCandidate

    chat_text = str(payload.chat_text or "").strip()
    candidate = RecruitmentCandidate(
        name=str(payload.candidate_name or "").strip() or "BOSS OCR Candidate",
        source="boss_desktop_ocr",
        current_role=str(payload.current_role or "").strip(),
        profile=chat_text,
        last_message=latest_message_hint(chat_text),
        contact_status="ocr_review",
        consent_to_contact=False,
        next_action="review_draft",
    )
    request = RecruitmentAgentRequest(
        thread_id=payload.thread_id or f"boss-desktop-ocr-{timestamp_id()}",
        knowledge_context=payload.knowledge_context,
        requirement=payload.requirement,
        candidate=candidate,
    )
    result = run_recruitment_agent(request)
    return {
        "ok": True,
        "mode": "boss_desktop_draft_from_ocr",
        "ocr_chars": len(chat_text),
        "candidate": candidate.model_dump(),
        "draft": result.model_dump(),
        "requires_human_approval": True,
        "safety": BOSS_DESKTOP_SAFETY,
        "message": "Draft generated from OCR text; no BOSS message was sent",
    }


def scan_and_draft_boss_chats(payload) -> dict[str, Any]:
    from .schemas import BossDesktopDraftFromOCRRequest

    scan = scan_boss_chats(payload.count, run_ocr=True)
    drafts: list[dict[str, Any]] = []
    for index, item in enumerate(scan.get("ocr_results") or [], start=1):
        text = str(item.get("text") or "").strip() if isinstance(item, dict) else ""
        if not text:
            drafts.append(
                {
                    "ok": False,
                    "index": index,
                    "message": "OCR did not return text for this conversation",
                    "ocr": item,
                }
            )
            continue
        draft_payload = BossDesktopDraftFromOCRRequest(
            thread_id=f"boss-desktop-scan-{timestamp_id()}-{index}",
            knowledge_context=payload.knowledge_context,
            requirement=payload.requirement,
            chat_text=text,
        )
        draft = draft_from_ocr_text(draft_payload)
        draft["index"] = index
        draft["ocr"] = item
        drafts.append(draft)

    return {
        "ok": bool(drafts) and all(bool(item.get("ok")) for item in drafts),
        "mode": "boss_desktop_scan_draft",
        "scan": scan,
        "drafts": drafts,
        "requires_human_approval": True,
        "safety": BOSS_DESKTOP_SAFETY,
        "message": "Scan/OCR/draft completed; no BOSS message was sent",
    }


def capture_region_image(x: int, y: int, width: int, height: int):
    try:
        import pyautogui

        return pyautogui.screenshot(region=(x, y, width, height))
    except Exception:
        if not has_module("mss") or not has_module("PIL"):
            raise
    import mss
    from PIL import Image

    with mss.mss() as sct:
        raw = sct.grab({"left": x, "top": y, "width": width, "height": height})
        return Image.frombytes("RGB", raw.size, raw.rgb)


def run_wgc(args: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    tool = wgc_tool_path()
    if platform.system() != "Windows":
        raise RuntimeError("Windows Graphics Capture helper is only supported on Windows")
    if not tool.exists():
        raise RuntimeError(f"WGC helper executable not found: {tool}")
    return subprocess.run(
        [str(tool), *args],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def wgc_command_result(
    mode: str,
    completed: subprocess.CompletedProcess[str],
    image_paths: list[Path],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    images = [image_metadata(path) for path in image_paths if path.exists()]
    payload: dict[str, Any] = {
        "ok": completed.returncode == 0 and bool(images),
        "mode": mode,
        "return_code": completed.returncode,
        "images": images,
        "stdout": truncate_log(completed.stdout),
        "stderr": truncate_log(completed.stderr),
        "safety": BOSS_DESKTOP_SAFETY,
        "message": "WGC helper completed" if completed.returncode == 0 else "WGC helper failed",
    }
    if extra:
        payload.update(extra)
    return payload


def image_metadata(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": str(path),
        "bytes": stat.st_size,
        "created_at": int(stat.st_ctime),
        "modified_at": int(stat.st_mtime),
    }


def cleanup_image_paths(paths: list[Path]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for path in paths:
        item = {"path": str(path), "deleted": False}
        try:
            if path.exists():
                path.unlink()
                item["deleted"] = True
        except Exception as exc:
            item["error"] = str(exc)
        results.append(item)
    return results


def cleanup_dir(path: Path) -> None:
    try:
        if path.exists() and path.is_dir() and not any(path.iterdir()):
            path.rmdir()
    except Exception:
        pass


def latest_message_hint(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    ignored = {"同意", "拒绝", "求简历", "换电话", "换微信", "我知道了", "已读"}
    useful: list[str] = []
    for line in lines:
        if line in ignored:
            continue
        if line.startswith("<div") or line.endswith("/>"):
            continue
        useful.append(line)
    return "\n".join(useful[-8:])[:1200]


def ocr_wgc_chat_images(image_paths: list[Path]) -> list[dict[str, Any]]:
    if not env_enabled("BOSS_VISUAL_OCR_PROBE"):
        return [
            {
                "ok": False,
                "path": str(path),
                "message": "OCR is disabled; set BOSS_VISUAL_OCR_PROBE=true for a supervised OCR test",
            }
            for path in image_paths
        ]

    provider_status = ocr_provider_status()
    if not provider_status.get("ready"):
        return [
            {
                "ok": False,
                "path": str(path),
                "ocr_provider": provider_status,
                "message": provider_status.get("message") or "OCR provider is not ready",
            }
            for path in image_paths
        ]

    try:
        from PIL import Image
    except Exception as exc:
        return [{"ok": False, "path": str(path), "message": f"Pillow is required for OCR crop: {exc}"} for path in image_paths]

    results: list[dict[str, Any]] = []
    for path in image_paths:
        try:
            with Image.open(path) as image:
                cropped = crop_chat_region(image)
                result = recognize_region(cropped)
        except Exception as exc:
            result = {"ok": False, "message": "OCR crop failed", "error": str(exc)}
        result["path"] = str(path)
        result["crop"] = chat_crop_ratios()
        results.append(result)
    return results


def crop_chat_region(image):
    left, top, right, bottom = chat_crop_ratios()
    width, height = image.size
    box = (
        int(width * left),
        int(height * top),
        int(width * right),
        int(height * bottom),
    )
    return image.crop(box)


def chat_crop_ratios() -> tuple[float, float, float, float]:
    return (
        ratio_env("BOSS_DESKTOP_CHAT_CROP_LEFT", 0.40),
        ratio_env("BOSS_DESKTOP_CHAT_CROP_TOP", 0.05),
        ratio_env("BOSS_DESKTOP_CHAT_CROP_RIGHT", 0.96),
        ratio_env("BOSS_DESKTOP_CHAT_CROP_BOTTOM", 0.92),
    )


def wgc_tool_path() -> Path:
    return repo_root() / "tools" / "wgc-capture" / "wgc-capture.exe"


def desktop_capture_dir(name: str) -> Path:
    output_dir = repo_root() / ".dev" / name
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def timestamp_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def truncate_log(value: str, limit: int = 4000) -> str:
    value = value or ""
    if len(value) <= limit:
        return value
    return value[:limit]


def find_boss_processes() -> list[dict[str, Any]]:
    if platform.system() != "Windows":
        return []
    script = r"""
$ErrorActionPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Get-Process -Name 'boss-zhipin','boss-zhipin-daemon' -ErrorAction SilentlyContinue |
  Select-Object @{Name='process_id';Expression={$_.Id}},
    @{Name='process_name';Expression={$_.ProcessName}},
    @{Name='main_window_handle';Expression={[int64]$_.MainWindowHandle}},
    @{Name='main_window_title';Expression={$_.MainWindowTitle}},
    @{Name='exe_path';Expression={$_.Path}} |
  ConvertTo-Json -Compress
"""
    try:
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return []
    raw = (completed.stdout or "").strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    items = parsed if isinstance(parsed, list) else [parsed]
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "process_id": int(item.get("process_id") or 0),
                "process_name": str(item.get("process_name") or ""),
                "main_window_handle": int(item.get("main_window_handle") or 0),
                "main_window_title": str(item.get("main_window_title") or ""),
                "exe_path": str(item.get("exe_path") or ""),
            }
        )
    return out


def has_module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def env_enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def ratio_env(name: str, default: float) -> float:
    try:
        value = float(os.getenv(name, ""))
    except ValueError:
        value = default
    if value <= 0:
        value = default
    return max(0.0, min(1.0, value))


def probe_screen_size() -> dict[str, int] | None:
    if not has_module("pyautogui"):
        return None
    try:
        import pyautogui

        width, height = pyautogui.size()
        return {"width": int(width), "height": int(height)}
    except Exception:
        return None


def visual_probe_message(has_visual_stack: bool, has_template_stack: bool, has_ocr_stack: bool) -> str:
    if has_template_stack and has_ocr_stack:
        return "visual stack is ready for supervised bounded screenshot, template matching, and OCR tests"
    if has_template_stack:
        return "visual stack is ready for supervised bounded screenshot and template matching tests; OCR engine is not ready"
    if has_visual_stack:
        return "basic visual stack is ready for supervised bounded screenshot tests"
    return "visual automation dependencies are not installed"
