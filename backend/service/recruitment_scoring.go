package service

import (
	"fmt"
	"regexp"
	"sort"
	"strings"

	"github.com/2930134478/AI-CS/backend/models"
)

var educationRanks = []string{"初中及以下", "中专/中技", "高中", "大专", "本科", "硕士", "博士"}

var activityScores = map[string]int{
	"刚刚活跃":   10,
	"今日活跃":   9,
	"本周活跃":   8,
	"3日内活跃":  7,
	"2周内活跃":  6,
	"近一周活跃":  5,
	"近一个月活跃": 3,
}

var jobStatusScores = map[string]int{
	"离职-随时到岗":  10,
	"在职-考虑机会":  8,
	"在职-月内到岗":  7,
	"在职-暂不考虑":  2,
}

type recruitmentScoreResult struct {
	Score      int
	Reason     string
	RiskFlags  string
	NextAction string
}

func scoreRecruitmentCandidate(req *models.RecruitmentRequirement, candidate *models.RecruitmentCandidate) recruitmentScoreResult {
	parsedReq := parseHardRequirements(req)
	parsedCand := parseCandidateProfile(candidate)

	reasons := make([]string, 0, 8)
	risks := make([]string, 0, 4)
	total := 0

	keywordPts, keywordReason, keywordRisk := scoreKeyword(parsedReq, parsedCand, req, candidate)
	total += keywordPts
	reasons = append(reasons, keywordReason)
	if keywordRisk != "" {
		risks = append(risks, keywordRisk)
	}

	locationPts, locationReason, locationRisk := scoreLocation(parsedReq, parsedCand, candidate)
	total += locationPts
	reasons = append(reasons, locationReason)
	if locationRisk != "" {
		risks = append(risks, locationRisk)
	}

	agePts, ageReason, ageRisk := scoreAge(parsedReq, parsedCand)
	total += agePts
	reasons = append(reasons, ageReason)
	if ageRisk != "" {
		risks = append(risks, ageRisk)
	}

	eduPts, eduReason, eduRisk := scoreEducation(parsedReq, parsedCand)
	total += eduPts
	reasons = append(reasons, eduReason)
	if eduRisk != "" {
		risks = append(risks, eduRisk)
	}

	expPts, expReason, expRisk := scoreExperience(parsedReq, parsedCand)
	total += expPts
	reasons = append(reasons, expReason)
	if expRisk != "" {
		risks = append(risks, expRisk)
	}

	activityPts, activityReason, activityRisk := scoreActivity(parsedReq, parsedCand)
	total += activityPts
	reasons = append(reasons, activityReason)
	if activityRisk != "" {
		risks = append(risks, activityRisk)
	}

	exclusionRisks := scoreExclusions(parsedReq, parsedCand, candidate)
	risks = append(risks, exclusionRisks...)
	if len(exclusionRisks) > 0 && total > 40 {
		total = 40
	}

	reasons = append(reasons, scoreBonus(parsedReq, parsedCand, req)...)

	if total > 100 {
		total = 100
	}
	if len(reasons) == 0 {
		reasons = append(reasons, "信息不足（0分）：需人工复核")
	}

	return recruitmentScoreResult{
		Score:      total,
		Reason:     strings.Join(reasons, "；"),
		RiskFlags:  strings.Join(risks, "；"),
		NextAction: nextActionForScore(total, risks),
	}
}

type parsedRequirement struct {
	Keyword    string
	Location   string
	Age        parsedRange
	Education  parsedEducationRange
	Experience parsedExperienceRange
	Activity   string
	JobStatus  string
	Bonus      []string
	Exclusions []string
	Major      parsedMajor
}

type parsedCandidate struct {
	Age          *int
	AgeRaw       string
	Education    string
	EducationRank *int
	ExperienceYears *int
	ExperienceRaw string
	ExperienceCategory string
	CurrentRole  string
	ExpectedCity string
	Activity     string
	JobStatus    string
	MajorRaw     string
	MajorName    string
	Tags         []string
	ResumeText   string
}

type parsedRange struct {
	Required bool
	Raw      string
	Min      *int
	Max      *int
}

type parsedEducationRange struct {
	Required bool
	Raw      string
	Min      string
	Max      string
}

type parsedExperienceRange struct {
	Required bool
	Raw      string
	MinYears *int
	MaxYears *int
	Category string
}

type parsedMajor struct {
	Required bool
	Raw      string
	Category string
	Group    string
	Major    string
}

func parseHardRequirements(req *models.RecruitmentRequirement) parsedRequirement {
	filters := parseFilterPairs(req.RecommendedFilters)
	keyword := firstNonEmpty(
		req.SearchKeyword,
		req.Role,
		conditionalValue(strings.Contains(req.JobCategory, "不限"), "", req.JobCategory),
		req.Title,
	)
	educationRaw := strings.TrimSpace(req.EducationRequirement)
	if educationRaw == "" || educationRaw == "不限" {
		educationRaw = mapSchoolRequirement(filters["院校要求"])
	}
	experienceRaw := firstNonEmpty(filters["经验要求"], filters["工作经验"])
	return parsedRequirement{
		Keyword:    keyword,
		Location:   strings.TrimSpace(req.Location),
		Age:        parseAgeRange(req.AgeRequirement),
		Education:  parseEducationRange(educationRaw),
		Experience: parseExperienceRange(experienceRaw),
		Activity:   firstNonEmpty(filters["活跃度"], filters["活跃状态"]),
		JobStatus:  filters["求职状态"],
		Bonus:      recruitmentTokens(req.NiceHave),
		Exclusions: parseExclusionTokens(req.MustHave),
		Major:      parseMajorRequirement(filters["专业要求"]),
	}
}

func mapSchoolRequirement(raw string) string {
	value := strings.TrimSpace(raw)
	switch {
	case value == "" || value == "不限":
		return "不限"
	case strings.Contains(value, "博士"):
		return "博士"
	case strings.Contains(value, "硕士"):
		return "硕士及以上"
	case strings.Contains(value, "本科"):
		return "本科及以上"
	case strings.Contains(value, "大专"):
		return "大专及以上"
	default:
		return value
	}
}

func parseCandidateProfile(candidate *models.RecruitmentCandidate) parsedCandidate {
	resumeText := strings.Join([]string{
		candidate.CurrentRole,
		candidate.Location,
		candidate.Tags,
		candidate.Profile,
		candidate.LastMessage,
	}, "\n")
	ageValue, ageRaw := parseCandidateAge(resumeText)
	eduLevel, eduRank := parseCandidateEducation(resumeText)
	expYears, expRaw, expCategory := parseCandidateExperience(resumeText)
	majorRaw, majorName := parseCandidateMajor(resumeText)
	return parsedCandidate{
		Age:                ageValue,
		AgeRaw:             ageRaw,
		Education:          eduLevel,
		EducationRank:      eduRank,
		ExperienceYears:    expYears,
		ExperienceRaw:      expRaw,
		ExperienceCategory: expCategory,
		CurrentRole:        candidate.CurrentRole,
		ExpectedCity:       parseExpectedCity(resumeText, candidate.Location),
		Activity:           parseCandidateActivity(resumeText),
		JobStatus:          parseCandidateJobStatus(resumeText),
		MajorRaw:           majorRaw,
		MajorName:          majorName,
		Tags:               recruitmentTokens(candidate.Tags),
		ResumeText:         resumeText,
	}
}

func candidateHaystack(parsed parsedCandidate, candidate *models.RecruitmentCandidate) string {
	parts := []string{
		candidate.Name,
		candidate.CurrentRole,
		candidate.Location,
		candidate.Tags,
		candidate.Profile,
		candidate.LastMessage,
		parsed.ResumeText,
		parsed.CurrentRole,
		parsed.ExpectedCity,
		strings.Join(parsed.Tags, " "),
	}
	return normalizeForMatch(strings.Join(parts, " "))
}

func scoreKeyword(parsedReq parsedRequirement, parsedCand parsedCandidate, req *models.RecruitmentRequirement, candidate *models.RecruitmentCandidate) (int, string, string) {
	haystack := candidateHaystack(parsedCand, candidate)
	keyword := firstNonEmpty(parsedReq.Keyword, req.SearchKeyword, req.Role, conditionalValue(strings.Contains(req.JobCategory, "不限"), "", req.JobCategory))
	if keyword == "" {
		return 0, "岗位关键词+0（未设置岗位要求）", "岗位关键词未设置"
	}
	if strings.Contains(haystack, normalizeForMatch(keyword)) {
		return 30, fmt.Sprintf("岗位关键词+30（匹配「%s」）", keyword), ""
	}
	bestPart := ""
	for _, part := range keywordParts(keyword) {
		part = strings.TrimSpace(part)
		if len([]rune(part)) < 2 {
			continue
		}
		if strings.Contains(haystack, normalizeForMatch(part)) {
			if len([]rune(part)) > len([]rune(bestPart)) {
				bestPart = part
			}
		}
	}
	if bestPart != "" {
		return 20, fmt.Sprintf("岗位关键词+20（部分匹配「%s」）", bestPart), "岗位关键词弱匹配"
	}
	for _, token := range recruitmentTokens(keyword) {
		if strings.Contains(haystack, normalizeForMatch(token)) {
			return 20, fmt.Sprintf("岗位关键词+20（部分匹配「%s」）", token), "岗位关键词弱匹配"
		}
	}
	return 0, fmt.Sprintf("岗位关键词+0（未匹配「%s」）", keyword), "岗位关键词不匹配"
}

func keywordParts(keyword string) []string {
	runes := []rune(strings.TrimSpace(keyword))
	if len(runes) == 0 {
		return nil
	}
	seen := map[string]bool{}
	parts := make([]string, 0, len(runes)*2)
	add := func(part string) {
		part = strings.TrimSpace(part)
		if len([]rune(part)) < 2 || seen[part] {
			return
		}
		seen[part] = true
		parts = append(parts, part)
	}
	add(string(runes))
	for size := minInt(len(runes), 6); size >= 2; size-- {
		for i := 0; i+size <= len(runes); i++ {
			add(string(runes[i : i+size]))
		}
	}
	sort.Slice(parts, func(i, j int) bool {
		return len([]rune(parts[i])) > len([]rune(parts[j]))
	})
	return parts
}

func minInt(a int, b int) int {
	if a < b {
		return a
	}
	return b
}

func scoreLocation(parsedReq parsedRequirement, parsedCand parsedCandidate, candidate *models.RecruitmentCandidate) (int, string, string) {
	if parsedReq.Location == "" {
		return 15, "地区+15（岗位未限定地区）", ""
	}
	actual := firstNonEmpty(parsedCand.ExpectedCity, candidate.Location)
	if actual == "" {
		return 5, fmt.Sprintf("地区+5（候选人地区未知，岗位要求%s）", parsedReq.Location), "地区信息不足"
	}
	if locationMatches(parsedReq.Location, actual) {
		return 15, fmt.Sprintf("地区+15（匹配%s）", actual), ""
	}
	return 0, fmt.Sprintf("地区+0（不符：要求%s，实际%s）", parsedReq.Location, actual), "地区不符"
}

func scoreAge(parsedReq parsedRequirement, parsedCand parsedCandidate) (int, string, string) {
	if !parsedReq.Age.Required {
		return 15, "年龄+15（岗位未限定年龄）", ""
	}
	if parsedCand.Age == nil {
		return 5, fmt.Sprintf("年龄+5（候选人年龄未知，要求%s）", parsedReq.Age.Raw), "年龄信息不足"
	}
	actual := *parsedCand.Age
	if parsedReq.Age.Min != nil && actual < *parsedReq.Age.Min {
		return 0, fmt.Sprintf("年龄+0（不符：要求%s，实际%d岁）", parsedReq.Age.Raw, actual), "年龄不符"
	}
	if parsedReq.Age.Max != nil && actual > *parsedReq.Age.Max {
		return 0, fmt.Sprintf("年龄+0（不符：要求%s，实际%d岁）", parsedReq.Age.Raw, actual), "年龄不符"
	}
	return 15, fmt.Sprintf("年龄+15（%d岁，符合%s）", actual, parsedReq.Age.Raw), ""
}

func scoreEducation(parsedReq parsedRequirement, parsedCand parsedCandidate) (int, string, string) {
	if !parsedReq.Education.Required {
		return 15, "学历+15（岗位未限定学历）", ""
	}
	actualLevel := parsedCand.Education
	if actualLevel == "" {
		actualLevel = "未知"
	}
	if parsedCand.EducationRank == nil {
		return 5, fmt.Sprintf("学历+5（候选人学历未知，要求%s）", parsedReq.Education.Raw), "学历信息不足"
	}
	minLevel := parsedReq.Education.Min
	if minLevel == "" || educationRankIndex(minLevel) < 0 {
		return 10, fmt.Sprintf("学历+10（要求%s，实际%s）", parsedReq.Education.Raw, actualLevel), ""
	}
	if *parsedCand.EducationRank < educationRankIndex(minLevel) {
		return 0, fmt.Sprintf("学历+0（不符：要求%s，实际%s）", parsedReq.Education.Raw, actualLevel), "学历不符"
	}
	return 15, fmt.Sprintf("学历+15（%s，符合%s）", actualLevel, parsedReq.Education.Raw), ""
}

func scoreExperience(parsedReq parsedRequirement, parsedCand parsedCandidate) (int, string, string) {
	if !parsedReq.Experience.Required {
		return 15, "经验+15（岗位未限定经验）", ""
	}
	actualRaw := parsedCand.ExperienceRaw
	if actualRaw == "" {
		actualRaw = "未知"
	}
	if parsedReq.Experience.Category == "fresh_or_student" {
		if parsedCand.ExperienceCategory == "fresh_or_student" {
			return 15, fmt.Sprintf("经验+15（%s，符合%s）", actualRaw, parsedReq.Experience.Raw), ""
		}
		if parsedCand.ExperienceYears != nil && *parsedCand.ExperienceYears <= 1 {
			return 10, fmt.Sprintf("经验+10（%s，接近%s）", actualRaw, parsedReq.Experience.Raw), ""
		}
		return 0, fmt.Sprintf("经验+0（不符：要求%s，实际%s）", parsedReq.Experience.Raw, actualRaw), "经验不足"
	}
	if parsedCand.ExperienceYears == nil {
		return 5, fmt.Sprintf("经验+5（候选人经验未知，要求%s）", parsedReq.Experience.Raw), "经验信息不足"
	}
	years := *parsedCand.ExperienceYears
	if parsedReq.Experience.MinYears != nil && years < *parsedReq.Experience.MinYears {
		return 0, fmt.Sprintf("经验+0（不符：要求%s，实际%s）", parsedReq.Experience.Raw, actualRaw), "经验不足"
	}
	if parsedReq.Experience.MaxYears != nil && years > *parsedReq.Experience.MaxYears {
		return 0, fmt.Sprintf("经验+0（不符：要求%s，实际%s）", parsedReq.Experience.Raw, actualRaw), "经验不足"
	}
	return 15, fmt.Sprintf("经验+15（%s，符合%s）", actualRaw, parsedReq.Experience.Raw), ""
}

func scoreActivity(parsedReq parsedRequirement, parsedCand parsedCandidate) (int, string, string) {
	if parsedCand.Activity == "" && parsedCand.JobStatus == "" {
		if parsedReq.Activity != "" || parsedReq.JobStatus != "" {
			return 3, "活跃度/求职状态+3（候选人状态未知）", "求职状态不明确"
		}
		return 10, "活跃度/求职状态+10（岗位未限定活跃度）", ""
	}
	score := 0
	details := make([]string, 0, 2)
	if parsedCand.Activity != "" {
		if value, ok := activityScores[parsedCand.Activity]; ok {
			score = maxInt(score, value)
		} else {
			score = maxInt(score, 4)
		}
		details = append(details, parsedCand.Activity)
	}
	if parsedCand.JobStatus != "" {
		if value, ok := jobStatusScores[parsedCand.JobStatus]; ok {
			score = maxInt(score, value)
		} else {
			score = maxInt(score, 4)
		}
		details = append(details, parsedCand.JobStatus)
	}
	if score > 10 {
		score = 10
	}
	risk := ""
	if parsedReq.JobStatus != "" && parsedCand.JobStatus != "" && parsedReq.JobStatus != parsedCand.JobStatus {
		risk = "求职状态不符"
	} else if parsedReq.Activity != "" && parsedCand.Activity != "" && parsedReq.Activity != parsedCand.Activity {
		risk = "活跃度偏低"
	} else if score <= 3 {
		risk = "求职状态不明确"
	}
	return score, fmt.Sprintf("活跃度/求职状态+%d（%s）", score, strings.Join(details, "、")), risk
}

func scoreExclusions(parsedReq parsedRequirement, parsedCand parsedCandidate, candidate *models.RecruitmentCandidate) []string {
	haystack := candidateHaystack(parsedCand, candidate)
	risks := make([]string, 0)
	for _, token := range parsedReq.Exclusions {
		if strings.Contains(haystack, normalizeForMatch(token)) {
			risks = append(risks, "命中排除项："+token)
		}
	}
	return risks
}

func scoreBonus(parsedReq parsedRequirement, parsedCand parsedCandidate, req *models.RecruitmentRequirement) []string {
	reasons := make([]string, 0)
	haystack := candidateHaystack(parsedCand, &models.RecruitmentCandidate{Tags: req.NiceHave})
	haystack = normalizeForMatch(strings.Join([]string{haystack, parsedCand.ResumeText, strings.Join(parsedCand.Tags, " ")}, " "))
	for _, token := range parsedReq.Bonus {
		if strings.Contains(haystack, normalizeForMatch(token)) {
			reasons = append(reasons, "加分项命中："+token)
		}
	}
	majorName := firstNonEmpty(parsedReq.Major.Major, parsedReq.Major.Group, parsedReq.Major.Category)
	if majorName != "" {
		candidateMajor := firstNonEmpty(parsedCand.MajorName, parsedCand.MajorRaw)
		if candidateMajor != "" && strings.Contains(candidateMajor, majorName) {
			reasons = append(reasons, "专业匹配："+candidateMajor)
		} else if parsedReq.Major.Required {
			reasons = append(reasons, "专业未匹配：要求"+parsedReq.Major.Raw)
		}
	}
	return reasons
}

func nextActionForScore(score int, risks []string) string {
	critical := map[string]bool{
		"地区不符": true, "学历不符": true, "经验不足": true, "年龄不符": true, "岗位关键词不匹配": true,
	}
	for _, risk := range risks {
		if critical[risk] || score < 50 {
			return "匹配度较低或存在硬性不符，建议人工复核后再决定是否沟通"
		}
	}
	if len(risks) > 0 {
		return "根据风险提示人工复核后，再决定是否发送首轮话术"
	}
	if score >= 70 {
		return "人工确认首轮话术后，在 BOSS 平台内发送"
	}
	return "建议先补充候选人信息或人工复核，再决定是否沟通"
}

func parseFilterPairs(raw string) map[string]string {
	pairs := map[string]string{}
	for _, item := range strings.FieldsFunc(raw, func(r rune) bool { return r == ';' || r == '；' }) {
		item = strings.TrimSpace(item)
		if item == "" {
			continue
		}
		parts := strings.FieldsFunc(item, func(r rune) bool { return r == ':' || r == '：' || r == '=' })
		if len(parts) != 2 {
			continue
		}
		key := strings.TrimSpace(parts[0])
		value := strings.TrimSpace(parts[1])
		if key != "" && value != "" && value != "不限" {
			pairs[key] = value
		}
	}
	return pairs
}

var ageRangePattern = regexp.MustCompile(`(\d{1,2})\s*[-~到至]\s*(\d{1,2})`)
var ageMinPattern = regexp.MustCompile(`(\d{1,2})\s*以上`)
var ageMaxPattern = regexp.MustCompile(`(\d{1,2})\s*以下`)

func parseAgeRange(raw string) parsedRange {
	value := strings.TrimSpace(raw)
	if value == "" || value == "不限" {
		return parsedRange{Required: false, Raw: value}
	}
	if hit := ageRangePattern.FindStringSubmatch(value); len(hit) == 3 {
		low, high := atoi(hit[1]), atoi(hit[2])
		if low > high {
			low, high = high, low
		}
		return parsedRange{Required: true, Raw: value, Min: &low, Max: &high}
	}
	if hit := ageMinPattern.FindStringSubmatch(value); len(hit) == 2 {
		min := atoi(hit[1])
		return parsedRange{Required: true, Raw: value, Min: &min}
	}
	if hit := ageMaxPattern.FindStringSubmatch(value); len(hit) == 2 {
		max := atoi(hit[1])
		return parsedRange{Required: true, Raw: value, Max: &max}
	}
	return parsedRange{Required: true, Raw: value}
}

func parseEducationRange(raw string) parsedEducationRange {
	value := strings.TrimSpace(raw)
	if value == "" || value == "不限" {
		return parsedEducationRange{Required: false, Raw: value}
	}
	if strings.Contains(value, "-") {
		parts := strings.SplitN(value, "-", 2)
		minPart := strings.TrimSpace(parts[0])
		maxPart := strings.TrimSpace(parts[1])
		if educationRankIndex(minPart) >= 0 && educationRankIndex(maxPart) >= 0 {
			return parsedEducationRange{Required: true, Raw: value, Min: minPart, Max: maxPart}
		}
	}
	for _, level := range educationRanks {
		if strings.HasPrefix(value, level) || strings.Contains(value, level) {
			maxLevel := ""
			if !strings.Contains(value, "以上") {
				maxLevel = level
			}
			return parsedEducationRange{Required: true, Raw: value, Min: level, Max: maxLevel}
		}
	}
	return parsedEducationRange{Required: true, Raw: value}
}

var experienceRangePattern = regexp.MustCompile(`(\d+)\s*[-~到至]\s*(\d+)\s*年`)
var experienceMinPattern = regexp.MustCompile(`(\d+)\s*年以上`)

func parseExperienceRange(raw string) parsedExperienceRange {
	value := strings.TrimSpace(raw)
	if value == "" || value == "不限" {
		return parsedExperienceRange{Required: false, Raw: value}
	}
	if strings.Contains(value, "应届") || strings.Contains(value, "在校") || strings.Contains(value, "毕业") {
		return parsedExperienceRange{Required: true, Raw: value, MinYears: intPtr(0), MaxYears: intPtr(0), Category: "fresh_or_student"}
	}
	if hit := experienceRangePattern.FindStringSubmatch(value); len(hit) == 3 {
		low, high := atoi(hit[1]), atoi(hit[2])
		if low > high {
			low, high = high, low
		}
		return parsedExperienceRange{Required: true, Raw: value, MinYears: &low, MaxYears: &high, Category: "years"}
	}
	if hit := experienceMinPattern.FindStringSubmatch(value); len(hit) == 2 {
		min := atoi(hit[1])
		return parsedExperienceRange{Required: true, Raw: value, MinYears: &min, Category: "years"}
	}
	return parsedExperienceRange{Required: true, Raw: value}
}

func parseMajorRequirement(raw string) parsedMajor {
	value := strings.TrimSpace(raw)
	if value == "" || value == "不限" {
		return parsedMajor{Required: false, Raw: value}
	}
	parts := strings.Split(value, "/")
	major := parsedMajor{Required: true, Raw: value}
	if len(parts) >= 1 {
		major.Category = strings.TrimSpace(parts[0])
	}
	if len(parts) >= 2 && strings.TrimSpace(parts[1]) != "全部" {
		major.Group = strings.TrimSpace(parts[1])
	}
	if len(parts) >= 3 && strings.TrimSpace(parts[2]) != "全部" {
		major.Major = strings.TrimSpace(parts[2])
	}
	return major
}

func parseExclusionTokens(raw string) []string {
	exclusions := make([]string, 0)
	prefixes := []string{"排除", "不要", "不能", "不接受", "禁止"}
	for _, token := range recruitmentTokens(raw) {
		cleaned := token
		for _, prefix := range prefixes {
			cleaned = strings.TrimPrefix(cleaned, prefix)
		}
		cleaned = strings.TrimLeft(cleaned, ":： ")
		if cleaned != "" {
			exclusions = append(exclusions, cleaned)
		}
	}
	return exclusions
}

var candidateAgePattern = regexp.MustCompile(`(\d{1,2})\s*岁`)

func parseCandidateAge(text string) (*int, string) {
	if hit := candidateAgePattern.FindStringSubmatch(text); len(hit) == 2 {
		value := atoi(hit[1])
		return &value, hit[0]
	}
	return nil, ""
}

func parseCandidateEducation(text string) (string, *int) {
	for i := len(educationRanks) - 1; i >= 0; i-- {
		level := educationRanks[i]
		if strings.Contains(text, level) {
			rank := i
			return level, &rank
		}
	}
	return "", nil
}

var candidateExperiencePattern = regexp.MustCompile(`(\d+)\s*年(?:以上)?(?:工作|相关|岗位|服务|餐饮|实习|采购|管理)?经验`)
var candidateExperienceAltPattern = regexp.MustCompile(`经验\s*(\d+)\s*年`)
var candidateExperienceYearsPattern = regexp.MustCompile(`(\d+)\s*年以上`)
var candidateExperienceLinePattern = regexp.MustCompile(`(?m)^\s*(\d+)\s*年(?:以上)?\s*$`)

func parseCandidateExperience(text string) (*int, string, string) {
	if strings.Contains(text, "应届") || strings.Contains(text, "在校") || strings.Contains(text, "毕业生") {
		return intPtr(0), "应届/在校", "fresh_or_student"
	}
	if hit := candidateExperiencePattern.FindStringSubmatch(text); len(hit) == 2 {
		years := atoi(hit[1])
		return &years, hit[0], "years"
	}
	if hit := candidateExperienceAltPattern.FindStringSubmatch(text); len(hit) == 2 {
		years := atoi(hit[1])
		return &years, hit[0], "years"
	}
	if hit := candidateExperienceYearsPattern.FindStringSubmatch(text); len(hit) == 2 {
		years := atoi(hit[1])
		return &years, hit[0], "years"
	}
	if hit := candidateExperienceLinePattern.FindStringSubmatch(text); len(hit) == 2 {
		years := atoi(hit[1])
		return &years, hit[0], "years"
	}
	return nil, "", ""
}

var expectedCityPattern = regexp.MustCompile(`期望(?:城市|地点|工作地|地区)?[:：]?\s*([\p{Han}]{2,12})`)
var residencePattern = regexp.MustCompile(`居住(?:地|在)?[:：]?\s*([\p{Han}]{2,12})`)

func parseExpectedCity(text string, fallback string) string {
	if hit := expectedCityPattern.FindStringSubmatch(text); len(hit) == 2 {
		return strings.Trim(hit[1], "，。；;、 ")
	}
	if hit := residencePattern.FindStringSubmatch(text); len(hit) == 2 {
		return strings.Trim(hit[1], "，。；;、 ")
	}
	return fallback
}

func parseCandidateActivity(text string) string {
	for _, value := range []string{"刚刚活跃", "今日活跃", "本周活跃", "3日内活跃", "2周内活跃", "近一周活跃", "近一个月活跃"} {
		if strings.Contains(text, value) {
			return value
		}
	}
	return ""
}

func parseCandidateJobStatus(text string) string {
	for _, value := range []string{"离职-随时到岗", "在职-暂不考虑", "在职-考虑机会", "在职-月内到岗"} {
		if strings.Contains(text, value) {
			return value
		}
	}
	if strings.Contains(text, "随时到岗") {
		return "离职-随时到岗"
	}
	if strings.Contains(text, "考虑机会") {
		return "在职-考虑机会"
	}
	return ""
}

var candidateMajorPattern = regexp.MustCompile(`([\p{Han}]{1,12})(?:专业|类)`)

func parseCandidateMajor(text string) (string, string) {
	if hit := candidateMajorPattern.FindStringSubmatch(text); len(hit) == 2 {
		return hit[0], hit[1]
	}
	return "", ""
}

func recruitmentTokens(raw string) []string {
	parts := strings.FieldsFunc(raw, func(r rune) bool {
		return r == ',' || r == '，' || r == ';' || r == '；' || r == '/' || r == '、' || r == '\n' || r == '\t' || r == ' '
	})
	out := make([]string, 0, len(parts))
	seen := map[string]bool{}
	for _, part := range parts {
		token := cleanText(part)
		if token == "" {
			continue
		}
		key := normalizeForMatch(token)
		if seen[key] {
			continue
		}
		seen[key] = true
		out = append(out, token)
	}
	sort.Strings(out)
	return out
}

func locationMatches(required string, actual string) bool {
	required = normalizeLocation(required)
	actual = normalizeLocation(actual)
	if required == "" || actual == "" {
		return false
	}
	if strings.Contains(actual, required) || strings.Contains(required, actual) {
		return true
	}
	requiredParts := splitLocationParts(required)
	actualParts := splitLocationParts(actual)
	for _, reqPart := range requiredParts {
		for _, actualPart := range actualParts {
			if strings.Contains(actualPart, reqPart) || strings.Contains(reqPart, actualPart) {
				return true
			}
		}
	}
	return false
}

func normalizeLocation(value string) string {
	value = strings.TrimSpace(value)
	replacer := strings.NewReplacer("省", "", "市", "", "自治区", "", "特别行政区", "")
	return strings.ToLower(replacer.Replace(value))
}

func splitLocationParts(value string) []string {
	parts := strings.FieldsFunc(value, func(r rune) bool {
		return r == ' ' || r == '/' || r == '、' || r == ',' || r == '，' || r == '-'
	})
	out := make([]string, 0, len(parts))
	for _, part := range parts {
		part = strings.TrimSpace(part)
		if len([]rune(part)) >= 2 {
			out = append(out, part)
		}
	}
	return out
}

func educationRankIndex(level string) int {
	for i, item := range educationRanks {
		if item == level {
			return i
		}
	}
	return -1
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			return strings.TrimSpace(value)
		}
	}
	return ""
}

func conditionalValue(condition bool, whenTrue string, whenFalse string) string {
	if condition {
		return whenTrue
	}
	return whenFalse
}

func intPtr(value int) *int {
	return &value
}

func atoi(raw string) int {
	value := 0
	for _, ch := range raw {
		if ch < '0' || ch > '9' {
			continue
		}
		value = value*10 + int(ch-'0')
	}
	return value
}

func maxInt(a int, b int) int {
	if a > b {
		return a
	}
	return b
}
