from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import dataclass
from typing import Any

try:
    from DrissionPage import ChromiumOptions, ChromiumPage
    from DrissionPage.common import Keys
except ModuleNotFoundError:
    ChromiumOptions = ChromiumPage = Keys = None


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
_boss_chat_signatures: dict[str, str] = {}


def _page_is_connected(page: ChromiumPage) -> bool:
    try:
        _ = page.url
        return True
    except Exception:
        return False


def get_page() -> ChromiumPage:
    global _page
    if ChromiumOptions is None or ChromiumPage is None:
        raise RuntimeError("DrissionPage is not installed; run pip install -r agent-service/requirements.txt")
    with _lock:
        if _page is not None:
            if _page_is_connected(_page):
                return _page
            _page = None
        co = ChromiumOptions()
        co.set_argument("--start-maximized")
        profile_dir = os.getenv(
            "BOSS_BROWSER_PROFILE",
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".dev", "boss-chrome-profile")),
        )
        os.makedirs(profile_dir, exist_ok=True)
        co.set_user_data_path(profile_dir)
        # ponytail: one stable local Chrome profile beats trying to control the user's normal locked browser profile.
        _page = ChromiumPage(co)
        return _page


def get_connected_page() -> ChromiumPage | None:
    global _page
    with _lock:
        if _page is not None and _page_is_connected(_page):
            return _page
        _page = None
        return None


def open_boss_search() -> ChromiumPage:
    page = get_page()
    url = os.getenv("BOSS_SEARCH_URL", "https://www.zhipin.com/web/chat/search")
    current_url = str(page.url)
    if "zhipin.com" not in current_url or "/web/chat/search" not in current_url:
        page.get(url)
        time.sleep(1.2)
    ensure_search_page(page, url)
    return page


def open_boss_chat() -> ChromiumPage:
    page = get_page()
    url = os.getenv("BOSS_CHAT_URL", "https://www.zhipin.com/web/chat/index")
    current_url = str(page.url)
    if "zhipin.com" not in current_url or "/web/chat/index" not in current_url:
        page.get(url)
        time.sleep(1.2)
    return page


def is_boss_chat_page(page: ChromiumPage) -> bool:
    try:
        current_url = str(page.url)
    except Exception:
        return False
    return "zhipin.com" in current_url and "/web/chat/index" in current_url


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
        city_action = select_city(page, payload.city)
        actions.append(city_action)
        if city_action.endswith(":not-found"):
            raise RuntimeError(city_action)
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


def read_candidates(limit: int = 10) -> dict[str, Any]:
    limit = max(1, min(50, int(limit or 10)))
    page = open_boss_search()
    login_lines = page_snapshot(page)
    if is_login_page(page, login_lines):
        raise RuntimeError("BOSS controlled browser is not logged in; login in the opened Chrome window, then retry")
    time.sleep(0.6)
    raw_cards = collect_candidate_cards(page, limit)
    candidates = []
    seen: set[str] = set()
    for raw in raw_cards:
        item = parse_boss_candidate(raw)
        key = "|".join([item["name"], item["current_role"], item["location"], item["profile"][:80]])
        if not item["name"] or key in seen:
            continue
        seen.add(key)
        candidates.append(item)
        if len(candidates) >= limit:
            break
    return {
        "ok": True,
        "message": f"read {len(candidates)} BOSS candidates",
        "candidates": candidates,
    }


def read_chats(limit: int = 20, incremental: bool = False) -> dict[str, Any]:
    limit = max(1, min(50, int(limit or 20)))
    if incremental:
        page = get_connected_page()
        if page is None:
            return {"ok": True, "message": "skip BOSS chat sync: controlled browser is not open", "chats": []}
    else:
        page = open_boss_chat()
    if incremental and not is_boss_chat_page(page):
        return {"ok": True, "message": "skip BOSS chat sync: current page is not chat", "chats": []}
    login_lines = page_snapshot(page)
    if is_login_page(page, login_lines):
        raise RuntimeError("BOSS controlled browser is not logged in; login in the opened Chrome window, then retry")
    time.sleep(0.6)
    chats = []
    seen: set[str] = set()
    if incremental:
        reset_boss_chat_list_scroll(page)
    raw_items = _collect_visible_boss_chat_items(page, limit) if incremental else collect_boss_chat_items(page, limit)
    for raw in raw_items:
        item = parse_boss_chat(raw)
        key = item["key"]
        if not item["name"] or key in seen:
            continue
        signature = boss_chat_signature(item)
        if incremental and _boss_chat_signatures.get(key) == signature:
            continue
        seen.add(key)
        item["_signature"] = signature
        chats.append(item)
        if len(chats) >= limit:
            break
    for item in chats:
        item["messages"] = []
        detail_matched = False
        if not incremental and click_boss_chat_item(page, item["name"], item["role"]):
            time.sleep(0.6)
            if boss_chat_detail_matches(page, item["name"], item["role"]):
                detail_matched = True
                scroll_boss_chat_history_bottom(page)
                time.sleep(0.5)
                item["messages"] = collect_boss_chat_history(page, 40)
        signature = item.pop("_signature", "")
        if signature and (not incremental or detail_matched):
            _boss_chat_signatures[item["key"]] = signature
    return {
        "ok": True,
        "message": f"read {len(chats)} BOSS chats",
        "chats": chats,
    }


def send_chat_message(name: str, role: str = "", content: str = "") -> dict[str, Any]:
    name = (name or "").strip()
    role = (role or "").strip()
    content = (content or "").strip()
    if not name:
        raise RuntimeError("BOSS chat target name is required")
    if not content:
        raise RuntimeError("BOSS message content is required")
    page = open_boss_chat()
    login_lines = page_snapshot(page)
    if is_login_page(page, login_lines):
        raise RuntimeError("BOSS controlled browser is not logged in; login in the opened Chrome window, then retry")
    if not click_boss_chat_item_in_list(page, name, role):
        raise RuntimeError(f"BOSS chat not found in visible list: {name} {role}".strip())
    time.sleep(0.5)
    if not boss_chat_detail_matches(page, name, role):
        raise RuntimeError(f"BOSS chat target mismatch after click: {name} {role}".strip())
    if not fill_boss_chat_input(page, content):
        raise RuntimeError("BOSS chat input not found")
    time.sleep(0.25)
    if not press_boss_chat_enter(page) and not click_boss_send_button(page):
        raise RuntimeError("BOSS send button not found or disabled")
    time.sleep(0.8)
    if boss_chat_input_text(page) == content:
        raise RuntimeError("BOSS send button clicked but message stayed in input")
    return {"ok": True, "message": "BOSS message sent", "target": f"{name} {role}".strip()}


def delete_chat(name: str, role: str = "") -> dict[str, Any]:
    name = (name or "").strip()
    role = (role or "").strip()
    if not name:
        raise RuntimeError("BOSS chat target name is required")
    page = open_boss_chat()
    login_lines = page_snapshot(page)
    if is_login_page(page, login_lines):
        raise RuntimeError("BOSS controlled browser is not logged in; login in the opened Chrome window, then retry")
    if not open_boss_chat_item_menu_in_list(page, name, role):
        raise RuntimeError(f"BOSS chat menu not found: {name} {role}".strip())
    time.sleep(0.25)
    if not js_click_text(page, "删除", exact=True) and not js_click_text(page, "删除", exact=False):
        raise RuntimeError("BOSS delete menu item not found")
    time.sleep(0.35)
    if not (js_click_text(page, "确定", exact=True) or js_click_text(page, "确认", exact=True)):
        raise RuntimeError("BOSS delete confirm button not found")
    time.sleep(0.8)
    return {"ok": True, "message": "BOSS chat deleted", "target": f"{name} {role}".strip()}


def click_boss_chat_item(page: ChromiumPage, name: str, role: str = "") -> bool:
    return run_js_bool(
        page,
        """
        const name = args[0];
        const role = args[1];
        const direct = all('.geek-item-wrap,.geek-item')
          .map(el => ({ el, text: clean(el), rect: el.getBoundingClientRect() }))
          .filter(item => item.text.includes(name))
          .filter(item => !role || item.text.includes(role))
          .sort((a, b) => a.rect.top - b.rect.top || a.text.length - b.text.length)[0]?.el;
        if (direct) {
          const target = direct.closest('.geek-item-wrap') || direct;
          target.scrollIntoView({ block: 'center', inline: 'center' });
          target.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
          target.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
          target.click();
          return true;
        }
        const maxLeft = Math.min(900, window.innerWidth * 0.5);
        const candidates = all('li,article,section,div').filter(visible)
          .map(el => ({ el, text: clean(el), rect: el.getBoundingClientRect() }))
          .filter(item => item.text.includes(name))
          .filter(item => !role || item.text.includes(role))
          .filter(item => item.rect.left < maxLeft)
          .filter(item => item.rect.width >= 180 && item.rect.width <= 620)
          .filter(item => item.rect.height >= 36 && item.rect.height <= 160)
          .filter(item => item.text.length >= name.length && item.text.length <= 260)
          .sort((a, b) => a.rect.top - b.rect.top || a.text.length - b.text.length);
        const target = candidates[0]?.el;
        if (!target) return false;
        target.scrollIntoView({ block: 'center', inline: 'center' });
        (target.closest('li') || target).click();
        return true;
        """,
        name,
        role,
    )


def click_boss_chat_item_in_list(page: ChromiumPage, name: str, role: str = "", attempts: int = 10) -> bool:
    reset_boss_chat_list_scroll(page)
    for _ in range(max(1, attempts)):
        if click_boss_chat_item(page, name, role):
            return True
        if not scroll_boss_chat_list(page):
            break
        time.sleep(0.25)
    return False


def open_boss_chat_item_menu_in_list(page: ChromiumPage, name: str, role: str = "", attempts: int = 10) -> bool:
    reset_boss_chat_list_scroll(page)
    for _ in range(max(1, attempts)):
        if open_boss_chat_item_menu(page, name, role):
            return True
        if not scroll_boss_chat_list(page):
            break
        time.sleep(0.25)
    return False


def boss_chat_detail_matches(page: ChromiumPage, name: str, role: str = "") -> bool:
    try:
        script = """
            return (function() {
              function clean(el) { return (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim(); }
              function visible(el) {
                const style = getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style && style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
              }
              const name = __NAME__;
              const nodes = [...document.querySelectorAll('main,section,article,header,div')].filter(visible)
                .map(el => ({ text: clean(el), rect: el.getBoundingClientRect() }))
                .filter(item => item.rect.left > Math.min(520, window.innerWidth * 0.34))
                .filter(item => item.text.includes(name))
                .filter(item => item.text.length <= 3000)
                .sort((a, b) => a.rect.left - b.rect.left || b.text.length - a.text.length);
              return nodes.slice(0, 3).map(item => item.text).join('\\n');
            })();
            """.replace("__NAME__", json.dumps(name, ensure_ascii=False))
        text = str(page.run_js(script) or "")
    except Exception:
        return False
    return boss_chat_detail_text_matches(text, name, role)


def boss_chat_detail_text_matches(text: str, name: str, role: str = "") -> bool:
    normalized = re.sub(r"\s+", " ", text or "")
    return bool(name and name in normalized and (not role or role in normalized))


def open_boss_chat_item_menu(page: ChromiumPage, name: str, role: str = "") -> bool:
    return run_js_bool(
        page,
        """
        const name = args[0];
        const role = args[1];
        const panes = all('div,ul,section')
          .map(el => ({ el, rect: el.getBoundingClientRect() }))
          .filter(item => visible(item.el))
          .filter(item => item.el.scrollHeight > item.el.clientHeight + 80)
          .filter(item => item.rect.left < Math.min(900, window.innerWidth * 0.55))
          .filter(item => item.rect.width >= 220 && item.rect.width <= 700)
          .filter(item => item.rect.height >= 220)
          .sort((a, b) => b.rect.height - a.rect.height);
        const root = panes[0]?.el || document;
        const rows = [...root.querySelectorAll('.geek-item-wrap,.geek-item,li,article,section,div')]
          .map(el => ({ el, text: clean(el), rect: el.getBoundingClientRect() }))
          .filter(item => item.text.includes(name))
          .filter(item => !role || item.text.includes(role))
          .filter(item => item.rect.left < Math.min(760, window.innerWidth * 0.42))
          .filter(item => item.rect.width >= 180 && item.rect.height >= 36 && item.rect.height <= 180)
          .sort((a, b) => a.rect.top - b.rect.top || a.text.length - b.text.length);
        const row = rows[0]?.el.closest('.geek-item-wrap') || rows[0]?.el;
        if (!row) return false;
        row.scrollIntoView({ block: 'center', inline: 'center' });
        for (const type of ['mouseenter', 'mouseover', 'mousemove']) {
          row.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, view: window }));
        }
        const rowRect = row.getBoundingClientRect();
        const op = row.querySelector('.user-operation,.icon-operate,.list-operate') ||
          [...row.querySelectorAll('img,button,span,div')]
            .map(el => ({ el, rect: el.getBoundingClientRect(), cls: String(el.className || '') }))
            .filter(item => /operate|operation|more|menu/i.test(item.cls) || item.rect.right > rowRect.right - 80)
            .sort((a, b) => b.rect.left - a.rect.left)[0]?.el;
        const doc = row.ownerDocument || document;
        const x = Math.max(rowRect.left + 8, rowRect.right - 28);
        const y = rowRect.top + rowRect.height / 2;
        const target = (op && (op.querySelector('img,button,span,div') || op)) || doc.elementFromPoint(x, y);
        if (!target) return false;
        if (op) {
          op.style.visibility = 'visible';
          op.style.opacity = '1';
          if (getComputedStyle(op).display === 'none') op.style.display = 'block';
        }
        for (const type of ['mousemove', 'mousedown', 'mouseup', 'click']) {
          target.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, view: window, clientX: x, clientY: y }));
        }
        for (const type of ['mousedown', 'mouseup', 'click']) {
          target.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, view: window }));
        }
        target.click();
        return true;
        """,
        name,
        role,
    )


def fill_boss_chat_input(page: ChromiumPage, content: str) -> bool:
    return run_js_bool(
        page,
        """
        const text = args[0];
        const inputs = all('textarea,[contenteditable="true"],input[type="text"],input:not([type])').filter(visible)
          .map(el => ({ el, rect: el.getBoundingClientRect(), ph: el.getAttribute('placeholder') || '' }))
          .filter(item => item.rect.top > window.innerHeight * 0.55)
          .filter(item => !/搜索|search/i.test(item.ph))
          .sort((a, b) => b.rect.bottom - a.rect.bottom || b.rect.width - a.rect.width);
        const target = inputs[0]?.el;
        if (!target) return false;
        target.focus();
        if (target.isContentEditable) {
          const doc = target.ownerDocument;
          const selection = doc.getSelection();
          const range = doc.createRange();
          range.selectNodeContents(target);
          if (selection) {
            selection.removeAllRanges();
            selection.addRange(range);
          }
          doc.execCommand('insertText', false, text);
          target.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: text }));
        } else {
          setInputValue(target, text);
        }
        return true;
        """,
        content,
    )


def click_boss_send_button(page: ChromiumPage) -> bool:
    return run_js_bool(
        page,
        """
        const target = [...document.querySelectorAll('.submit-content')]
          .filter(visible)
          .map(el => ({ el, text: clean(el), rect: el.getBoundingClientRect(), cls: String(el.className || '') }))
          .filter(item => item.text === '发送')
          .filter(item => item.rect.top > window.innerHeight * 0.7 && item.rect.left > window.innerWidth * 0.55)
          .sort((a, b) => b.rect.top - a.rect.top)[0]?.el;
        if (!target) return false;
        const button = target.querySelector('.submit.active') || target;
        if (/disabled|disable/.test(String(button.className || ''))) return false;
        for (const type of ['mousedown', 'mouseup', 'click']) {
          target.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, view: window }));
        }
        target.click();
        return true;
        """,
    )


def press_boss_chat_enter(page: ChromiumPage) -> bool:
    return run_js_bool(
        page,
        """
        const input = document.querySelector('#boss-chat-editor-input,[contenteditable="true"].boss-chat-editor-input');
        if (!input) return false;
        input.focus();
        for (const type of ['keydown', 'keypress', 'keyup']) {
          input.dispatchEvent(new KeyboardEvent(type, {
            key: 'Enter',
            code: 'Enter',
            keyCode: 13,
            which: 13,
            bubbles: true,
            cancelable: true
          }));
        }
        return true;
        """,
    )


def boss_chat_input_text(page: ChromiumPage) -> str:
    try:
        return str(page.run_js("""
        const input = document.querySelector('#boss-chat-editor-input,[contenteditable="true"].boss-chat-editor-input');
        return (input?.innerText || input?.textContent || '').trim();
        """) or "").strip()
    except Exception:
        return ""


def _collect_visible_boss_chat_items(page: ChromiumPage, limit: int) -> list[str]:
    script = f"""
    return (function(limit) {{
      function cleanText(value) {{ return String(value || '').replace(/\\s+/g, '\\n').replace(/\\n+/g, '\\n').trim(); }}
      function docs() {{
        const found = [document];
        for (const frame of document.querySelectorAll('iframe')) {{
          try {{ if (frame.contentDocument) found.push(frame.contentDocument); }} catch (e) {{}}
        }}
        return found;
      }}
      function visible(el) {{
        const style = getComputedStyle(el);
        const rect = el.getBoundingClientRect();
        return style && style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
      }}
      const blacklist = /全部职位|全部\\n未读|新招呼|沟通中|已约面|已获取简历|已交换电话|已交换微信|收藏|更多|在线简历|附件简历|求简历|换电话|换微信|约面试/;
      const candidates = docs().flatMap(doc => [...doc.querySelectorAll('li,article,section,div')])
        .filter(visible)
        .map(el => {{
          const rect = el.getBoundingClientRect();
          const text = cleanText(el.innerText || el.textContent);
          return {{ text, lines: text.split('\\n').filter(Boolean), top: rect.top, left: rect.left, width: rect.width, height: rect.height, area: rect.width * rect.height }};
        }})
        .filter(item => item.text.length >= 6 && item.text.length <= 260)
        .filter(item => item.lines.length >= 2 && item.lines.length <= 5)
        .filter(item => item.width >= 220 && item.width <= 620 && item.height >= 44 && item.height <= 130)
        .filter(item => item.left < Math.min(900, window.innerWidth * 0.48))
        .filter(item => !blacklist.test(item.text))
        .filter(item => !/\\d{{2}}岁|期望\\n|职位\\n|在线简历|附件简历/.test(item.text))
        .filter(item => /\\[已读\\]|\\[未读\\]|\\d{{1,2}}:\\d{{2}}|昨天|\\d{{2}}月\\d{{2}}日/.test(item.text))
        .sort((a, b) => a.top - b.top || a.left - b.left || a.area - b.area);
      const out = [];
      const keys = new Set();
      for (const item of candidates) {{
        const key = item.text.replace(/\\n/g, ' ').slice(0, 90);
        if (keys.has(key)) continue;
        if (out.some(text => text.includes(item.text) || item.text.includes(text))) continue;
        keys.add(key);
        out.push(item.text);
        if (out.length >= limit) break;
      }}
      return out;
    }})({limit});
    """
    try:
        raw = page.run_js(script) or []
    except Exception:
        raw = []
    return [str(item).strip() for item in raw if str(item).strip()]

def collect_boss_chat_items(page: ChromiumPage, limit: int) -> list[str]:
    collected: list[str] = []
    seen: set[str] = set()
    stagnant = 0
    for _ in range(10):
        before = len(collected)
        for raw in _collect_visible_boss_chat_items(page, limit):
            key = re.sub(r"\s+", " ", raw).strip()[:120]
            if not key or key in seen:
                continue
            seen.add(key)
            collected.append(raw)
            if len(collected) >= limit:
                return collected
        stagnant = stagnant + 1 if len(collected) == before else 0
        if stagnant >= 2 or not scroll_boss_chat_list(page):
            break
        time.sleep(0.25)
    return collected


def scroll_boss_chat_list(page: ChromiumPage) -> bool:
    # ponytail: DOM-based BOSS list detection is heuristic; replace with official chat API if one is available.
    return run_js_bool(
        page,
        """
        const panes = all('div,ul,section')
          .map(el => ({ el, rect: el.getBoundingClientRect() }))
          .filter(item => visible(item.el))
          .filter(item => item.el.scrollHeight > item.el.clientHeight + 80)
          .filter(item => item.rect.left < Math.min(900, window.innerWidth * 0.55))
          .filter(item => item.rect.width >= 220 && item.rect.width <= 700)
          .filter(item => item.rect.height >= 220)
          .sort((a, b) => b.rect.height - a.rect.height);
        const target = panes[0]?.el;
        if (!target) return false;
        const before = target.scrollTop;
        const max = target.scrollHeight - target.clientHeight;
        target.scrollTop = Math.min(max, before + Math.max(160, Math.floor(target.clientHeight * 0.8)));
        target.dispatchEvent(new Event('scroll', { bubbles: true }));
        return target.scrollTop > before;
        """,
    )


def reset_boss_chat_list_scroll(page: ChromiumPage) -> None:
    run_js_bool(
        page,
        """
        const panes = all('div,ul,section')
          .map(el => ({ el, rect: el.getBoundingClientRect() }))
          .filter(item => visible(item.el))
          .filter(item => item.el.scrollHeight > item.el.clientHeight + 80)
          .filter(item => item.rect.left < Math.min(900, window.innerWidth * 0.55))
          .filter(item => item.rect.width >= 220 && item.rect.width <= 700)
          .filter(item => item.rect.height >= 220)
          .sort((a, b) => b.rect.height - a.rect.height);
        if (panes[0]) panes[0].el.scrollTop = 0;
        return true;
        """,
    )


def collect_boss_chat_history(page: ChromiumPage, limit: int = 40) -> list[dict[str, str]]:
    script = f"""
    return (function(limit) {{
      function cleanText(value) {{ return String(value || '').replace(/\\s+/g, ' ').trim(); }}
      const items = [...document.querySelectorAll('.message-item')]
        .map(el => {{
          const mine = el.querySelector('.item-myself');
          const friend = el.querySelector('.item-friend');
          const bubble = el.querySelector('.item-myself .text-content') ||
            el.querySelector('.item-friend .text-content') ||
            el.querySelector('.item-myself .text') ||
            el.querySelector('.item-friend .text');
          return {{
            sender: mine ? 'agent' : (friend ? 'candidate' : ''),
            content: cleanText(bubble?.innerText || bubble?.textContent || '').replace(/^(已读|送达)\\s+/, ''),
            time_text: cleanText(el.querySelector('.message-time')?.innerText || '')
          }};
        }})
        .filter(item => item.sender && item.content);
      const latest = items.slice(Math.max(0, items.length - limit));
      const out = [];
      for (const item of latest) {{
        out.push(item);
        if (out.length >= limit) break;
      }}
      return out;
    }})({limit});
    """
    try:
        raw = page.run_js(script) or []
    except Exception:
        raw = []
    messages: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        content = str(item.get("content", "")).strip()
        sender = str(item.get("sender", "")).strip()
        if content:
            messages.append({"sender": sender, "content": content, "time_text": str(item.get("time_text", "")).strip()})
    return messages


def scroll_boss_chat_history_bottom(page: ChromiumPage) -> bool:
    # ponytail: background incremental sync avoids detail scrolling; full sync only needs the visible newest end.
    return run_js_bool(
        page,
        """
        const target = document.querySelector('.conversation-message');
        if (!target) return false;
        target.scrollTop = target.scrollHeight;
        target.dispatchEvent(new Event('scroll', { bubbles: true }));
        return true;
        """,
    )


def boss_chat_signature(item: dict[str, str]) -> str:
    return "|".join(
        [
            str(item.get("key", "")).strip(),
            str(item.get("last_sender", "")).strip(),
            str(item.get("last_message", "")).strip(),
            str(item.get("time_text", "")).strip(),
        ]
    )


def parse_boss_chat(raw: str) -> dict[str, str]:
    text = normalize_card_text(raw)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    status_prefix = r"^\[(已读|未读|送达|宸茶|鏈|閫佽揪)\]\s*"
    status_names = {"已读", "未读", "送达", "宸茶", "鏈", "閫佽揪"}
    agent_status_prefix = r"^\[(送达|閫佽揪)\]\s*"
    # ponytail: BOSS list "[已读]20" means the candidate's message was read, not that we sent it.
    last_sender = "agent" if any(re.match(agent_status_prefix, line) for line in lines) else "candidate"
    cleaned = [re.sub(r"^\[(已读|未读)\]\s*", "", line).strip() for line in lines]
    time_text = next((line for line in cleaned if re.fullmatch(r"\d{1,2}:\d{2}|昨天|\d{2}月\d{2}日|\d{4}\.\d{2}\.\d{2}", line)), "")
    body = [line for line in cleaned if line and line != time_text]
    body = [re.sub(status_prefix, "", line).strip() for line in body]
    while body and re.fullmatch(r"\d+", body[0]):
        body = body[1:]
    name, role, last_message = "", "", ""
    if len(body) >= 3 and not re.search(r"\s", body[0]):
        name, role = body[0], body[1]
        last_message = " ".join(body[2:])
    elif body:
        info = re.sub(r"\s*\d{1,2}:\d{2}$", "", body[0]).strip()
        parts = [part for part in re.split(r"\s+", info, maxsplit=1) if part]
        name = parts[0] if parts else ""
        role = parts[1] if len(parts) > 1 else ""
        last_message = body[1] if len(body) > 1 else ""
    if not re.fullmatch(r"[\u4e00-\u9fa5A-Za-z*]{1,12}", name or ""):
        name = ""
    if name in status_names or not role:
        name, role, last_message = "", "", ""
    key = "|".join([name, role]) if name else ""
    return {
        "key": key,
        "name": name,
        "role": role,
        "last_message": last_message,
        "last_sender": last_sender,
        "time_text": time_text,
        "profile": "\n".join(lines[:8]),
    }


def collect_candidate_cards(page: ChromiumPage, limit: int) -> list[str]:
    script = f"""
    return (function(limit) {{
      function cleanText(value) {{ return String(value || '').replace(/\\s+/g, '\\n').replace(/\\n+/g, '\\n').trim(); }}
      function docs() {{
        const found = [document];
        for (const frame of document.querySelectorAll('iframe')) {{
          try {{ if (frame.contentDocument) found.push(frame.contentDocument); }} catch (e) {{}}
        }}
        return found;
      }}
      function visible(el) {{
        const style = getComputedStyle(el);
        const rect = el.getBoundingClientRect();
        return style && style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
      }}
      function cardKey(text) {{
        const hit = text.match(/([\\u4e00-\\u9fa5A-Za-z·*]{{1,12}})[\\s\\S]{{0,80}}?(\\d{{2}})\\s*岁/);
        return hit ? `${{hit[1]}}-${{hit[2]}}` : text.slice(0, 60);
      }}
      const blacklist = /学历要求|年龄要求|推荐筛选|更多筛选|筛选说明|请选择专业|开启AI搜索|综合排序|匹配度优先/;
      const nodes = docs().flatMap(doc => [...doc.querySelectorAll('article,section,li,div')]);
      const cards = nodes
        .filter(visible)
        .map(el => {{
          const rect = el.getBoundingClientRect();
          return {{ text: cleanText(el.innerText || el.textContent), top: rect.top, left: rect.left, area: rect.width * rect.height, width: rect.width, height: rect.height }};
        }})
        .filter(item => item.text.length >= 35 && item.text.length <= 1200)
        .filter(item => item.width >= 360 && item.height >= 70 && item.height <= 420)
        .filter(item => /\\d{{2}}\\s*岁/.test(item.text))
        .filter(item => /K|经验|应届|离职|到岗|期望|职位|学校|院校|活跃/.test(item.text))
        .filter(item => !blacklist.test(item.text))
        .sort((a, b) => a.top - b.top || b.area - a.area);
      const out = [];
      const keys = new Set();
      for (const card of cards) {{
        const key = cardKey(card.text);
        if (keys.has(key)) continue;
        if (out.some(item => item.includes(card.text) || card.text.includes(item))) continue;
        keys.add(key);
        out.push(card.text);
        if (out.length >= limit) break;
      }}
      return out;
    }})({limit});
    """
    try:
        raw = page.run_js(script) or []
    except Exception:
        raw = []
    return [str(item).strip() for item in raw if str(item).strip()]


def parse_boss_candidate(raw: str) -> dict[str, str]:
    text = normalize_card_text(raw)
    lines = [line.strip(" |｜\t") for line in text.splitlines() if line.strip(" |｜\t")]
    summary = next((line for line in lines if re.search(r"\d{2}\s*岁", line)), "")
    name = parse_candidate_name(lines, text)
    location = parse_candidate_label(text, ["期望城市", "期望"])
    current_role = parse_candidate_label(text, ["职位", "当前职位", "最近职位"])
    if not current_role and summary:
        current_role = " | ".join(split_card_parts(summary)[1:3])
    tags = ", ".join(split_card_parts(summary)[1:])
    return {
        "name": name,
        "source": "BOSS",
        "current_role": current_role,
        "location": location,
        "tags": tags,
        "profile": "\n".join(lines[:18]),
    }


def normalize_card_text(raw: str) -> str:
    return re.sub(r"\n{2,}", "\n", re.sub(r"[ \t]+", " ", raw or "")).strip()


def parse_candidate_name(lines: list[str], text: str) -> str:
    for line in lines[:4]:
        hit = re.match(r"^([\u4e00-\u9fa5A-Za-z·*]{1,12})", line)
        if hit and not any(word in hit.group(1) for word in ["搜索", "筛选", "学历", "年龄"]):
            return hit.group(1)
    hit = re.search(r"([\u4e00-\u9fa5A-Za-z·*]{1,12})[\s\S]{0,80}?\d{2}\s*岁", text)
    return hit.group(1) if hit else ""


def parse_candidate_label(text: str, labels: list[str]) -> str:
    for label in labels:
        hit = re.search(rf"{label}\s*[:：]?\s*([^\n]+)", text)
        if hit:
            value = hit.group(1).strip(" ·|｜")
            if label.startswith("期望"):
                return re.split(r"\s*[·|｜]\s*", value, maxsplit=1)[0].strip()
            return value
    return ""


def split_card_parts(line: str) -> list[str]:
    return [item.strip() for item in re.split(r"\s*[|｜]\s*", line or "") if item.strip()]


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
    city = (city or "").strip()
    if not city:
        return ""
    search_city, area = split_boss_city_area(city)
    frame = search_frame(page)
    if frame:
        try:
            input_ele = frame.ele("css:.city-wrap input", timeout=1)
            input_ele.click()
            input_ele.input(search_city, clear=True)
            time.sleep(0.6)
            result = frame.ele("css:.search-result-item", timeout=1)
            if result:
                result.click()
                time.sleep(0.3)
                if boss_search_city_selected(page, search_city):
                    return city_action_result(city, search_city, area, select_boss_area(page, area))
        except Exception:
            pass
    ok = run_js_bool(
        page,
        """
        const text = args[0];
        const wrap = all('.city-wrap, .city-or-area-name, .search-city-kw')
          .filter(visible)
          .map(el => ({ el, rect: el.getBoundingClientRect() }))
          .sort((a, b) => a.rect.top - b.rect.top || a.rect.left - b.rect.left)[0]?.el;
        if (!wrap) return false;
        wrap.click();
        const input = activeInput() ||
          all('.city-wrap input, .city-or-area-name input, input[placeholder*="城市"], input[placeholder*="区域"], input[placeholder*="地区"], input[type="text"], input:not([type])')
            .filter(visible)
            .find(input => /城市|区域|地区|搜索/.test(input.placeholder || '') || input.getBoundingClientRect().top < window.innerHeight * 0.35);
        if (!input) return false;
        input.focus();
        setInputValue(input, text);
        pressEnter(input);
        return true;
        """,
        search_city,
    )
    time.sleep(0.5 if ok else 0.1)
    if click_city_text(page, search_city) and boss_search_city_selected(page, search_city):
        return city_action_result(city, search_city, area, select_boss_area(page, area))
    if boss_search_city_selected(page, search_city):
        return city_action_result(city, search_city, area, select_boss_area(page, area))
    return f"city={city}:not-found"


def city_action_result(city: str, search_city: str, area: str, area_selected: bool) -> str:
    if area and not area_selected:
        return f"city={search_city}; area={area}:not-selected"
    return f"city={city}"


def split_boss_city_area(city: str) -> tuple[str, str]:
    city = (city or "").strip()
    if "市" in city and not city.endswith("市"):
        head, tail = city.split("市", 1)
        return (head + "市").strip(), tail.strip()
    return city, ""


def select_boss_area(page: ChromiumPage, area: str) -> bool:
    if not area:
        return True
    run_js_bool(page, "const el = all('.city-wrap, .city-or-area-name, .search-city-kw').filter(visible)[0]; if (!el) return false; el.click(); return true;")
    time.sleep(0.2)
    if not click_city_text(page, area):
        close_boss_city_search(page)
        return False
    time.sleep(0.2)
    if boss_search_city_selected(page, area):
        return True
    close_boss_city_search(page)
    return False


def close_boss_city_search(page: ChromiumPage) -> None:
    target = search_frame(page) or page
    try:
        target.run_js(
            """
            const input = document.querySelector('.city-wrap input');
            if (input) {
              input.value = '';
              input.dispatchEvent(new Event('input', { bubbles: true }));
              input.blur();
            }
            document.body.click();
            """
        )
    except Exception:
        pass


def click_city_text(page: ChromiumPage, city: str) -> bool:
    short_city = city.replace("区", "").replace("县", "")
    return js_click_text(page, city, exact=True) or (short_city != city and js_click_text(page, short_city, exact=True))


def boss_search_city_selected(page: ChromiumPage, city: str) -> bool:
    short_city = city.replace("区", "").replace("县", "")
    return run_js_bool(
        page,
        """
        const names = args[0].filter(Boolean);
        const nodes = all('.city-wrap, .city-or-area-name, .search-city-kw')
          .filter(visible)
          .map(el => clean(el));
        return nodes.some(text => names.some(name => text.includes(name)));
        """,
        [city, short_city],
    )


def select_category(page: ChromiumPage, category: str) -> str:
    if not category:
        return ""
    target_category = "不限职位" if "不限" in category else category
    clicked = open_job_category_dropdown(page)
    time.sleep(0.3 if clicked else 0.1)
    if click_job_dropdown_option(page, target_category):
        return f"职位={target_category}"
    if click_job_dropdown_option(page, "不限职位"):
        return "职位=不限职位"
    return f"职位={target_category}:not-found"


def open_job_category_dropdown(page: ChromiumPage) -> bool:
    return run_js_bool(
        page,
        """
        const doc = searchDoc();
        const current = doc.querySelector('.search-current-job, .search-job-list-C .ui-dropmenu-label, .job-selecter-wrap .ui-dropmenu-label, .job-selecter-wrap');
        if (current) {
          current.click();
          return true;
        }
        const input = doc.querySelector('input.search-input');
        if (!input) return false;
        const inputRect = input.getBoundingClientRect();
        const target = [...doc.querySelectorAll('button,a,span,div')]
          .filter(visible)
          .map(el => ({ el, text: clean(el), rect: el.getBoundingClientRect() }))
          .filter(item => item.rect.top >= inputRect.top - 24 && item.rect.bottom <= inputRect.bottom + 24)
          .filter(item => item.rect.right <= inputRect.left + 30 && item.rect.left >= inputRect.left - 360)
          .filter(item => item.text && item.text.length <= 20)
          .sort((a, b) => Math.abs(a.rect.right - inputRect.left) - Math.abs(b.rect.right - inputRect.left))[0]?.el;
        if (!target) return false;
        target.click();
        return true;
        """,
    )


def click_job_dropdown_option(page: ChromiumPage, value: str) -> bool:
    return run_js_bool(
        page,
        """
        const value = args[0];
        const doc = searchDoc();
        const lists = [...doc.querySelectorAll('.search-job-list-C .ui-dropmenu-list, .job-selecter-wrap .ui-dropmenu-list, .ui-dropmenu-visible .ui-dropmenu-list, .ui-dropmenu-list')]
          .filter(visible);
        const roots = lists.length ? lists : [doc];
        const input = doc.querySelector('input.search-input');
        const inputRect = input ? input.getBoundingClientRect() : null;
        const items = roots.flatMap(root => [...root.querySelectorAll('li,div,span,a')].filter(visible));
        const target = items
          .map(el => ({ el, text: clean(el), rect: el.getBoundingClientRect() }))
          .filter(item => !inputRect || item.rect.top <= inputRect.bottom + 260)
          .filter(item => item.text === value || (value.includes('不限') && item.text.includes('不限')))
          .sort((a, b) => Math.abs(a.rect.top - (inputRect ? inputRect.bottom : 0)) - Math.abs(b.rect.top - (inputRect ? inputRect.bottom : 0)))[0];
        if (!target) return false;
        target.el.click();
        return true;
        """,
        value,
    )


def boss_search_keyword_value(page: ChromiumPage) -> str:
    try:
        return str(
            page.run_js(
                """
                const doc = searchDoc();
                const input = doc.querySelector('input.search-input');
                return input ? String(input.value || input.getAttribute('value') || '').trim() : '';
                """
            )
            or ""
        ).strip()
    except Exception:
        return ""


def fill_keyword(page: ChromiumPage, keyword: str) -> str:
    if not keyword:
        return ""
    frame = search_frame(page)
    if frame:
        try:
            input_ele = frame.ele("css:input.search-input", timeout=1)
            input_ele.click()
            input_ele.input(keyword, clear=True)
            if boss_search_keyword_value(page) == keyword:
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
    if press_search_enter(page):
        time.sleep(0.5)
        return "search=entered"
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


def press_search_enter(page: ChromiumPage) -> bool:
    if Keys is None:
        return False
    targets = []
    frame = search_frame(page)
    if frame:
        targets.append(frame)
    targets.append(page)
    for target in targets:
        try:
            input_ele = target.ele("css:input.search-input", timeout=1)
            input_ele.click()
            time.sleep(0.05)
            page.actions.type(Keys.ENTER)
            return True
        except Exception:
            pass
    return False


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
        const proto = input instanceof win.HTMLTextAreaElement ? win.HTMLTextAreaElement.prototype : win.HTMLInputElement.prototype;
        const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
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
