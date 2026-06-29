from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import dataclass
from typing import Any

from DrissionPage import ChromiumOptions, ChromiumPage


@dataclass
class BossSearchPayload:
    city: str = ""
    category: str = ""
    keyword: str = ""
    education: str = ""
    age: str = ""
    recommended_filters: str = ""
    sort_preference: str = ""
    filter_viewed_14_days: bool = False
    filter_exchanged_30_days: bool = False


_page: ChromiumPage | None = None
_lock = threading.Lock()


def get_page() -> ChromiumPage:
    global _page
    with _lock:
        if _page is not None:
            return _page
        co = ChromiumOptions()
        co.set_argument("--start-maximized")
        # ponytail: controlled Chrome profile is enough for local demos; add explicit user-data-dir only if login persistence fails.
        _page = ChromiumPage(co)
        return _page


def open_boss_search() -> ChromiumPage:
    page = get_page()
    url = os.getenv("BOSS_SEARCH_URL", "https://www.zhipin.com/web/chat/search")
    current_url = str(page.url)
    if "zhipin.com" not in current_url or "/web/chat/" not in current_url:
        page.get(url)
        time.sleep(1.2)
    ensure_search_page(page, url)
    return page


def search_candidates(payload: BossSearchPayload) -> dict[str, Any]:
    page = open_boss_search()
    login_lines = page_snapshot(page)
    if is_login_page(page, login_lines):
        raise RuntimeError("BOSS controlled browser is not logged in; login in the opened Chrome window, then retry")
    ensure_filter_panel(page)
    actions: list[str] = []

    if payload.category:
        actions.append(select_category(page, payload.category))
    if payload.city:
        actions.append(select_city(page, payload.city))
    if payload.keyword:
        actions.append(fill_keyword(page, payload.keyword))
    if payload.education:
        actions.append(select_education(page, payload.education))
    if payload.age:
        actions.append(click_text(page, payload.age, "年龄"))

    filters = parse_recommended_filters(payload.recommended_filters)
    more_values = [
        filters.get("院校要求", ""),
        filters.get("经验要求", ""),
        filters.get("性别要求", ""),
        filters.get("薪资区间", ""),
        filters.get("活跃度", ""),
        filters.get("跳槽频率", ""),
        filters.get("求职状态", ""),
        filters.get("职位要求", ""),
    ]
    majors = split_multi(filters.get("专业要求", ""))
    if any(value and value != "不限" for value in more_values) or majors:
        actions.append(click_text(page, "更多筛选", "打开更多筛选"))
        time.sleep(0.4)
        for value in more_values:
            if value and value != "不限":
                actions.append(click_text(page, value, "更多筛选"))
        for major in majors[:10]:
            actions.extend(select_major(page, major))
        actions.append(click_text(page, "确定", "确认更多筛选"))

    actions.append(click_search(page))
    time.sleep(1)
    snapshot = page_snapshot(page)
    return {
        "ok": True,
        "message": "BOSS browser search executed",
        "output": "; ".join([item for item in actions if item]),
        "snapshot": snapshot,
    }


def snapshot() -> dict[str, Any]:
    page = open_boss_search()
    lines = page_snapshot(page)
    return {"ok": True, "url": str(page.url), "logged_in": not is_login_page(page, lines), "snapshot": lines}


def is_login_page(page: ChromiumPage, lines: list[str]) -> bool:
    if "/web/user" in str(page.url):
        return True
    text = "\n".join(lines[:40])
    return "登录/注册" in text or "验证码登录" in text or "APP扫码登录" in text


def ensure_search_page(page: ChromiumPage, url: str) -> None:
    if has_search_filters(page):
        return
    if url not in str(page.url):
        page.get(url)
        time.sleep(1.2)
        if has_search_filters(page):
            return
    if click_sidebar_search(page):
        time.sleep(1.2)
        if has_search_filters(page):
            return
    fallback = "https://www.zhipin.com/web/chat/recommend"
    if fallback not in str(page.url):
        page.get(fallback)
        time.sleep(1.2)
        click_sidebar_search(page)
        time.sleep(1.2)


def ensure_filter_panel(page: ChromiumPage) -> None:
    if has_search_filters(page):
        return
    if js_click_text(page, "筛选", exact=True):
        time.sleep(0.6)


def has_search_filters(page: ChromiumPage) -> bool:
    lines = page_snapshot(page)
    text = "\n".join(lines)
    return "学历要求" in text and "年龄要求" in text


def click_sidebar_search(page: ChromiumPage) -> bool:
    return run_js_bool(
        page,
        """
        const nodes = all('button,a,span,div,li,p').filter(visible);
        const target = nodes
          .map(el => ({ el, text: clean(el), rect: el.getBoundingClientRect() }))
          .filter(item => item.text === '搜索' && item.rect.left < Math.min(280, window.innerWidth * 0.25))
          .sort((a, b) => (a.rect.width * a.rect.height) - (b.rect.width * b.rect.height))[0];
        if (!target) return false;
        target.el.click();
        return true;
        """,
    )


def select_city(page: ChromiumPage, city: str) -> str:
    if not city:
        return ""
    frame = search_frame(page)
    if frame:
        try:
            input_ele = frame.ele("css:.city-wrap input", timeout=1)
            input_ele.click()
            input_ele.input(city, clear=True)
            time.sleep(0.6)
            result = frame.ele("css:.search-result-item", timeout=1)
            if result:
                result.click()
                time.sleep(0.3)
                return f"city={city}"
        except Exception:
            pass
    ok = run_js_bool(
        page,
        """
        const text = args[0];
        const doc = searchDoc();
        const wrap = doc.querySelector('.city-wrap');
        const input = doc.querySelector('.city-wrap input');
        if (!wrap || !input) return false;
        wrap.click();
        input.focus();
        setInputValue(input, text);
        pressEnter(input);
        return true;
        """,
        city,
    )
    time.sleep(0.5 if ok else 0.1)
    if js_click_text(page, city, exact=True) or js_click_text(page, city.replace("区", "").replace("县", ""), exact=True):
        return f"city={city}"
    return f"city={city}" if ok else f"city={city}:not-found"


def select_category(page: ChromiumPage, category: str) -> str:
    if not category or "不限" in category:
        return ""
    clicked = run_js_bool(
        page,
        """
        const doc = searchDoc();
        const current = doc.querySelector('.search-current-job, .search-job-list-C .ui-dropmenu-label');
        if (!current) return false;
        current.click();
        return true;
        """,
    )
    time.sleep(0.3 if clicked else 0.1)
    if click_job_dropdown_option(page, category):
        return f"职位={category}"
    if click_job_dropdown_option(page, "不限职位"):
        return "职位=不限职位"
    return f"职位={category}:not-found"


def click_job_dropdown_option(page: ChromiumPage, value: str) -> bool:
    return run_js_bool(
        page,
        """
        const value = args[0];
        const doc = searchDoc();
        const list = doc.querySelector('.search-job-list-C .ui-dropmenu-list, .ui-dropmenu-visible .ui-dropmenu-list');
        if (!list) return false;
        const items = [...list.querySelectorAll('li,div,span')].filter(visible);
        const target = items
          .map(el => ({ el, text: clean(el), rect: el.getBoundingClientRect() }))
          .filter(item => item.text === value)
          .sort((a, b) => (b.rect.width * b.rect.height) - (a.rect.width * a.rect.height))[0];
        if (!target) return false;
        target.el.click();
        return true;
        """,
        value,
    )


def fill_keyword(page: ChromiumPage, keyword: str) -> str:
    if not keyword:
        return ""
    frame = search_frame(page)
    if frame:
        try:
            input_ele = frame.ele("css:input.search-input", timeout=1)
            input_ele.click()
            input_ele.input(keyword, clear=True)
            return f"keyword={keyword}"
        except Exception:
            pass
    ok = run_js_bool(
        page,
        """
        const text = args[0];
        const input = searchDoc().querySelector('input.search-input');
        if (!input) return false;
        input.focus();
        setInputValue(input, text);
        pressEnter(input);
        return true;
        """,
        keyword,
    )
    return f"keyword={keyword}" if ok else f"keyword={keyword}:not-found"


def click_search(page: ChromiumPage) -> str:
    ok = run_js_bool(
        page,
        """
        const doc = searchDoc();
        const input = doc.querySelector('input.search-input');
        if (!input) return false;
        const inputRect = input.getBoundingClientRect();
        const candidates = [...doc.querySelectorAll('button,div,span,a,i,svg')]
          .filter(visible)
          .map(el => ({ el, text: clean(el), cls: String(el.className || ''), rect: el.getBoundingClientRect() }))
          .filter(item => item.rect.top >= inputRect.top - 24 && item.rect.bottom <= inputRect.bottom + 24)
          .filter(item => item.rect.left >= inputRect.right - 20 && item.rect.left <= inputRect.right + 180)
          .filter(item => !/AI/.test(item.text))
          .filter(item => /搜索|search|icon-search/.test(item.text + ' ' + item.cls));
        const target = candidates.sort((a, b) => Math.abs(a.rect.left - inputRect.right) - Math.abs(b.rect.left - inputRect.right))[0]?.el;
        if (target) {
          (target.closest('button,a,div') || target).click();
          return true;
        }
        input.focus();
        pressEnter(input);
        return true;
        """,
    )
    return "search=clicked" if ok else "search=not-found"


def click_text(page: ChromiumPage, text: str, label: str) -> str:
    if not text:
        return ""
    ok = js_click_text(page, text, exact=True) or js_click_text(page, text, exact=False)
    return f"{label}={text}" if ok else f"{label}={text}:not-found"


def select_education(page: ChromiumPage, value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    if "-" not in value:
        return click_text(page, value, "学历")
    parts = [item.strip() for item in value.split("-", 1)]
    if len(parts) != 2:
        return f"学历={value}:not-found"
    levels = ["初中及以下", "中专/中技", "高中", "大专", "本科", "硕士", "博士"]
    if parts[0] not in levels or parts[1] not in levels:
        return f"学历={value}:not-found"
    if not run_js_bool(page, "const el = searchDoc().querySelector('.degree-select-custom-label'); if (!el) return false; el.click(); return true;"):
        return f"学历={value}:not-found"
    time.sleep(0.2)
    if drag_education_range(page, levels.index(parts[0]), levels.index(parts[1]), len(levels)):
        return f"学历={value}"
    return f"学历={value}:not-found"


def drag_education_range(page: ChromiumPage, min_index: int, max_index: int, total: int) -> bool:
    frame = search_frame(page)
    if not frame:
        return False
    try:
        target_values = [min_index + 1, max_index + 1]
        if len(visible_elements(frame.eles("css:.degree-select-custom-slider .ui-slider-button"))) < 2:
            return False
        for index, target in enumerate(target_values):
            for _ in range(total):
                current = current_education_range(page)[index]
                if current == target:
                    break
                handles = visible_elements(frame.eles("css:.degree-select-custom-slider .ui-slider-button"))
                # ponytail: BOSS slider snaps by DPI; these one-step offsets were calibrated on the live page.
                offset_x = 35 if target > current else -10
                frame.actions.move_to(handles[index]).hold().move_to(handles[index], offset_x=offset_x, offset_y=0, duration=0.1).release()
                time.sleep(0.2)
        return current_education_range(page) == target_values
    except Exception:
        return False


def current_education_range(page: ChromiumPage) -> list[int]:
    raw = page.run_js(
        """
        const doc = [...document.querySelectorAll('iframe')]
          .map(frame => frame.contentDocument)
          .find(doc => doc?.querySelector('.degree-select-custom-slider'));
        const slider = [...doc.querySelectorAll('.degree-select-custom-slider')]
          .find(item => item.getBoundingClientRect().width > 0);
        return slider?.querySelector('input[type=hidden]')?.value || '1,7';
        """
    )
    parts = [int(item) for item in str(raw).split(",")[:2] if item.isdigit()]
    return parts if len(parts) == 2 else [1, 7]


def visible_elements(elements):
    visible = []
    for item in elements:
        try:
            if item.rect.size[0] > 0:
                visible.append(item)
        except Exception:
            pass
    return visible


def search_frame(page: ChromiumPage):
    try:
        for frame in page.get_frames():
            if "/web/frame/search/" in str(getattr(frame, "url", "")):
                return frame
    except Exception:
        return None
    return None


def select_major(page: ChromiumPage, value: str) -> list[str]:
    actions: list[str] = []
    if not value:
        return actions
    parts = [item.strip() for item in value.split("/") if item.strip()]
    leaf = "" if not parts or parts[-1] == "全部" else parts[-1]
    if not open_major_dialog(page):
        return [f"专业={value}:not-found"]
    time.sleep(0.3)
    actions.append("专业要求=open")
    selected = bool(leaf and select_major_by_search(page, leaf))
    for part in ([] if selected else [item for item in parts if item != "全部"]):
        actions.append(click_text(page, part, "专业"))
        time.sleep(0.1)
    actions.append(f"专业={leaf or value}" if selected else f"专业路径={value}")
    actions.append(click_text(page, "确定", "确认专业"))
    time.sleep(0.2)
    return actions


def open_major_dialog(page: ChromiumPage) -> bool:
    if js_click_text(page, "选择专业", exact=False) or js_click_text(page, "专业要求", exact=False):
        return True
    run_js_bool(
        page,
        """
        for (const doc of docs()) {
          for (const el of [doc.scrollingElement, ...doc.querySelectorAll('div')].filter(Boolean)) {
            if (el.scrollHeight > el.clientHeight) el.scrollTop = el.scrollHeight;
          }
        }
        return true;
        """,
    )
    time.sleep(0.2)
    if js_click_text(page, "选择专业", exact=False) or js_click_text(page, "专业要求", exact=False):
        return True
    return run_js_bool(
        page,
        """
        const target = all('button,a,span,div,li,p').filter(visible)
          .map(el => ({ el, text: clean(el), rect: el.getBoundingClientRect() }))
          .filter(item => /专业要求|选择专业/.test(item.text))
          .sort((a, b) => (a.rect.width * a.rect.height) - (b.rect.width * b.rect.height))[0]?.el;
        if (!target) return false;
        target.scrollIntoView({ block: 'center', inline: 'center' });
        target.click();
        return true;
        """,
    )


def select_major_by_search(page: ChromiumPage, value: str) -> bool:
    opened = run_js_bool(
        page,
        """
        const text = args[0];
        const doc = docs().find(doc => /请选择专业/.test(clean(doc.body || doc.documentElement)) && doc.querySelector('input[placeholder*="专业"]'));
        const input = doc?.querySelector('input[placeholder*="专业"]');
        if (!input) return false;
        input.focus();
        setInputValue(input, text);
        pressEnter(input);
        const icon = [...doc.querySelectorAll('button,i,svg,span')].filter(visible)
          .find(el => /search|搜索/.test(clean(el) + ' ' + String(el.className || '')));
        if (icon) icon.click();
        return true;
        """,
        value,
    )
    if not opened:
        return False
    time.sleep(0.5)
    return run_js_bool(
        page,
        """
        const text = args[0];
        const doc = docs().find(doc => /请选择专业/.test(clean(doc.body || doc.documentElement)));
        if (!doc) return false;
        const target = [...doc.querySelectorAll('label,li,div,span')].filter(visible)
          .map(el => ({ el, text: clean(el), rect: el.getBoundingClientRect() }))
          .filter(item => item.text === text)
          .sort((a, b) => (a.rect.width * a.rect.height) - (b.rect.width * b.rect.height))[0]?.el;
        if (!target) return false;
        (target.closest('label') || target.closest('li') || target).click();
        return true;
        """,
        value,
    )


def fill_active_or_first_input(page: ChromiumPage, value: str, label: str) -> str:
    if not value:
        return ""
    ok = run_js_bool(
        page,
        """
        const text = args[0];
        const inputs = all('input[type="text"], input:not([type])').filter(visible);
        const preferred = inputs.find(input => /搜索|职位|关键词|专业|城市|区域/.test(input.placeholder || input.name || ''));
        const target = activeInput() || preferred || inputs[inputs.length - 1];
        if (!target) return false;
        target.focus();
        target.value = text;
        target.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: text }));
        target.dispatchEvent(new Event('change', { bubbles: true }));
        target.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }));
        return true;
        """,
        value,
    )
    return f"{label}={value}" if ok else f"{label}={value}:not-found"


def js_click_text(page: ChromiumPage, text: str, exact: bool) -> bool:
    return run_js_bool(
        page,
        """
        const text = args[0];
        const exact = args[1];
        const nodes = all('button,a,span,div,li,p,em').filter(visible);
        const matches = nodes
          .map(el => ({ el, text: clean(el), rect: el.getBoundingClientRect() }))
          .filter(item => item.text && (exact ? item.text === text : item.text.includes(text)))
          .sort((a, b) => (a.rect.width * a.rect.height) - (b.rect.width * b.rect.height));
        if (!matches.length) return false;
        const target = matches[0].el;
        target.scrollIntoView({ block: 'center', inline: 'center' });
        target.click();
        return true;
        """,
        text,
        exact,
    )


def run_js_bool(page: ChromiumPage, body: str, *args: Any) -> bool:
    args_json = ", ".join(json.dumps(arg, ensure_ascii=False) for arg in args)
    script = f"""
    return (function() {{
      function clean(el) {{ return (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim(); }}
      function visible(el) {{
        const style = getComputedStyle(el);
        const rect = el.getBoundingClientRect();
        return style && style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
      }}
      function docs() {{
        const found = [document];
        for (const frame of document.querySelectorAll('iframe')) {{
          try {{ if (frame.contentDocument) found.push(frame.contentDocument); }} catch (e) {{}}
        }}
        return found;
      }}
      function all(selector) {{ return docs().flatMap(doc => [...doc.querySelectorAll(selector)]); }}
      function searchDoc() {{ return docs().find(doc => doc.querySelector('.search-part-container, input.search-input')) || document; }}
      function setInputValue(input, value) {{
        const win = input.ownerDocument.defaultView || window;
        const setter = Object.getOwnPropertyDescriptor(win.HTMLInputElement.prototype, 'value')?.set;
        if (setter) setter.call(input, value); else input.value = value;
        input.dispatchEvent(new InputEvent('input', {{ bubbles: true, inputType: 'insertText', data: value }}));
        input.dispatchEvent(new Event('change', {{ bubbles: true }}));
      }}
      function pressEnter(input) {{
        input.dispatchEvent(new KeyboardEvent('keydown', {{ key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }}));
        input.dispatchEvent(new KeyboardEvent('keyup', {{ key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }}));
      }}
      function activeInput() {{
        for (const doc of docs()) {{
          const el = doc.activeElement;
          if (el && el.tagName === 'INPUT') return el;
        }}
        return null;
      }}
      const args = [{args_json}];
      {body}
    }})();
    """
    try:
        return bool(page.run_js(script))
    except Exception:
        return False


def page_snapshot(page: ChromiumPage) -> list[str]:
    try:
        text = str(page.run_js("""
        return (function collectText(doc) {
          const parts = [doc.body ? doc.body.innerText || '' : ''];
          for (const frame of doc.querySelectorAll('iframe')) {
            try { if (frame.contentDocument) parts.push(collectText(frame.contentDocument)); } catch (e) {}
          }
          return parts.join('\\n');
        })(document);
        """) or "")
    except Exception:
        text = ""
    lines = [line.strip() for line in text.splitlines()]
    return [line for line in lines if line][:120]


def parse_recommended_filters(raw: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in re.split(r"[;；]", raw or ""):
        if not item.strip():
            continue
        parts = re.split(r"[:：=]", item, maxsplit=1)
        if len(parts) == 2:
            result[parts[0].strip()] = parts[1].strip()
    return result


def split_multi(raw: str) -> list[str]:
    return [item.strip() for item in re.split(r"[、,，]", raw or "") if item.strip()]
