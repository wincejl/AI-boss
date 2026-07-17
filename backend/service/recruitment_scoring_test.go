package service

import (
	"strings"
	"testing"

	"github.com/2930134478/AI-CS/backend/models"
)

func TestScoreRecruitmentCandidateStrongMatch(t *testing.T) {
	req := &models.RecruitmentRequirement{
		Role:                 "服务员",
		SearchKeyword:        "服务员",
		Location:             "北京市朝阳区",
		EducationRequirement: "本科及以上",
		AgeRequirement:       "30-35",
		RecommendedFilters:   "经验要求:在校/应届; 活跃度:刚刚活跃; 求职状态:离职-随时到岗",
	}
	candidate := &models.RecruitmentCandidate{
		Name:        "张三",
		CurrentRole: "门店服务员",
		Location:    "北京市朝阳区",
		Tags:        "统招本科，男，32 岁，刚刚活跃，离职随时到岗",
		Profile:     "本科测控仪器专业，在校期间在连锁餐饮门店做全职服务实习，可随时到岗",
	}
	result := scoreRecruitmentCandidate(req, candidate)
	if result.Score < 80 {
		t.Fatalf("expected strong match score >= 80, got %d (%s)", result.Score, result.Reason)
	}
	if !strings.Contains(result.Reason, "岗位关键词+30") {
		t.Fatalf("missing keyword reason: %s", result.Reason)
	}
	if !strings.Contains(result.Reason, "地区+15") {
		t.Fatalf("missing location reason: %s", result.Reason)
	}
}

func TestScoreRecruitmentCandidateMustHaveMissingOnlyNeedsConfirm(t *testing.T) {
	req := &models.RecruitmentRequirement{
		Role:          "采购经理",
		SearchKeyword: "采购经理",
		MustHave:      "SAP经验",
	}
	candidate := &models.RecruitmentCandidate{
		CurrentRole: "采购经理",
		Profile:     "5年采购经验，熟悉供应商管理和成本控制",
	}

	result := scoreRecruitmentCandidate(req, candidate)
	if result.Score <= 40 {
		t.Fatalf("must-have missing should not cap score as exclusion, got %d (%s)", result.Score, result.Reason)
	}
	if !strings.Contains(result.RiskFlags, "重点要求待确认：SAP经验") {
		t.Fatalf("expected must-have confirmation risk, got %q", result.RiskFlags)
	}
	if strings.Contains(result.RiskFlags, "命中排除项") {
		t.Fatalf("must-have should not become exclusion risk, got %q", result.RiskFlags)
	}
}

func TestScoreRecruitmentCandidateMustHaveAndNiceHaveAddScore(t *testing.T) {
	req := &models.RecruitmentRequirement{
		MustHave: "供应链流程",
		NiceHave: "采购师证书",
	}
	candidate := &models.RecruitmentCandidate{
		Profile: "熟悉供应链流程，持有采购师证书",
	}

	result := scoreRecruitmentCandidate(req, candidate)
	if result.Score < 77 {
		t.Fatalf("expected must-have and nice-have to add score, got %d (%s)", result.Score, result.Reason)
	}
	if !strings.Contains(result.Reason, "重点要求匹配：供应链流程") {
		t.Fatalf("expected must-have match reason, got %q", result.Reason)
	}
	if !strings.Contains(result.Reason, "加分项命中：采购师证书") {
		t.Fatalf("expected nice-have match reason, got %q", result.Reason)
	}
}

func TestScoreRecruitmentCandidateExplicitExclusionStillCaps(t *testing.T) {
	req := &models.RecruitmentRequirement{
		Role:          "采购经理",
		SearchKeyword: "采购经理",
		MustHave:      "排除：应届生",
	}
	candidate := &models.RecruitmentCandidate{
		CurrentRole: "采购经理",
		Profile:     "应届生，有采购实习经验",
	}

	result := scoreRecruitmentCandidate(req, candidate)
	if result.Score > 40 {
		t.Fatalf("explicit exclusion should cap score, got %d (%s)", result.Score, result.Reason)
	}
	if !strings.Contains(result.RiskFlags, "命中排除项：应届生") {
		t.Fatalf("expected explicit exclusion risk, got %q", result.RiskFlags)
	}
}

func TestScoreRecruitmentCandidateReadsDescriptionSections(t *testing.T) {
	req := &models.RecruitmentRequirement{
		Role:          "采购经理",
		SearchKeyword: "采购经理",
		Description:   "岗位描述：\n负责供应链采购、供应商管理和成本控制。\n\n【重点要求】\n- 供应链流程\n\n【加分项】\n- 采购师证书\n\n【排除项】\n- 应届生",
	}
	candidate := &models.RecruitmentCandidate{
		CurrentRole: "采购经理",
		Profile:     "熟悉供应链流程，持有采购师证书，应届生",
	}

	result := scoreRecruitmentCandidate(req, candidate)
	if !strings.Contains(result.Reason, "重点要求匹配：供应链流程") {
		t.Fatalf("expected must-have from description, got %q", result.Reason)
	}
	if !strings.Contains(result.Reason, "加分项命中：采购师证书") {
		t.Fatalf("expected bonus from description, got %q", result.Reason)
	}
	if !strings.Contains(result.RiskFlags, "命中排除项：应届生") {
		t.Fatalf("expected exclusion from description, got %q", result.RiskFlags)
	}
	if result.Score > 40 {
		t.Fatalf("description exclusion should cap score, got %d", result.Score)
	}
}

func TestScoreRecruitmentCandidateLocationMismatch(t *testing.T) {
	req := &models.RecruitmentRequirement{
		Role:           "水电工",
		SearchKeyword:  "水电工",
		Location:       "上海市浦东新区",
		AgeRequirement: "不限",
	}
	candidate := &models.RecruitmentCandidate{
		CurrentRole: "水电维修",
		Location:    "北京市海淀区",
		Tags:        "5年经验，今日活跃",
		Profile:     "从事水电维修5年，期望城市北京",
	}
	result := scoreRecruitmentCandidate(req, candidate)
	if !strings.Contains(result.RiskFlags, "地区不符") {
		t.Fatalf("expected location risk, got %q", result.RiskFlags)
	}
	if !strings.Contains(result.Reason, "地区+0") {
		t.Fatalf("expected location mismatch reason, got %s", result.Reason)
	}
}

func TestScoreRecruitmentCandidateBossProfile(t *testing.T) {
	req := &models.RecruitmentRequirement{
		Role:                 "流水线采购经理",
		SearchKeyword:        "流水线采购经理",
		EducationRequirement: "不限",
		AgeRequirement:       "不限",
		RecommendedFilters:   "院校要求:统招本科; 薪资区间:4-5K",
	}
	candidate := &models.RecruitmentCandidate{
		Name:        "葛**",
		CurrentRole: "博鼎集团子公司博鼎动力",
		Location:    "潍坊",
		Profile:     "葛**\n2周内活跃\n39岁\n10年以上\n本科\n离职-随时到岗\n10-15K\n品类运营\n机械零部件\n采购经理/主管\n职位\n博鼎集团子公司博鼎动力",
	}
	result := scoreRecruitmentCandidate(req, candidate)
	if result.Score < 60 {
		t.Fatalf("expected BOSS profile score >= 60, got %d (%s) risks=%q", result.Score, result.Reason, result.RiskFlags)
	}
	if !strings.Contains(result.Reason, "岗位关键词+20") && !strings.Contains(result.Reason, "岗位关键词+30") {
		t.Fatalf("expected keyword partial/full match, got %s", result.Reason)
	}
}

func TestScoreRecruitmentCandidateEducationMismatch(t *testing.T) {
	req := &models.RecruitmentRequirement{
		Role:                 "工程师",
		SearchKeyword:        "工程师",
		EducationRequirement: "硕士及以上",
	}
	candidate := &models.RecruitmentCandidate{
		CurrentRole: "维修工程师",
		Tags:        "大专，3年经验",
		Profile:     "大专机电专业，3年设备维修经验",
	}
	result := scoreRecruitmentCandidate(req, candidate)
	if !strings.Contains(result.RiskFlags, "学历不符") {
		t.Fatalf("expected education risk, got %q", result.RiskFlags)
	}
	if !strings.Contains(result.Reason, "学历+0") {
		t.Fatalf("expected education mismatch reason, got %s", result.Reason)
	}
}
