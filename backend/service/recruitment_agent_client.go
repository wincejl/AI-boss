package service

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/2930134478/AI-CS/backend/models"
)

var ErrRecruitmentAgentDisabled = errors.New("recruitment agent service is not configured")

type RecruitmentAgentClient struct {
	baseURL    string
	httpClient *http.Client
}

type RecruitmentAgentEvent struct {
	Step    string `json:"step"`
	Status  string `json:"status"`
	Message string `json:"message"`
}

type RecruitmentAgentRunResult struct {
	ThreadID              string                  `json:"thread_id"`
	Stage                 string                  `json:"stage"`
	MatchScore            int                     `json:"match_score"`
	MatchReason           string                  `json:"match_reason"`
	RiskFlags             []string                `json:"risk_flags"`
	Draft                 string                  `json:"draft"`
	NextAction            string                  `json:"next_action"`
	RequiresHumanApproval bool                    `json:"requires_human_approval"`
	Mode                  string                  `json:"mode"`
	Events                []RecruitmentAgentEvent `json:"events"`
}

type RecruitmentAgentHealth struct {
	OK            bool   `json:"ok"`
	Service       string `json:"service"`
	LLMConfigured bool   `json:"llm_configured"`
	Checkpoint    string `json:"checkpoint"`
}

type recruitmentAgentRequest struct {
	ThreadID         string                             `json:"thread_id"`
	KnowledgeContext string                             `json:"knowledge_context"`
	Requirement      recruitmentAgentRequirementPayload `json:"requirement"`
	Candidate        recruitmentAgentCandidatePayload   `json:"candidate"`
}

type recruitmentAgentRequirementPayload struct {
	ID                    uint   `json:"id"`
	Title                 string `json:"title"`
	Role                  string `json:"role"`
	JobCategory           string `json:"job_category"`
	Location              string `json:"location"`
	SearchKeyword         string `json:"search_keyword"`
	EducationRequirement  string `json:"education_requirement"`
	AgeRequirement        string `json:"age_requirement"`
	RecommendedFilters    string `json:"recommended_filters"`
	SortPreference        string `json:"sort_preference"`
	FilterViewed14Days    bool   `json:"filter_viewed_14_days"`
	FilterExchanged30Days bool   `json:"filter_exchanged_30_days"`
	BatchSize             int    `json:"batch_size"`
	Tags                  string `json:"tags"`
	MustHave              string `json:"must_have"`
	NiceHave              string `json:"nice_have"`
	Description           string `json:"description"`
}

type recruitmentAgentCandidatePayload struct {
	ID               uint   `json:"id"`
	Name             string `json:"name"`
	Source           string `json:"source"`
	CurrentRole      string `json:"current_role"`
	Location         string `json:"location"`
	Tags             string `json:"tags"`
	Profile          string `json:"profile"`
	ContactStatus    string `json:"contact_status"`
	ConsentToContact bool   `json:"consent_to_contact"`
	PrivateContact   string `json:"private_contact"`
	GroupStatus      string `json:"group_status"`
	LastMessage      string `json:"last_message"`
	NextAction       string `json:"next_action"`
}

func NewRecruitmentAgentClient() *RecruitmentAgentClient {
	baseURL := strings.TrimRight(strings.TrimSpace(os.Getenv("RECRUITMENT_AGENT_URL")), "/")
	return &RecruitmentAgentClient{
		baseURL: baseURL,
		httpClient: &http.Client{
			Timeout: 25 * time.Second,
		},
	}
}

func (c *RecruitmentAgentClient) Enabled() bool {
	return c != nil && c.baseURL != ""
}

func (c *RecruitmentAgentClient) BaseURL() string {
	if c == nil {
		return ""
	}
	return c.baseURL
}

func (c *RecruitmentAgentClient) Health(ctx context.Context) (*RecruitmentAgentHealth, error) {
	if !c.Enabled() {
		return nil, ErrRecruitmentAgentDisabled
	}
	var out RecruitmentAgentHealth
	if err := c.doJSON(ctx, http.MethodGet, "/health", nil, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

func (c *RecruitmentAgentClient) Run(ctx context.Context, req *models.RecruitmentRequirement, candidate *models.RecruitmentCandidate, knowledgeContext string) (*RecruitmentAgentRunResult, error) {
	if !c.Enabled() {
		return nil, ErrRecruitmentAgentDisabled
	}
	payload := recruitmentAgentRequest{
		ThreadID:         fmt.Sprintf("candidate-%d", candidate.ID),
		KnowledgeContext: knowledgeContext,
		Requirement: recruitmentAgentRequirementPayload{
			ID:                    req.ID,
			Title:                 req.Title,
			Role:                  req.Role,
			JobCategory:           req.JobCategory,
			Location:              req.Location,
			SearchKeyword:         req.SearchKeyword,
			EducationRequirement:  req.EducationRequirement,
			AgeRequirement:        req.AgeRequirement,
			RecommendedFilters:    req.RecommendedFilters,
			SortPreference:        req.SortPreference,
			FilterViewed14Days:    req.FilterViewed14Days,
			FilterExchanged30Days: req.FilterExchanged30Days,
			BatchSize:             req.BatchSize,
			Tags:                  req.Tags,
			MustHave:              req.MustHave,
			NiceHave:              req.NiceHave,
			Description:           req.Description,
		},
		Candidate: recruitmentAgentCandidatePayload{
			ID:               candidate.ID,
			Name:             candidate.Name,
			Source:           candidate.Source,
			CurrentRole:      candidate.CurrentRole,
			Location:         candidate.Location,
			Tags:             candidate.Tags,
			Profile:          candidate.Profile,
			ContactStatus:    candidate.ContactStatus,
			ConsentToContact: candidate.ConsentToContact,
			PrivateContact:   candidate.PrivateContact,
			GroupStatus:      candidate.GroupStatus,
			LastMessage:      candidate.LastMessage,
			NextAction:       candidate.NextAction,
		},
	}
	var out RecruitmentAgentRunResult
	if err := c.doJSON(ctx, http.MethodPost, "/v1/recruitment/run", payload, &out); err != nil {
		return nil, err
	}
	if out.Mode == "" {
		out.Mode = "langgraph"
	}
	return &out, nil
}

func (c *RecruitmentAgentClient) doJSON(ctx context.Context, method string, path string, payload any, out any) error {
	if !c.Enabled() {
		return ErrRecruitmentAgentDisabled
	}

	var body io.Reader
	if payload != nil {
		raw, err := json.Marshal(payload)
		if err != nil {
			return err
		}
		body = bytes.NewReader(raw)
	}

	req, err := http.NewRequestWithContext(ctx, method, c.baseURL+path, body)
	if err != nil {
		return err
	}
	if payload != nil {
		req.Header.Set("Content-Type", "application/json")
	}

	res, err := c.httpClient.Do(req)
	if err != nil {
		return err
	}
	defer res.Body.Close()

	if res.StatusCode < 200 || res.StatusCode >= 300 {
		raw, _ := io.ReadAll(io.LimitReader(res.Body, 2048))
		return fmt.Errorf("recruitment agent service returned %s: %s", res.Status, strings.TrimSpace(string(raw)))
	}
	if out == nil {
		return nil
	}
	return json.NewDecoder(res.Body).Decode(out)
}
