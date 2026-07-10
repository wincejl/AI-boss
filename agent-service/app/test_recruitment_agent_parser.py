from app.recruitment_agent import (
    parse_candidate_profile,
    parse_hard_requirements,
    summarize_candidate_profile,
    summarize_hard_requirements,
)
from app.schemas import RecruitmentCandidate, RecruitmentRequirement


def test_parse_hard_requirements_from_recruitment_form() -> None:
    requirement = RecruitmentRequirement(
        title="北京市朝阳区 服务员",
        role="服务员",
        job_category="服务员",
        location="北京市朝阳区",
        search_keyword="服务员",
        education_requirement="本科及以上",
        age_requirement="30-35",
        recommended_filters=(
            "院校要求:统招本科; 经验要求:在校/应届; 性别要求:男; "
            "薪资区间:2-3K; 活跃度:刚刚活跃; 跳槽频率:时间≥1年; "
            "求职状态:离职-随时到岗; 职位要求:仅从事过此职位; "
            "专业要求:工学/仪器类/全部"
        ),
    )

    parsed = parse_hard_requirements(requirement)

    assert parsed["keyword"] == "服务员"
    assert parsed["location"] == "北京市朝阳区"
    assert parsed["age"]["min"] == 30
    assert parsed["age"]["max"] == 35
    assert parsed["education"]["min"] == "本科"
    assert parsed["education"]["max"] is None
    assert parsed["experience"]["category"] == "fresh_or_student"
    assert parsed["salary"]["min_k"] == 2
    assert parsed["salary"]["max_k"] == 3
    assert parsed["major"]["category"] == "工学"
    assert parsed["major"]["group"] == "仪器类"
    assert parsed["activity"] == "刚刚活跃"
    assert parsed["job_status"] == "离职-随时到岗"


def test_summarize_hard_requirements_is_human_readable() -> None:
    parsed = parse_hard_requirements(
        RecruitmentRequirement(role="水电工", location="上海", age_requirement="40以下")
    )

    summary = summarize_hard_requirements(parsed)

    assert "岗位关键词=水电工" in summary
    assert "地区=上海" in summary
    assert "年龄=40以下" in summary


def test_parse_candidate_profile_from_manual_candidate() -> None:
    candidate = RecruitmentCandidate(
        name="张三",
        current_role="门店服务员",
        location="北京市西城区",
        tags="统招本科，男，32 岁，工学仪器类，应届，薪资 2.3K, 刚刚活跃，离职随时到岗",
        profile=(
            "本科测控仪器专业，在校期间在连锁餐饮门店做全职服务实习，"
            "期望薪资 2300，可随时到岗，居住朝阳区，求职意向仅服务业相关岗位"
        ),
    )

    parsed = parse_candidate_profile(candidate)

    assert parsed["age"]["value"] == 32
    assert parsed["education"]["level"] == "本科"
    assert parsed["experience"]["category"] == "fresh_or_student"
    assert parsed["current_role"] == "门店服务员"
    assert parsed["expected_city"] == "朝阳区"
    assert parsed["salary"]["min_k"] == 2.3
    assert parsed["activity"] == "刚刚活跃"
    assert parsed["job_status"] == "离职-随时到岗"
    assert "工学仪器" in parsed["major"]["raw"]


def test_summarize_candidate_profile_is_human_readable() -> None:
    parsed = parse_candidate_profile(
        RecruitmentCandidate(current_role="水电工", tags="35 岁，高中，5年经验，今日活跃")
    )

    summary = summarize_candidate_profile(parsed)

    assert "年龄=35 岁" in summary
    assert "学历=高中" in summary
    assert "当前岗位=水电工" in summary


if __name__ == "__main__":
    test_parse_hard_requirements_from_recruitment_form()
    test_summarize_hard_requirements_is_human_readable()
    test_parse_candidate_profile_from_manual_candidate()
    test_summarize_candidate_profile_is_human_readable()
    print("ok")
