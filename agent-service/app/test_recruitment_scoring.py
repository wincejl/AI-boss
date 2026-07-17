from app.recruitment_scoring import score_candidate_match
from app.schemas import RecruitmentCandidate, RecruitmentRequirement


def test_score_candidate_match_strong_match() -> None:
    requirement = RecruitmentRequirement(
        role="服务员",
        search_keyword="服务员",
        location="北京市朝阳区",
        education_requirement="本科及以上",
        age_requirement="30-35",
        recommended_filters="经验要求:在校/应届; 活跃度:刚刚活跃; 求职状态:离职-随时到岗",
    )
    candidate = RecruitmentCandidate(
        name="张三",
        current_role="门店服务员",
        location="北京市朝阳区",
        tags="统招本科，男，32 岁，刚刚活跃，离职随时到岗",
        profile="本科测控仪器专业，在校期间在连锁餐饮门店做全职服务实习，可随时到岗",
    )

    score, reason, risks, next_action = score_candidate_match(requirement, candidate)

    assert score >= 80
    assert "岗位关键词+30" in reason
    assert "地区+15" in reason
    assert "年龄+15" in reason
    assert not risks or "地区不符" not in risks
    assert next_action


def test_score_candidate_match_location_mismatch() -> None:
    requirement = RecruitmentRequirement(
        role="水电工",
        search_keyword="水电工",
        location="上海市浦东新区",
    )
    candidate = RecruitmentCandidate(
        current_role="水电维修",
        location="北京市海淀区",
        tags="5年经验，今日活跃",
        profile="从事水电维修5年，期望城市北京",
    )

    score, reason, risks, _ = score_candidate_match(requirement, candidate)

    assert "地区不符" in risks
    assert "地区+0" in reason
    assert score < 80


def test_description_sections_drive_scoring_and_semantic_text() -> None:
    from app.recruitment_agent import _build_requirement_text, parse_hard_requirements

    requirement = RecruitmentRequirement(
        role="采购经理",
        search_keyword="采购经理",
        description=(
            "岗位描述：\n负责供应链采购和供应商管理。\n\n"
            "【重点要求】\n- 供应链流程\n\n"
            "【加分项】\n- 采购师证书\n\n"
            "【排除项】\n- 应届生"
        ),
    )
    candidate = RecruitmentCandidate(
        current_role="采购经理",
        profile="熟悉供应链流程，持有采购师证书，应届生",
    )

    parsed = parse_hard_requirements(requirement)
    score, reason, risks, _ = score_candidate_match(requirement, candidate)
    semantic_text = _build_requirement_text(requirement)

    assert "供应链流程" in parsed["must_have"]
    assert "采购师证书" in parsed["bonus"]
    assert "应届生" in parsed["exclusions"]
    assert "应届生" in " ".join(risks)
    assert score <= 40
    assert "供应链流程" in reason
    assert "采购师证书" in reason
    assert "供应链流程" in semantic_text
    assert "采购师证书" in semantic_text
    assert "应届生" not in semantic_text


if __name__ == "__main__":
    test_score_candidate_match_strong_match()
    test_score_candidate_match_location_mismatch()
    test_description_sections_drive_scoring_and_semantic_text()
    print("ok")
