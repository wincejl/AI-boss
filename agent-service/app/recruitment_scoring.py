from __future__ import annotations

import re
from typing import Any

from .schemas import RecruitmentCandidate, RecruitmentRequirement


def _parser():
    from . import recruitment_agent as parser

    return parser

ACTIVITY_SCORES = {
    "刚刚活跃": 10,
    "今日活跃": 9,
    "本周活跃": 8,
    "3日内活跃": 7,
    "2周内活跃": 6,
    "近一周活跃": 5,
    "近一个月活跃": 3,
}


def _keyword_parts(keyword: str) -> list[str]:
    keyword = (keyword or "").strip().lower()
    if not keyword:
        return []
    parts: list[str] = []
    seen: set[str] = set()

    def add(part: str) -> None:
        part = part.strip().lower()
        if len(part) < 2 or part in seen:
            return
        seen.add(part)
        parts.append(part)

    add(keyword)
    max_size = min(len(keyword), 6)
    for size in range(max_size, 1, -1):
        for index in range(0, len(keyword) - size + 1):
            add(keyword[index : index + size])
    parts.sort(key=len, reverse=True)
    return parts

JOB_STATUS_SCORES = {
    "离职-随时到岗": 10,
    "在职-考虑机会": 8,
    "在职-月内到岗": 7,
    "在职-暂不考虑": 2,
}


def score_parsed_match(
    parsed_req: dict[str, Any],
    parsed_cand: dict[str, Any],
    requirement: RecruitmentRequirement,
    candidate: RecruitmentCandidate,
) -> tuple[int, str, list[str], str]:
    reasons: list[str] = []
    risks: list[str] = []
    total = 0

    keyword_pts, keyword_reason, keyword_risk = _score_keyword(parsed_req, parsed_cand, requirement, candidate)
    total += keyword_pts
    reasons.append(keyword_reason)
    if keyword_risk:
        risks.append(keyword_risk)

    location_pts, location_reason, location_risk = _score_location(parsed_req, parsed_cand, candidate)
    total += location_pts
    reasons.append(location_reason)
    if location_risk:
        risks.append(location_risk)

    age_pts, age_reason, age_risk = _score_age(parsed_req, parsed_cand)
    total += age_pts
    reasons.append(age_reason)
    if age_risk:
        risks.append(age_risk)

    edu_pts, edu_reason, edu_risk = _score_education(parsed_req, parsed_cand)
    total += edu_pts
    reasons.append(edu_reason)
    if edu_risk:
        risks.append(edu_risk)

    exp_pts, exp_reason, exp_risk = _score_experience(parsed_req, parsed_cand)
    total += exp_pts
    reasons.append(exp_reason)
    if exp_risk:
        risks.append(exp_risk)

    activity_pts, activity_reason, activity_risk = _score_activity(parsed_req, parsed_cand)
    total += activity_pts
    reasons.append(activity_reason)
    if activity_risk:
        risks.append(activity_risk)

    exclusion_risks = _score_exclusions(parsed_req, parsed_cand, candidate)
    risks.extend(exclusion_risks)

    must_have_pts, must_have_reasons, must_have_risks = _score_must_have(parsed_req, parsed_cand, candidate)
    total += must_have_pts
    reasons.extend(must_have_reasons)
    risks.extend(must_have_risks)

    bonus_pts, bonus_reasons = _score_bonus_with_points(parsed_req, parsed_cand, requirement, candidate)
    total += bonus_pts
    reasons.extend(bonus_reasons)

    if exclusion_risks:
        total = min(total, 40)

    if total > 100:
        total = 100
    if not reasons:
        reasons.append("信息不足（0分）：需人工复核")

    next_action = _next_action_for_score(total, risks)
    return total, "；".join(reasons), risks, next_action


def score_candidate_match(
    requirement: RecruitmentRequirement, candidate: RecruitmentCandidate
) -> tuple[int, str, list[str], str]:
    parser = _parser()
    parsed_req = parser.parse_hard_requirements(requirement)
    parsed_cand = parser.parse_candidate_profile(candidate)
    return score_parsed_match(parsed_req, parsed_cand, requirement, candidate)


def _candidate_haystack(parsed_cand: dict[str, Any], candidate: RecruitmentCandidate) -> str:
    parts = [
        candidate.name,
        candidate.current_role,
        candidate.location,
        candidate.tags,
        candidate.profile,
        candidate.last_message,
        parsed_cand.get("resume_text", ""),
        parsed_cand.get("current_role", ""),
        parsed_cand.get("expected_city", ""),
        " ".join(parsed_cand.get("tags", [])),
    ]
    return " ".join(str(part) for part in parts if part).lower()


def _score_keyword(
    parsed_req: dict[str, Any],
    parsed_cand: dict[str, Any],
    requirement: RecruitmentRequirement,
    candidate: RecruitmentCandidate,
) -> tuple[int, str, str | None]:
    haystack = _candidate_haystack(parsed_cand, candidate)
    parser = _parser()
    keyword = parser.first_non_empty(
        parsed_req.get("keyword", ""),
        requirement.search_keyword,
        requirement.role,
        "" if "不限" in requirement.job_category else requirement.job_category,
    )
    if not keyword:
        return 0, "岗位关键词+0（未设置岗位要求）", "岗位关键词未设置"

    if keyword.lower() in haystack:
        return 30, f"岗位关键词+30（匹配「{keyword}」）", None

    best_part = ""
    for part in _keyword_parts(keyword):
        if part.lower() in haystack and len(part) > len(best_part):
            best_part = part
    if best_part:
        return 20, f"岗位关键词+20（部分匹配「{best_part}」）", "岗位关键词弱匹配"

    for token in parser.tokens(keyword):
        if token.lower() in haystack:
            return 20, f"岗位关键词+20（部分匹配「{token}」）", "岗位关键词弱匹配"

    return 0, f"岗位关键词+0（未匹配「{keyword}」）", "岗位关键词不匹配"


def _normalize_location(value: str) -> str:
    value = (value or "").strip()
    value = re.sub(r"(省|市|自治区|特别行政区)$", "", value)
    return value.lower()


def _location_matches(required: str, actual: str) -> bool:
    required = _normalize_location(required)
    actual = _normalize_location(actual)
    if not required or not actual:
        return False
    if required in actual or actual in required:
        return True
    required_parts = [part for part in re.split(r"[\s/、,，-]+", required) if len(part) >= 2]
    actual_parts = [part for part in re.split(r"[\s/、,，-]+", actual) if len(part) >= 2]
    return any(req in actual or actual in req for req in required_parts for actual in actual_parts)


def _score_location(
    parsed_req: dict[str, Any], parsed_cand: dict[str, Any], candidate: RecruitmentCandidate
) -> tuple[int, str, str | None]:
    required = (parsed_req.get("location") or "").strip()
    if not required:
        return 15, "地区+15（岗位未限定地区）", None

    actual = _parser().first_non_empty(
        parsed_cand.get("expected_city", ""),
        candidate.location,
    )
    if not actual:
        return 5, f"地区+5（候选人地区未知，岗位要求{required}）", "地区信息不足"

    if _location_matches(required, actual):
        return 15, f"地区+15（匹配{actual}）", None

    return 0, f"地区+0（不符：要求{required}，实际{actual}）", "地区不符"


def _score_age(parsed_req: dict[str, Any], parsed_cand: dict[str, Any]) -> tuple[int, str, str | None]:
    required = parsed_req.get("age", {})
    if not required.get("required"):
        return 15, "年龄+15（岗位未限定年龄）", None

    actual = parsed_cand.get("age", {}).get("value")
    raw_required = required.get("raw") or "不限"
    if actual is None:
        return 5, f"年龄+5（候选人年龄未知，要求{raw_required}）", "年龄信息不足"

    min_age = required.get("min")
    max_age = required.get("max")
    if min_age is not None and actual < min_age:
        return 0, f"年龄+0（不符：要求{raw_required}，实际{actual}岁）", "年龄不符"
    if max_age is not None and actual > max_age:
        return 0, f"年龄+0（不符：要求{raw_required}，实际{actual}岁）", "年龄不符"
    return 15, f"年龄+15（{actual}岁，符合{raw_required}）", None


def _score_education(parsed_req: dict[str, Any], parsed_cand: dict[str, Any]) -> tuple[int, str, str | None]:
    required = parsed_req.get("education", {})
    if not required.get("required"):
        return 15, "学历+15（岗位未限定学历）", None

    actual_rank = parsed_cand.get("education", {}).get("rank")
    actual_level = parsed_cand.get("education", {}).get("level") or "未知"
    raw_required = required.get("raw") or "不限"
    min_level = required.get("min")
    if actual_rank is None:
        return 5, f"学历+5（候选人学历未知，要求{raw_required}）", "学历信息不足"
    education_ranks = _parser().EDUCATION_RANKS
    if not min_level or min_level not in education_ranks:
        return 10, f"学历+10（要求{raw_required}，实际{actual_level}）", None

    min_rank = education_ranks.index(min_level)
    if actual_rank < min_rank:
        return 0, f"学历+0（不符：要求{raw_required}，实际{actual_level}）", "学历不符"
    return 15, f"学历+15（{actual_level}，符合{raw_required}）", None


def _score_experience(parsed_req: dict[str, Any], parsed_cand: dict[str, Any]) -> tuple[int, str, str | None]:
    required = parsed_req.get("experience", {})
    if not required.get("required"):
        return 15, "经验+15（岗位未限定经验）", None

    actual_years = parsed_cand.get("experience", {}).get("years")
    actual_raw = parsed_cand.get("experience", {}).get("raw") or "未知"
    raw_required = required.get("raw") or "不限"
    if actual_years is None and parsed_cand.get("experience", {}).get("category") != "fresh_or_student":
        return 5, f"经验+5（候选人经验未知，要求{raw_required}）", "经验信息不足"

    if required.get("category") == "fresh_or_student":
        if parsed_cand.get("experience", {}).get("category") == "fresh_or_student":
            return 15, f"经验+15（{actual_raw}，符合{raw_required}）", None
        if actual_years is not None and actual_years <= 1:
            return 10, f"经验+10（{actual_raw}，接近{raw_required}）", None
        return 0, f"经验+0（不符：要求{raw_required}，实际{actual_raw}）", "经验不足"

    min_years = required.get("min_years")
    max_years = required.get("max_years")
    if actual_years is None:
        return 5, f"经验+5（候选人经验未知，要求{raw_required}）", "经验信息不足"
    if min_years is not None and actual_years < min_years:
        return 0, f"经验+0（不符：要求{raw_required}，实际{actual_raw}）", "经验不足"
    if max_years is not None and actual_years > max_years:
        return 0, f"经验+0（不符：要求{raw_required}，实际{actual_raw}）", "经验不足"
    return 15, f"经验+15（{actual_raw}，符合{raw_required}）", None


def _score_activity(parsed_req: dict[str, Any], parsed_cand: dict[str, Any]) -> tuple[int, str, str | None]:
    required_activity = (parsed_req.get("activity") or "").strip()
    required_status = (parsed_req.get("job_status") or "").strip()
    actual_activity = (parsed_cand.get("activity") or "").strip()
    actual_status = (parsed_cand.get("job_status") or "").strip()

    if not actual_activity and not actual_status:
        if required_activity or required_status:
            return 3, "活跃度/求职状态+3（候选人状态未知）", "求职状态不明确"
        return 10, "活跃度/求职状态+10（岗位未限定活跃度）", None

    score = 0
    detail_parts: list[str] = []
    if actual_activity:
        score = max(score, ACTIVITY_SCORES.get(actual_activity, 4))
        detail_parts.append(actual_activity)
    if actual_status:
        score = max(score, JOB_STATUS_SCORES.get(actual_status, 4))
        detail_parts.append(actual_status)
    score = min(score, 10)

    risk = None
    if required_status and actual_status and actual_status != required_status:
        risk = "求职状态不符"
    elif required_activity and actual_activity and actual_activity != required_activity:
        risk = "活跃度偏低"
    elif score <= 3:
        risk = "求职状态不明确"

    detail = "、".join(detail_parts) if detail_parts else "未知"
    return score, f"活跃度/求职状态+{score}（{detail}）", risk


def _score_exclusions(
    parsed_req: dict[str, Any], parsed_cand: dict[str, Any], candidate: RecruitmentCandidate
) -> list[str]:
    haystack = _candidate_haystack(parsed_cand, candidate)
    risks: list[str] = []
    for token in parsed_req.get("exclusions", []):
        if token.lower() in haystack:
            risks.append(f"命中排除项：{token}")
    return risks


def _score_must_have(
    parsed_req: dict[str, Any], parsed_cand: dict[str, Any], candidate: RecruitmentCandidate
) -> tuple[int, list[str], list[str]]:
    reasons: list[str] = []
    risks: list[str] = []
    haystack = _candidate_haystack(parsed_cand, candidate)
    score = 0
    for token in parsed_req.get("must_have", []):
        if token.lower() in haystack:
            if score < 12:
                score += 4
            reasons.append(f"重点要求匹配：{token}")
        elif len(risks) < 3:
            risks.append(f"重点要求待确认：{token}")
    return min(score, 12), reasons, risks


def _score_bonus(
    parsed_req: dict[str, Any],
    parsed_cand: dict[str, Any],
    requirement: RecruitmentRequirement,
    candidate: RecruitmentCandidate,
) -> list[str]:
    reasons: list[str] = []
    haystack = _candidate_haystack(parsed_cand, candidate)
    for token in parsed_req.get("bonus", []):
        if token.lower() in haystack:
            reasons.append(f"加分项命中：{token}")
    major_req = parsed_req.get("major", {})
    major_name = (major_req.get("major") or major_req.get("group") or major_req.get("category") or "").strip()
    if major_name:
        candidate_major = (parsed_cand.get("major", {}).get("name") or parsed_cand.get("major", {}).get("raw") or "").strip()
        if candidate_major and major_name in candidate_major:
            reasons.append(f"专业匹配：{candidate_major}")
        elif major_req.get("required"):
            reasons.append(f"专业未匹配：要求{major_req.get('raw')}")
    return reasons


def _score_bonus_with_points(
    parsed_req: dict[str, Any],
    parsed_cand: dict[str, Any],
    requirement: RecruitmentRequirement,
    candidate: RecruitmentCandidate,
) -> tuple[int, list[str]]:
    reasons = _score_bonus(parsed_req, parsed_cand, requirement, candidate)
    haystack = _candidate_haystack(parsed_cand, candidate)
    score = 0
    for token in parsed_req.get("bonus", []):
        if token.lower() in haystack and score < 9:
            score += 3
    major_req = parsed_req.get("major", {})
    major_name = (major_req.get("major") or major_req.get("group") or major_req.get("category") or "").strip()
    if major_name:
        candidate_major = (parsed_cand.get("major", {}).get("name") or parsed_cand.get("major", {}).get("raw") or "").strip()
        if candidate_major and major_name in candidate_major:
            score += 4
    return min(score, 10), reasons


def _next_action_for_score(score: int, risks: list[str]) -> str:
    critical = {"地区不符", "学历不符", "经验不足", "年龄不符", "岗位关键词不匹配"}
    if any(risk in critical for risk in risks) or score < 50:
        return "匹配度较低或存在硬性不符，建议人工复核后再决定是否沟通"
    if risks:
        return "根据风险提示人工复核后，再决定是否发送首轮话术"
    if score >= 70:
        return "人工确认首轮话术后，在 BOSS 平台内发送"
    return "建议先补充候选人信息或人工复核，再决定是否沟通"
