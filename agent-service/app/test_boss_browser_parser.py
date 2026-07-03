from app.boss_browser import _page_is_connected, boss_chat_input_text, parse_boss_candidate, parse_boss_chat


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


if __name__ == "__main__":
    test_page_is_connected_handles_dead_page()
    test_boss_chat_input_text_handles_js_error()
    test_parse_boss_candidate_card()
    test_parse_boss_chat_item()
    print("ok")
