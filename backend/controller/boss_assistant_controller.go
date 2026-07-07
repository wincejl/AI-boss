package controller

import (
	"net/http"
	"strings"

	"github.com/2930134478/AI-CS/backend/models"
	"github.com/2930134478/AI-CS/backend/service"
	"github.com/gin-gonic/gin"
)

type BossAssistantController struct {
	service      *service.BossAssistantService
	recruitment  *service.RecruitmentService
	conversation *service.ConversationService
	users        *service.UserService
}

func NewBossAssistantController(s *service.BossAssistantService, recruitment *service.RecruitmentService, conversation *service.ConversationService, users *service.UserService) *BossAssistantController {
	return &BossAssistantController{service: s, recruitment: recruitment, conversation: conversation, users: users}
}

func (b *BossAssistantController) GetStatus(c *gin.Context) {
	if !requirePermission(c, b.users, string(service.PermRecruitment)) {
		return
	}
	status, err := b.service.GetStatus()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, status)
}

func (b *BossAssistantController) DetectAndSave(c *gin.Context) {
	if !requirePermission(c, b.users, string(service.PermRecruitment)) {
		return
	}
	status, err := b.service.DetectAndSave()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, status)
}

func (b *BossAssistantController) SaveConfig(c *gin.Context) {
	if !requirePermission(c, b.users, string(service.PermRecruitment)) {
		return
	}
	var req service.SaveBossAssistantConfigInput
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid request"})
		return
	}
	status, err := b.service.SaveConfig(req)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, status)
}

func (b *BossAssistantController) ClickMenu(c *gin.Context) {
	if !requirePermission(c, b.users, string(service.PermRecruitment)) {
		return
	}
	var req service.ClickBossMenuInput
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid request"})
		return
	}
	result, err := b.service.ClickMenu(req)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, result)
}

func (b *BossAssistantController) SearchCandidates(c *gin.Context) {
	if !requirePermission(c, b.users, string(service.PermRecruitment)) {
		return
	}
	var req service.BossSearchInput
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid request"})
		return
	}
	result, err := b.service.SearchCandidates(req)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, result)
}

func (b *BossAssistantController) ImportCandidates(c *gin.Context) {
	if !requirePermission(c, b.users, string(service.PermRecruitment)) {
		return
	}
	var req struct {
		RequirementID uint `json:"requirement_id"`
		Limit         int  `json:"limit"`
	}
	if err := c.ShouldBindJSON(&req); err != nil || req.RequirementID == 0 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid request"})
		return
	}
	result, err := b.service.ReadCandidates(req.Limit)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	existing, err := b.recruitment.ListCandidates(req.RequirementID)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	seen := map[string]bool{}
	for _, item := range existing {
		seen[bossCandidateKey(item.Name, item.CurrentRole, item.Location, item.Profile)] = true
	}
	created := []*models.RecruitmentCandidate{}
	skipped := 0
	for _, draft := range result.Candidates {
		key := bossCandidateKey(draft.Name, draft.CurrentRole, draft.Location, draft.Profile)
		if key == "" || seen[key] {
			skipped++
			continue
		}
		item, err := b.recruitment.CreateCandidate(service.CreateRecruitmentCandidateInput{
			RequirementID: req.RequirementID,
			OwnerID:       getUserIDFromHeader(c),
			Name:          draft.Name,
			Source:        defaultString(draft.Source, "BOSS"),
			CurrentRole:   draft.CurrentRole,
			Location:      draft.Location,
			Tags:          draft.Tags,
			Profile:       draft.Profile,
		})
		if err != nil {
			skipped++
			continue
		}
		seen[key] = true
		created = append(created, item)
	}
	c.JSON(http.StatusOK, gin.H{
		"candidates": created,
		"imported":   len(created),
		"skipped":    skipped,
		"message":    result.Message,
	})
}

func (b *BossAssistantController) ImportChats(c *gin.Context) {
	if !requirePermission(c, b.users, string(service.PermChat)) {
		return
	}
	var req struct {
		Limit int `json:"limit"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		req.Limit = 20
	}
	result, err := b.service.ReadChats(req.Limit)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	items := make([]service.ImportBossChatInput, 0, len(result.Chats))
	for _, chat := range result.Chats {
		items = append(items, service.ImportBossChatInput{
			Key:         chat.Key,
			Name:        chat.Name,
			Role:        chat.Role,
			LastMessage: chat.LastMessage,
			TimeText:    chat.TimeText,
			Profile:     chat.Profile,
			Messages:    chat.Messages,
		})
	}
	imported, err := b.conversation.ImportBossChats(items, getUserIDFromHeader(c))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{
		"conversations": imported.Conversations,
		"imported":      imported.Imported,
		"updated":       imported.Updated,
		"skipped":       imported.Skipped,
		"message":       result.Message,
	})
}

func bossCandidateKey(name string, role string, location string, profile string) string {
	name = strings.ToLower(strings.TrimSpace(name))
	if name == "" {
		return ""
	}
	role = strings.ToLower(strings.TrimSpace(role))
	location = strings.ToLower(strings.TrimSpace(location))
	profile = strings.ToLower(strings.TrimSpace(profile))
	if len(profile) > 80 {
		profile = profile[:80]
	}
	return strings.Join([]string{name, role, location, profile}, "|")
}

func defaultString(value string, fallback string) string {
	if strings.TrimSpace(value) == "" {
		return fallback
	}
	return value
}
