from app import boss_visual
from pathlib import Path
from app.schemas import (
    BossDesktopDraftFromOCRRequest,
    BossDesktopScanDraftRequest,
    RecruitmentAgentResponse,
    RecruitmentRequirement,
)


def _fake_agent_response() -> RecruitmentAgentResponse:
    return RecruitmentAgentResponse(
        thread_id="test-thread",
        stage="awaiting_human_approval",
        match_score=72,
        match_reason="mocked match",
        risk_flags=[],
        draft="Hello, this is a human-reviewed draft.",
        next_action="review_draft",
        requires_human_approval=True,
    )


def test_latest_message_hint_filters_button_labels() -> None:
    text = """
23 years old
Bachelor
同意
拒绝
Candidate says they can start next week.
<div>ignored image</div>
求简历
Candidate is currently in Xiamen.
"""

    hint = boss_visual.latest_message_hint(text)

    assert "同意" not in hint
    assert "拒绝" not in hint
    assert "求简历" not in hint
    assert "<div" not in hint
    assert "Candidate says they can start next week." in hint
    assert "Candidate is currently in Xiamen." in hint


def test_draft_from_ocr_text_returns_human_review_draft() -> None:
    import app.recruitment_agent as recruitment_agent

    captured = {}
    original_run = recruitment_agent.run_recruitment_agent

    def fake_run(payload):
        captured["payload"] = payload
        return _fake_agent_response()

    try:
        recruitment_agent.run_recruitment_agent = fake_run
        result = boss_visual.draft_from_ocr_text(
            BossDesktopDraftFromOCRRequest(
                requirement=RecruitmentRequirement(title="Supply Chain Buyer", role="Buyer", location="Xiamen"),
                chat_text="Candidate is in Xiamen and can start next week.",
                candidate_name="Test Candidate",
            )
        )
    finally:
        recruitment_agent.run_recruitment_agent = original_run

    assert result["ok"] is True
    assert result["requires_human_approval"] is True
    assert result["draft"]["draft"] == "Hello, this is a human-reviewed draft."
    assert captured["payload"].candidate.name == "Test Candidate"
    assert captured["payload"].candidate.source == "boss_desktop_ocr"


def test_scan_and_draft_uses_mocked_ocr_text() -> None:
    import app.recruitment_agent as recruitment_agent

    original_scan = boss_visual.scan_boss_chats
    original_run = recruitment_agent.run_recruitment_agent
    try:
        boss_visual.scan_boss_chats = lambda count, run_ocr=False: {
            "ok": True,
            "mode": "mock_scan",
            "ocr_results": [{"ok": True, "text": "Candidate has purchasing experience."}],
        }
        recruitment_agent.run_recruitment_agent = lambda payload: _fake_agent_response()

        result = boss_visual.scan_and_draft_boss_chats(
            BossDesktopScanDraftRequest(
                count=1,
                requirement=RecruitmentRequirement(title="Supply Chain Buyer", role="Buyer", location="Xiamen"),
            )
        )
    finally:
        boss_visual.scan_boss_chats = original_scan
        recruitment_agent.run_recruitment_agent = original_run

    assert result["ok"] is True
    assert result["requires_human_approval"] is True
    assert result["scan"]["mode"] == "mock_scan"
    assert len(result["drafts"]) == 1
    assert result["drafts"][0]["draft"]["requires_human_approval"] is True


def test_cleanup_image_paths_deletes_temp_file(tmp_path: Path) -> None:
    image_path = tmp_path / "boss.png"
    image_path.write_bytes(b"png")

    result = boss_visual.cleanup_image_paths([image_path])

    assert result == [{"path": str(image_path), "deleted": True}]
    assert not image_path.exists()


if __name__ == "__main__":
    test_latest_message_hint_filters_button_labels()
    test_draft_from_ocr_text_returns_human_review_draft()
    test_scan_and_draft_uses_mocked_ocr_text()
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        test_cleanup_image_paths_deletes_temp_file(Path(tmp))
    print("ok")
