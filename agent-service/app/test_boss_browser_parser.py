from app.boss_browser import _page_is_connected, boss_chat_detail_text_matches, boss_chat_input_text, boss_chat_signature, parse_boss_candidate, parse_boss_chat


def test_page_is_connected_handles_dead_page() -> None:
    class DeadPage:
        @property
        def url(self) -> str:
            raise RuntimeError("page disconnected")

    assert not _page_is_connected(DeadPage())


def test_boss_chat_input_text_handles_js_error() -> None:
    class BrokenPage:
        def run_js(self, script: str):
            raise RuntimeError("page disconnected")

    assert boss_chat_input_text(BrokenPage()) == ""


def test_boss_chat_detail_text_matches_requires_same_person() -> None:
    assert boss_chat_detail_text_matches("黄有龙 刚刚活跃 沟通职位：锯床操作工", "黄有龙", "锯床操作工")
    assert not boss_chat_detail_text_matches("ccccccc 刚刚活跃 沟通职位：锯床操作工", "黄有龙", "锯床操作工")


def test_parse_boss_candidate_card() -> None:
    raw = """
林**
20岁 | 26年应届生 | 大专 | 离校-随时到岗 | 2-4K
本人做过餐饮前厅服务员，能接受轮班。
期望 厦门 · 服务员
职位 麦当劳 · 服务员
"""
    item = parse_boss_candidate(raw)
    assert item["name"] == "林**"
    assert "服务员" in item["current_role"]
    assert "厦门" in item["location"]
    assert "大专" in item["tags"]


def test_parse_boss_chat_item() -> None:
    item = parse_boss_chat("刘杰 锯床工\n[已读] 你好，刚刚看了你的简历\n11:25")
    assert item["name"] == "刘杰"
    assert item["role"] == "锯床工"
    assert item["last_message"] == "你好，刚刚看了你的简历"
    assert item["time_text"] == "11:25"
    assert item["key"] == "刘杰|锯床工"

    item = parse_boss_chat("11:25\n刘杰\n锯床工\n[已读]你好，刚刚看了你的简历")
    assert item["name"] == "刘杰"
    assert item["role"] == "锯床工"
    assert item["last_message"] == "你好，刚刚看了你的简历"
    assert item["key"] == "刘杰|锯床工"

    item = parse_boss_chat("06月24日\n吴金发\n锯床工\n老板\n招师傅吗？")
    assert item["name"] == "吴金发"
    assert item["last_message"] == "老板 招师傅吗？"


def test_parse_boss_chat_skips_unread_count() -> None:
    item = parse_boss_chat("1\n22:12\n钟思绮\n锯床操作工\n牛人钟思绮向您发起了沟通")
    assert item["name"] == "钟思绮"
    assert item["role"] == "锯床操作工"
    assert item["last_message"] == "牛人钟思绮向您发起了沟通"
    assert item["last_sender"] == "candidate"


def test_parse_boss_chat_ignores_status_fragment() -> None:
    item = parse_boss_chat("20:31\n\u5df2\u8bfb\n1")
    assert item["name"] == ""
    assert item["key"] == ""


def test_parse_boss_chat_requires_role() -> None:
    item = parse_boss_chat("20:53\n我没什么经验")
    assert item["name"] == ""
    assert item["key"] == ""


def test_parse_boss_chat_marks_agent_last_message() -> None:
    item = parse_boss_chat("Alice Worker\n[送达] hello\n11:25")
    assert item["name"] == "Alice"
    assert item["last_message"] == "hello"
    assert item["last_sender"] == "agent"

    item = parse_boss_chat("Bob Worker\nhello\n11:26")
    assert item["name"] == "Bob"
    assert item["last_message"] == "hello"
    assert item["last_sender"] == "candidate"


def test_parse_boss_chat_read_status_is_candidate_message() -> None:
    item = parse_boss_chat("01:37\nccccccc\n锯床操作工\n[已读]20")
    assert item["name"] == "ccccccc"
    assert item["role"] == "锯床操作工"
    assert item["last_message"] == "20"
    assert item["last_sender"] == "candidate"


def test_boss_chat_signature_changes_on_latest_message() -> None:
    first = parse_boss_chat("Alice Worker\nhello\n11:25")
    same = parse_boss_chat("Alice Worker\nhello\n11:25")
    changed = parse_boss_chat("Alice Worker\nnew message\n11:26")

    assert boss_chat_signature(first) == boss_chat_signature(same)
    assert boss_chat_signature(first) != boss_chat_signature(changed)


def test_collect_boss_chat_items_scrolls_visible_pages() -> None:
    import app.boss_browser as boss_browser

    pages = [
        ["Alice Worker\nhello\n11:25"],
        ["Bob Worker\nhello\n11:26"],
        ["Bob Worker\nhello\n11:26", "Cat Worker\nhello\n11:27"],
    ]
    calls = {"i": 0}
    old_collect = boss_browser._collect_visible_boss_chat_items
    old_scroll = boss_browser.scroll_boss_chat_list

    def fake_collect(page, limit):
        return pages[min(calls["i"], len(pages) - 1)]

    def fake_scroll(page):
        calls["i"] += 1
        return calls["i"] < len(pages)

    try:
        boss_browser._collect_visible_boss_chat_items = fake_collect
        boss_browser.scroll_boss_chat_list = fake_scroll
        assert boss_browser.collect_boss_chat_items(object(), 10) == [
            "Alice Worker\nhello\n11:25",
            "Bob Worker\nhello\n11:26",
            "Cat Worker\nhello\n11:27",
        ]
    finally:
        boss_browser._collect_visible_boss_chat_items = old_collect
        boss_browser.scroll_boss_chat_list = old_scroll


def test_incremental_read_chats_does_not_click_details() -> None:
    import app.boss_browser as boss_browser

    calls = {"clicks": 0}
    old_get = boss_browser.get_connected_page
    old_is_chat_page = boss_browser.is_boss_chat_page
    old_snapshot = boss_browser.page_snapshot
    old_login = boss_browser.is_login_page
    old_sleep = boss_browser.time.sleep
    old_reset = boss_browser.reset_boss_chat_list_scroll
    old_collect = boss_browser._collect_visible_boss_chat_items
    old_click = boss_browser.click_boss_chat_item
    old_signatures = dict(boss_browser._boss_chat_signatures)

    def fake_click(page, name, role):
        calls["clicks"] += 1
        return True

    try:
        boss_browser._boss_chat_signatures.clear()
        boss_browser.get_connected_page = lambda: object()
        boss_browser.is_boss_chat_page = lambda page: True
        boss_browser.page_snapshot = lambda page: []
        boss_browser.is_login_page = lambda page, lines: False
        boss_browser.time.sleep = lambda seconds: None
        boss_browser.reset_boss_chat_list_scroll = lambda page: None
        boss_browser._collect_visible_boss_chat_items = lambda page, limit: ["Alice Worker\nhello\n11:25"]
        boss_browser.click_boss_chat_item = fake_click

        result = boss_browser.read_chats(10, incremental=True)

        assert calls["clicks"] == 0
        assert result["chats"][0]["messages"] == []
    finally:
        boss_browser.get_connected_page = old_get
        boss_browser.is_boss_chat_page = old_is_chat_page
        boss_browser.page_snapshot = old_snapshot
        boss_browser.is_login_page = old_login
        boss_browser.time.sleep = old_sleep
        boss_browser.reset_boss_chat_list_scroll = old_reset
        boss_browser._collect_visible_boss_chat_items = old_collect
        boss_browser.click_boss_chat_item = old_click
        boss_browser._boss_chat_signatures.clear()
        boss_browser._boss_chat_signatures.update(old_signatures)


def test_incremental_read_chats_skips_non_chat_page() -> None:
    import app.boss_browser as boss_browser

    old_get = boss_browser.get_connected_page
    old_is_chat_page = boss_browser.is_boss_chat_page
    old_collect = boss_browser._collect_visible_boss_chat_items
    calls = {"collect": 0}

    def fake_collect(page, limit):
        calls["collect"] += 1
        return ["Alice Worker\nhello\n11:25"]

    try:
        boss_browser.get_connected_page = lambda: object()
        boss_browser.is_boss_chat_page = lambda page: False
        boss_browser._collect_visible_boss_chat_items = fake_collect

        result = boss_browser.read_chats(10, incremental=True)

        assert result["chats"] == []
        assert calls["collect"] == 0
    finally:
        boss_browser.get_connected_page = old_get
        boss_browser.is_boss_chat_page = old_is_chat_page
        boss_browser._collect_visible_boss_chat_items = old_collect


def test_incremental_read_chats_does_not_start_browser_when_closed() -> None:
    import app.boss_browser as boss_browser

    old_connected = boss_browser.get_connected_page
    old_get = boss_browser.get_page
    calls = {"get": 0}

    def fake_get_page():
        calls["get"] += 1
        raise AssertionError("incremental sync must not launch browser")

    try:
        boss_browser.get_connected_page = lambda: None
        boss_browser.get_page = fake_get_page

        result = boss_browser.read_chats(10, incremental=True)

        assert result["chats"] == []
        assert calls["get"] == 0
    finally:
        boss_browser.get_connected_page = old_connected
        boss_browser.get_page = old_get


def test_click_boss_chat_item_in_list_scrolls_until_match() -> None:
    import app.boss_browser as boss_browser

    calls = {"clicks": 0, "scrolls": 0, "resets": 0}
    old_click = boss_browser.click_boss_chat_item
    old_scroll = boss_browser.scroll_boss_chat_list
    old_reset = boss_browser.reset_boss_chat_list_scroll
    old_sleep = boss_browser.time.sleep

    def fake_click(page, name, role):
        calls["clicks"] += 1
        return calls["clicks"] == 3

    def fake_scroll(page):
        calls["scrolls"] += 1
        return True

    try:
        boss_browser.click_boss_chat_item = fake_click
        boss_browser.scroll_boss_chat_list = fake_scroll
        boss_browser.reset_boss_chat_list_scroll = lambda page: calls.__setitem__("resets", calls["resets"] + 1)
        boss_browser.time.sleep = lambda seconds: None

        assert boss_browser.click_boss_chat_item_in_list(object(), "ccccccc", "锯床操作工", attempts=5)
        assert calls == {"clicks": 3, "scrolls": 2, "resets": 1}
    finally:
        boss_browser.click_boss_chat_item = old_click
        boss_browser.scroll_boss_chat_list = old_scroll
        boss_browser.reset_boss_chat_list_scroll = old_reset
        boss_browser.time.sleep = old_sleep


def test_select_city_does_not_fake_success_when_input_missing() -> None:
    import app.boss_browser as boss_browser

    old_search_frame = boss_browser.search_frame
    old_run_js_bool = boss_browser.run_js_bool
    old_js_click_text = boss_browser.js_click_text
    old_sleep = boss_browser.time.sleep

    try:
        boss_browser.search_frame = lambda page: None
        boss_browser.run_js_bool = lambda page, body, *args: False
        boss_browser.js_click_text = lambda page, text, exact: False
        boss_browser.time.sleep = lambda seconds: None

        assert boss_browser.select_city(object(), "城厢区") == "city=城厢区:not-found"
    finally:
        boss_browser.search_frame = old_search_frame
        boss_browser.run_js_bool = old_run_js_bool
        boss_browser.js_click_text = old_js_click_text
        boss_browser.time.sleep = old_sleep


def test_split_boss_city_area() -> None:
    import app.boss_browser as boss_browser

    assert boss_browser.split_boss_city_area("莆田市城厢区") == ("莆田", "城厢区")
    assert boss_browser.split_boss_city_area("莆田") == ("莆田", "")


def test_city_action_result_falls_back_to_city_when_area_missing() -> None:
    import app.boss_browser as boss_browser

    assert boss_browser.city_action_result("莆田市城厢区", "莆田", "城厢区", False) == "city=莆田; area=城厢区:not-selected"


if __name__ == "__main__":
    test_page_is_connected_handles_dead_page()
    test_boss_chat_input_text_handles_js_error()
    test_boss_chat_detail_text_matches_requires_same_person()
    test_parse_boss_candidate_card()
    test_parse_boss_chat_item()
    test_parse_boss_chat_skips_unread_count()
    test_parse_boss_chat_ignores_status_fragment()
    test_parse_boss_chat_requires_role()
    test_parse_boss_chat_marks_agent_last_message()
    test_parse_boss_chat_read_status_is_candidate_message()
    test_boss_chat_signature_changes_on_latest_message()
    test_collect_boss_chat_items_scrolls_visible_pages()
    test_incremental_read_chats_does_not_click_details()
    test_incremental_read_chats_skips_non_chat_page()
    test_incremental_read_chats_does_not_start_browser_when_closed()
    test_click_boss_chat_item_in_list_scrolls_until_match()
    test_select_city_does_not_fake_success_when_input_missing()
    test_split_boss_city_area()
    test_city_action_result_falls_back_to_city_when_area_missing()
    print("ok")
