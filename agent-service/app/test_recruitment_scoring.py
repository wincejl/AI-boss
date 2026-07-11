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


if __name__ == "__main__":
    test_score_candidate_match_strong_match()
    test_score_candidate_match_location_mismatch()
    print("ok")
