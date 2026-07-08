package controller

import (
	"errors"
	"log"
	"net/http"
	"os"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/2930134478/AI-CS/backend/models"
	"github.com/2930134478/AI-CS/backend/service"
	"github.com/gin-gonic/gin"
)

type BossAssistantController struct {
	service      *service.BossAssistantService
	recruitment  *service.RecruitmentService
	conversation *service.ConversationService
	users        *service.UserService
	ai           *service.AIService
	messages     *service.MessageService
	bossSyncMu   sync.Mutex
}

func NewBossAssistantController(s *service.BossAssistantService, recruitment *service.RecruitmentService, conversation *service.ConversationService, users *service.UserService, ai *service.AIService, messages *service.MessageService) *BossAssistantController {
	controller := &BossAssistantController{service: s, recruitment: recruitment, conversation: conversation, users: users, ai: ai, messages: messages}
	controller.startBossAutoSync()
	return controller
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
		Limit       int  `json:"limit"`
		Incremental bool `json:"incremental"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		req.Limit = 50
	}
	if req.Limit <= 0 || req.Limit > 50 {
		req.Limit = 50
	}
	imported, result, err := b.importBossChats(getUserIDFromHeader(c), req.Limit, req.Incremental)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{
		"conversations": imported.Conversations,
		"imported":      imported.Imported,
		"updated":       imported.Updated,
		"closed":        imported.Closed,
		"skipped":       imported.Skipped,
		"message":       result.Message,
	})
}

func (b *BossAssistantController) importBossChats(ownerID uint, limit int, incremental bool) (*service.ImportBossChatsResult, *service.BossChatsResult, error) {
	b.bossSyncMu.Lock()
	defer b.bossSyncMu.Unlock()
	if b.service == nil || b.conversation == nil {
		return nil, nil, errors.New("boss chat sync service is not configured")
	}
	if limit <= 0 || limit > 50 {
		limit = 50
	}
	result, err := b.service.ReadChats(limit, incremental)
	if err != nil {
		return nil, nil, err
	}
	items := make([]service.ImportBossChatInput, 0, len(result.Chats))
	for _, chat := range result.Chats {
		items = append(items, service.ImportBossChatInput{
			Key:         chat.Key,
			Name:        chat.Name,
			Role:        chat.Role,
			LastMessage: chat.LastMessage,
			LastSender:  chat.LastSender,
			TimeText:    chat.TimeText,
			Profile:     chat.Profile,
			Messages:    chat.Messages,
		})
	}
	imported, err := b.conversation.ImportBossChats(items, ownerID, !incremental)
	if err != nil {
		return nil, nil, err
	}
	if incremental {
		b.draftReplyBossChats(imported, ownerID)
	}
	return imported, result, nil
}

func (b *BossAssistantController) startBossAutoSync() {
	if !bossAutoSyncEnabled() || b.service == nil || b.conversation == nil {
		return
	}
	ownerID := b.bossAutoSyncOwnerID()
	if ownerID == 0 {
		log.Printf("BOSS auto sync skipped: no owner user")
		return
	}
	interval := bossAutoSyncInterval()
	go func() {
		ticker := time.NewTicker(interval)
		defer ticker.Stop()
		for {
			if _, _, err := b.importBossChats(ownerID, 20, true); err != nil {
				log.Printf("BOSS auto sync skipped: %v", err)
			}
			<-ticker.C
		}
	}()
	log.Printf("✅ BOSS 自动增量同步已启动，间隔 %s", interval)
}

func (b *BossAssistantController) bossAutoSyncOwnerID() uint {
	if value := strings.TrimSpace(os.Getenv("BOSS_AUTO_SYNC_USER_ID")); value != "" {
		if id, err := strconv.ParseUint(value, 10, 64); err == nil {
			return uint(id)
		}
	}
	if b.users == nil {
		return 1
	}
	users, err := b.users.ListUsers()
	if err != nil {
		return 1
	}
	for _, user := range users {
		if user.Role == "admin" {
			return user.ID
		}
	}
	if len(users) > 0 {
		return users[0].ID
	}
	return 1
}

func (b *BossAssistantController) DeleteChat(c *gin.Context) {
	if !requirePermission(c, b.users, string(service.PermChat)) {
		return
	}
	var req struct {
		ConversationID uint `json:"conversation_id"`
	}
	if err := c.ShouldBindJSON(&req); err != nil || req.ConversationID == 0 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "conversation_id is required"})
		return
	}
	userID := getUserIDFromHeader(c)
	detail, err := b.conversation.GetConversationDetail(req.ConversationID, userID)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "会话不存在"})
		return
	}
	if !strings.HasPrefix(detail.Referrer, "boss://chat/") {
		c.JSON(http.StatusBadRequest, gin.H{"error": "不是BOSS沟通会话"})
		return
	}
	name, role := service.BossChatTargetFromNotes(detail.Notes)
	if strings.TrimSpace(name) == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "无法从会话备注识别BOSS联系人"})
		return
	}
	deleted, err := b.service.DeleteChat(service.BossChatMessageInput{Name: name, Role: role})
	if err != nil {
		c.JSON(http.StatusBadGateway, gin.H{"error": "BOSS联系人删除失败: " + err.Error()})
		return
	}
	if err := b.conversation.CloseConversation(req.ConversationID, userID); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"ok": true, "message": deleted.Message, "target": deleted.Target})
}

func (b *BossAssistantController) draftReplyBossChats(imported *service.ImportBossChatsResult, ownerID uint) {
	if !bossAIDraftReplyEnabled() || imported == nil || b.ai == nil || b.messages == nil || ownerID == 0 {
		return
	}
	for _, item := range latestImportedBossVisitorMessages(imported.NewVisitorMessages) {
		item := item
		go b.createBossChatAIDraft(item, ownerID)
	}
}

func latestImportedBossVisitorMessages(items []service.ImportedBossVisitorMessage) []service.ImportedBossVisitorMessage {
	latest := map[uint]service.ImportedBossVisitorMessage{}
	order := []uint{}
	for _, item := range items {
		if item.ConversationID == 0 || strings.TrimSpace(item.Content) == "" {
			continue
		}
		if _, ok := latest[item.ConversationID]; !ok {
			order = append(order, item.ConversationID)
		}
		latest[item.ConversationID] = item
	}
	out := make([]service.ImportedBossVisitorMessage, 0, len(order))
	for _, id := range order {
		out = append(out, latest[id])
	}
	return out
}

func (b *BossAssistantController) createBossChatAIDraft(item service.ImportedBossVisitorMessage, ownerID uint) {
	useKB, useLLM, useWeb := true, true, false
	prompt := buildBossAIDraftPrompt(item)
	aiResult, err := b.ai.GenerateAIResponseWithOptions(item.ConversationID, prompt, ownerID, &service.GenerateAIResponseInput{
		UseKnowledgeBase: &useKB,
		UseLLM:           &useLLM,
		UseWebSearch:     &useWeb,
	})
	if err != nil || aiResult == nil || aiResult.GenerationFailed || strings.TrimSpace(aiResult.Content) == "" {
		log.Printf("BOSS AI draft skipped: conversation=%d err=%v", item.ConversationID, err)
		return
	}
	content := strings.TrimSpace(aiResult.Content)
	if _, err := b.messages.CreateAIDraft(item.ConversationID, content, aiResult.SourcesUsed); err != nil {
		log.Printf("BOSS AI draft save failed: conversation=%d err=%v", item.ConversationID, err)
	}
}

func (b *BossAssistantController) sendBossChatAIReply(item service.ImportedBossVisitorMessage, ownerID uint, content string) error {
	if b.service == nil {
		return errors.New("boss assistant service is not configured")
	}
	if _, err := b.service.SendChatMessage(service.BossChatMessageInput{
		Name:    item.Name,
		Role:    item.Role,
		Content: content,
	}); err != nil {
		return err
	}
	_, err := b.messages.CreateMessage(service.CreateMessageInput{
		ConversationID: item.ConversationID,
		Content:        content,
		SenderID:       ownerID,
		SenderIsAgent:  true,
	})
	return err
}

func buildBossAIDraftPrompt(item service.ImportedBossVisitorMessage) string {
	var parts []string
	parts = append(parts,
		"你是招聘客服助手。请根据知识库中的招聘话术，给候选人生成一条可直接发送的中文回复草稿。",
		"要求：自然、简短、像真人招聘沟通；不要解释生成过程；不要使用Markdown；不要承诺未确认事项；优先推进了解岗位意向、工期、经验、地区，合适时引导交换微信。",
	)
	if strings.TrimSpace(item.Name) != "" {
		parts = append(parts, "候选人："+strings.TrimSpace(item.Name))
	}
	if strings.TrimSpace(item.Role) != "" {
		parts = append(parts, "沟通岗位："+strings.TrimSpace(item.Role))
	}
	parts = append(parts, "候选人最新消息："+strings.TrimSpace(item.Content))
	return strings.Join(parts, "\n")
}

func bossAIDraftReplyEnabled() bool {
	switch strings.ToLower(strings.TrimSpace(os.Getenv("BOSS_AI_DRAFT_REPLY"))) {
	case "1", "true", "yes", "on":
		return true
	case "0", "false", "no", "off":
		return false
	default:
		return true
	}
}

func bossAIAutoReplyEnabled() bool {
	switch strings.ToLower(strings.TrimSpace(os.Getenv("BOSS_AI_AUTO_REPLY_ENABLED"))) {
	case "1", "true", "yes", "on":
		return true
	default:
		return false
	}
}

func bossAutoSyncEnabled() bool {
	switch strings.ToLower(strings.TrimSpace(os.Getenv("BOSS_AUTO_SYNC_ENABLED"))) {
	case "1", "true", "yes", "on":
		return true
	case "0", "false", "no", "off":
		return false
	default:
		return bossAIAutoReplyEnabled()
	}
}

func bossAutoSyncInterval() time.Duration {
	value := strings.TrimSpace(os.Getenv("BOSS_AUTO_SYNC_INTERVAL_SECONDS"))
	if value == "" {
		return 5 * time.Second
	}
	seconds, err := strconv.Atoi(value)
	if err != nil || seconds < 3 {
		return 5 * time.Second
	}
	return time.Duration(seconds) * time.Second
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
