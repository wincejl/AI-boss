package controller

import (
	"errors"
	"log"
	"net/http"
	"os"
	"regexp"
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

func (b *BossAssistantController) ProbeVisual(c *gin.Context) {
	if !requirePermission(c, b.users, string(service.PermRecruitment)) {
		return
	}
	result, err := b.service.ProbeVisual()
	if err != nil {
		c.JSON(http.StatusBadGateway, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, result)
}

func (b *BossAssistantController) ProbeVisualRegion(c *gin.Context) {
	if !requirePermission(c, b.users, string(service.PermRecruitment)) {
		return
	}
	var req service.BossVisualRegionProbeInput
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid request"})
		return
	}
	result, err := b.service.ProbeVisualRegion(req)
	if err != nil {
		c.JSON(http.StatusBadGateway, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, result)
}

func (b *BossAssistantController) ProbeVisualOCRRegion(c *gin.Context) {
	if !requirePermission(c, b.users, string(service.PermRecruitment)) {
		return
	}
	var req service.BossVisualOCRRegionInput
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid request"})
		return
	}
	result, err := b.service.ProbeVisualOCRRegion(req)
	if err != nil {
		c.JSON(http.StatusBadGateway, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, result)
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
	rescored, _ := b.recruitment.RescoreCandidates(req.RequirementID)
	c.JSON(http.StatusOK, gin.H{
		"candidates": created,
		"imported":   len(created),
		"skipped":    skipped,
		"rescored":   rescored,
		"message":    result.Message,
	})
}

func (b *BossAssistantController) ImportDesktopOCRChats(c *gin.Context) {
	if !requirePermission(c, b.users, string(service.PermChat)) {
		return
	}
	if b.service == nil || b.conversation == nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "boss desktop OCR import service is not configured"})
		return
	}
	var req struct {
		Count int  `json:"count"`
		Draft bool `json:"draft"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid request"})
		return
	}
	if req.Count <= 0 {
		req.Count = 1
	}
	if req.Count > 10 {
		req.Count = 10
	}
	result, err := b.service.ScanDesktopOCRChats(req.Count)
	if err != nil {
		c.JSON(http.StatusBadGateway, gin.H{"error": err.Error()})
		return
	}

	items := make([]service.ImportBossChatInput, 0, len(result.OCRResults))
	seen := map[string]struct{}{}
	skipped := 0
	parseWarnings := []string{}
	parsedChats := []desktopOCRParsedChat{}
	for index, ocr := range result.OCRResults {
		if !ocr.OK {
			parseWarnings = append(parseWarnings, "OCR result was not successful")
			skipped++
			continue
		}
		parsed := desktopOCRParseChat(index+1, ocr.Text)
		parsedChats = append(parsedChats, parsed)
		parseWarnings = append(parseWarnings, parsed.Warnings...)
		key := desktopOCRProfileKey(parsed.Profile)
		if key == "" || !parsed.Importable {
			skipped++
			continue
		}
		if _, ok := seen[key]; ok {
			skipped++
			continue
		}
		seen[key] = struct{}{}
		items = append(items, service.ImportBossChatInput{
			Key:         desktopOCRChatKey(parsed.Name, parsed.Profile, index+1),
			Name:        parsed.Name,
			Role:        defaultString(parsed.Role, "BOSS Desktop OCR"),
			LastMessage: parsed.LastMessage,
			LastSender:  parsed.LastSender,
			TimeText:    "Desktop OCR",
			Profile:     parsed.Profile,
			Messages:    parsed.Messages,
		})
	}

	ownerID := getUserIDFromHeader(c)
	imported, err := b.conversation.ImportBossChats(items, ownerID, false)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	if req.Draft {
		b.draftReplyBossChats(imported, ownerID)
	}

	c.JSON(http.StatusOK, gin.H{
		"conversations":   imported.Conversations,
		"imported":        imported.Imported,
		"updated":         imported.Updated,
		"closed":          imported.Closed,
		"skipped":         skipped + imported.Skipped,
		"scan":            result,
		"deleted_images":  result.DeletedImages,
		"image_retention": result.ImageRetention,
		"parsed":          parsedChats,
		"warnings":        parseWarnings,
		"requires_review": true,
		"message":         "BOSS desktop OCR results imported into dashboard conversations; screenshots were deleted and no message was sent",
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
		return 60 * time.Second
	}
	seconds, err := strconv.Atoi(value)
	if err != nil || seconds < 30 {
		return 60 * time.Second
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

type desktopOCRParsedChat struct {
	Importable  bool                             `json:"importable"`
	Name        string                           `json:"name"`
	Role        string                           `json:"role"`
	Profile     string                           `json:"profile"`
	LastMessage string                           `json:"last_message"`
	LastSender  string                           `json:"last_sender"`
	Messages    []service.BossChatHistoryMessage `json:"messages"`
	Confidence  string                           `json:"confidence"`
	Warnings    []string                         `json:"warnings"`
}

var desktopOCRTimeLinePattern = regexp.MustCompile(`^(\d{1,2}:\d{2}|\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[-/.]\d{1,2})(\s+\d{1,2}:\d{2})?$`)

func desktopOCRParseChat(index int, raw string) desktopOCRParsedChat {
	lines := desktopOCRUsefulLines(raw, 0)
	parsed := desktopOCRParsedChat{
		Name:       desktopOCRConversationName(index, strings.Join(lines, "\n")),
		Role:       "BOSS Desktop OCR",
		LastSender: "visitor",
		Confidence: "low",
		Warnings:   []string{},
	}
	if len(lines) == 0 {
		parsed.Warnings = append(parsed.Warnings, "OCR returned no useful chat text after filtering")
		return parsed
	}

	profileLines := []string{}
	for pos, line := range lines {
		if parsed.Name == "" || strings.HasPrefix(strings.ToLower(parsed.Name), "boss desktop ocr #") {
			if pos < 12 && desktopOCRLooksLikeStrictCandidateName(line) && !desktopOCRLooksLikeRoleLine(line) && !desktopOCRLooksLikeMessageLine(line) {
				parsed.Name = line
				continue
			}
		}
		if role := desktopOCRRoleFromLine(line); role != "" {
			if parsed.Role == "BOSS Desktop OCR" || strings.Contains(line, "\u6c9f\u901a\u804c\u4f4d") || strings.Contains(line, "\u6c9f\u901a\u7684\u804c\u4f4d") {
				parsed.Role = role
			}
			profileLines = append(profileLines, line)
			continue
		}
		if desktopOCRLooksLikeProfileLine(line) {
			profileLines = append(profileLines, line)
			continue
		}
		if desktopOCRLooksLikeMessageLine(line) {
			sender := desktopOCRGuessSender(line)
			parsed.Messages = append(parsed.Messages, service.BossChatHistoryMessage{
				Sender:  sender,
				Content: desktopOCRMarkUncertainMessage(line, sender),
			})
			continue
		}
		if parsed.Role == "BOSS Desktop OCR" && desktopOCRLooksLikeRoleLine(line) {
			parsed.Role = desktopOCRCleanRole(line)
			profileLines = append(profileLines, line)
			continue
		}
		if len(profileLines) < 10 {
			profileLines = append(profileLines, line)
		}
	}

	if parsed.Name == "" {
		parsed.Name = "BOSS Desktop OCR #" + strconv.Itoa(index)
	}
	if strings.HasPrefix(strings.ToLower(parsed.Name), "boss desktop ocr #") && parsed.Role != "BOSS Desktop OCR" {
		parsed.Name = desktopOCRFallbackNameFromRole(parsed.Role)
	}
	if len(parsed.Messages) > 0 {
		last := parsed.Messages[len(parsed.Messages)-1]
		parsed.LastMessage = last.Content
		parsed.LastSender = last.Sender
		parsed.Confidence = "medium"
		if len(parsed.Messages) >= 2 && !strings.HasPrefix(strings.ToLower(parsed.Name), "boss desktop ocr #") {
			parsed.Confidence = "high"
		}
	} else {
		parsed.LastMessage = desktopOCRLatestMessage(strings.Join(lines, "\n"))
		if parsed.LastMessage != "" {
			parsed.LastMessage = "[OCR review] " + parsed.LastMessage
			parsed.Messages = []service.BossChatHistoryMessage{{Sender: "candidate", Content: parsed.LastMessage}}
			parsed.Warnings = append(parsed.Warnings, "OCR text did not contain clear chat bubbles; imported as one review message")
		}
	}

	profile := strings.TrimSpace(strings.Join(profileLines, "\n"))
	if profile == "" {
		profile = desktopOCRCleanText(strings.Join(lines, "\n"))
	}
	parsed.Profile = profile
	parsed.Importable = desktopOCRParsedChatImportable(parsed)
	if !parsed.Importable {
		parsed.Warnings = append(parsed.Warnings, "OCR result was too noisy or too sparse to import")
	}
	return parsed
}

func desktopOCRParsedChatImportable(parsed desktopOCRParsedChat) bool {
	if strings.TrimSpace(parsed.Profile) == "" {
		return false
	}
	if len(parsed.Messages) > 0 {
		return true
	}
	if !strings.HasPrefix(strings.ToLower(parsed.Name), "boss desktop ocr #") {
		return true
	}
	return desktopOCRLooksLikeRoleLine(parsed.Role)
}

func desktopOCRConversationName(index int, profile string) string {
	if index <= 0 {
		index = 1
	}
	for _, line := range desktopOCRUsefulLines(profile, 6) {
		if desktopOCRLooksLikeStrictCandidateName(line) {
			return line
		}
	}
	return "BOSS Desktop OCR #" + strconv.Itoa(index)
}

func desktopOCRChatKey(name string, profile string, index int) string {
	name = strings.ToLower(strings.TrimSpace(name))
	if name != "" && !strings.HasPrefix(name, "boss desktop ocr #") {
		return "boss-desktop-ocr:name:" + name
	}
	if key := desktopOCRProfileKey(profile); key != "" {
		return "boss-desktop-ocr:text:" + key
	}
	return "boss-desktop-ocr:index:" + strconv.Itoa(index)
}

func desktopOCRProfileKey(profile string) string {
	value := strings.ToLower(strings.TrimSpace(profile))
	if value == "" {
		return ""
	}
	value = strings.Join(strings.Fields(value), " ")
	if len(value) > 180 {
		value = value[:180]
	}
	return value
}

func desktopOCRLatestMessage(profile string) string {
	useful := desktopOCRUsefulLines(profile, 8)
	out := strings.Join(useful, "\n")
	if len(out) > 1200 {
		out = out[:1200]
	}
	return out
}

func desktopOCRCleanText(profile string) string {
	useful := desktopOCRUsefulLines(profile, 24)
	return strings.TrimSpace(strings.Join(useful, "\n"))
}

func desktopOCRLooksLikeRoleLine(line string) bool {
	line = strings.TrimSpace(line)
	if line == "" || desktopOCRIsNoiseLine(line) || desktopOCRIsTimeOrStatusLine(line) {
		return false
	}
	if desktopOCRContainsAny(line, []string{
		"\u5de5\u7a0b\u5e08", "\u5f00\u53d1", "\u8fd0\u8425", "\u4ea7\u54c1", "\u8bbe\u8ba1", "\u6d4b\u8bd5",
		"\u524d\u7aef", "\u540e\u7aef", "Java", "Python", "Go", "\u5b9e\u4e60", "\u5c97\u4f4d", "\u804c\u4f4d", "\u62db\u8058",
	}) {
		return true
	}
	return false
}

func desktopOCRRoleFromLine(line string) string {
	line = strings.TrimSpace(line)
	if line == "" || desktopOCRIsNoiseLine(line) {
		return ""
	}
	for _, prefix := range []string{
		"\u6c9f\u901a\u804c\u4f4d\uff1a",
		"\u6c9f\u901a\u804c\u4f4d:",
		"\u6c9f\u901a\u7684\u804c\u4f4d-",
		"\u6c9f\u901a\u7684\u804c\u4f4d\uff1a",
		"\u6c9f\u901a\u7684\u804c\u4f4d:",
		"\u804c\u4f4d\uff1a",
		"\u804c\u4f4d:",
	} {
		if strings.Contains(line, prefix) {
			parts := strings.SplitN(line, prefix, 2)
			if len(parts) == 2 {
				return desktopOCRCleanRole(parts[1])
			}
		}
	}
	return ""
}

func desktopOCRCleanRole(value string) string {
	value = strings.TrimSpace(value)
	value = strings.Trim(value, " \t-:：")
	if len([]rune(value)) > 40 {
		runes := []rune(value)
		value = string(runes[:40])
	}
	return value
}

func desktopOCRLooksLikeProfileLine(line string) bool {
	line = strings.TrimSpace(line)
	if line == "" || desktopOCRIsNoiseLine(line) || desktopOCRIsTimeOrStatusLine(line) || desktopOCRIsControlLine(line) {
		return false
	}
	if desktopOCRContainsAny(line, []string{
		"\u671f\u671b\uff1a", "\u671f\u671b:", "\u6c9f\u901a\u804c\u4f4d", "\u6c9f\u901a\u7684\u804c\u4f4d",
		"\u5de5\u4f5c\u7ecf\u5386", "\u6559\u80b2\u7ecf\u5386", "\u81f3\u4eca", "\u9ad8\u4e2d", "\u5927\u4e13", "\u672c\u79d1", "\u7855\u58eb", "\u535a\u58eb",
	}) {
		return true
	}
	if desktopOCRLooksLikeExperienceLine(line) {
		return true
	}
	return false
}

func desktopOCRLooksLikeExperienceLine(line string) bool {
	line = strings.TrimSpace(line)
	if len([]rune(line)) < 6 {
		return false
	}
	for idx, r := range []rune(line) {
		if idx >= 4 {
			break
		}
		if r < '0' || r > '9' {
			return false
		}
	}
	return strings.ContainsAny(line, "-/~") || strings.Contains(line, "\u81f3")
}

func desktopOCRFallbackNameFromRole(role string) string {
	role = desktopOCRCleanRole(role)
	if role == "" || role == "BOSS Desktop OCR" {
		return "BOSS Desktop OCR"
	}
	return role + "\u5019\u9009\u4eba"
}

func desktopOCRLooksLikeMessageLine(line string) bool {
	line = strings.TrimSpace(line)
	if line == "" || desktopOCRIsNoiseLine(line) || desktopOCRIsTimeOrStatusLine(line) || desktopOCRIsControlLine(line) || desktopOCRLooksLikeProfileLine(line) {
		return false
	}
	runes := []rune(line)
	if len(runes) < 3 || len(runes) > 260 {
		return false
	}
	if desktopOCRContainsAny(line, []string{
		"\u4f60", "\u60a8", "\u6211", "\u54b1", "\u53ef\u4ee5", "\u65b9\u4fbf", "\u5417", "\u5462", "\u554a", "\u5594",
		"\u7b80\u5386", "\u9762\u8bd5", "\u5fae\u4fe1", "\u7535\u8bdd", "\u9879\u76ee", "\u7ecf\u9a8c", "\u85aa\u8d44",
		"\u5230\u5c97", "\u804a", "\u6c9f\u901a", "\u4e86\u89e3", "\u6295\u9012", "\u53d1\u6211", "\u6536\u5230",
	}) {
		return true
	}
	return len(runes) >= 8 && !desktopOCRLooksLikeStrictCandidateName(line) && !desktopOCRLooksLikeRoleLine(line)
}

func desktopOCRGuessSender(line string) string {
	line = strings.TrimSpace(line)
	if desktopOCRContainsAny(line, []string{
		"\u662f\u5426\u8fd8\u62db\u4eba", "\u8fd8\u62db\u4eba", "\u6211\u60f3\u4e86\u89e3", "\u6211\u60f3\u95ee",
	}) {
		return "candidate"
	}
	if desktopOCRContainsAny(line, []string{
		"\u6211\u8fd9\u8fb9", "\u6211\u4eec\u8fd9\u8fb9", "\u770b\u4e86\u4f60\u7684\u7b80\u5386", "\u770b\u4e86\u60a8\u7684\u7b80\u5386",
		"\u53d1\u60a8", "\u53d1\u4f60", "\u7ed9\u60a8", "\u7ed9\u4f60", "\u6211\u4eec\u5728\u62db", "\u8fd9\u4e2a\u5c97\u4f4d",
		"\u53ef\u4ee5\u804a\u4e00\u804a", "\u53ef\u4ee5\u5148\u804a", "\u65b9\u4fbf\u804a",
	}) {
		return "agent"
	}
	return "candidate"
}

func desktopOCRMarkUncertainMessage(line string, sender string) string {
	line = strings.TrimSpace(line)
	if sender == "agent" {
		return line
	}
	return line
}

func desktopOCRIsTimeOrStatusLine(line string) bool {
	line = strings.TrimSpace(line)
	if line == "" {
		return true
	}
	if desktopOCRTimeLinePattern.MatchString(line) {
		return true
	}
	for _, marker := range []string{
		"\u4eca\u5929", "\u6628\u5929", "\u524d\u5929", "\u5df2\u8bfb", "\u9001\u8fbe", "\u672a\u8bfb",
	} {
		if line == marker {
			return true
		}
		if strings.HasPrefix(line, marker+" ") && len([]rune(line)) <= 10 {
			return true
		}
	}
	return false
}

func desktopOCRIsControlLine(line string) bool {
	line = strings.TrimSpace(line)
	controls := []string{
		"\u540c\u610f", "\u62d2\u7edd", "\u6c42\u7b80\u5386", "\u6362\u7535\u8bdd", "\u6362\u5fae\u4fe1", "\u6211\u77e5\u9053\u4e86",
		"\u804c\u4f4d", "\u7b80\u5386", "\u5e38\u7528\u8bed", "\u8868\u60c5", "\u53d1\u9001", "\u66f4\u591a", "\u5907\u6ce8",
		"\u4e3e\u62a5", "\u62c9\u9ed1",
	}
	for _, item := range controls {
		if line == item {
			return true
		}
	}
	return false
}

func desktopOCRIsStrictNoiseLine(line string) bool {
	lower := strings.ToLower(strings.TrimSpace(line))
	if lower == "" || strings.HasPrefix(lower, "http") || strings.Contains(lower, "<div") || strings.Contains(lower, "<img") || strings.Contains(lower, "![") {
		return true
	}
	if desktopOCRIsTimeOrStatusLine(line) {
		return true
	}
	return desktopOCRContainsAny(line, []string{
		"BOSS\u76f4\u8058\u5e73\u53f0\u63d0\u4ea4",
		"\u53d1\u5e03\u3001\u5c55\u793a\u7684\u7b80\u5386",
		"\u4e2a\u4eba\u4fe1\u606f",
		"\u9690\u79c1\u653f\u7b56",
		"\u7528\u6237\u534f\u8bae",
		"\u4e3e\u62a5",
		"\u62c9\u9ed1",
		"\u5907\u6ce8",
		"\u672a\u9009\u4e2d\u8054\u7cfb\u4eba",
		"\u5217\u8868\u53ea\u5c55\u793a\u8fd130\u5929",
		"\u5e2e\u6211\u95ee\u610f\u5411",
		"\u6709\u6548\u7f29\u77ed",
		"\u62db\u8058\u65f6\u95f4",
		"\u7684\u4eba\u90fd\u5e73\u5b89\u5e78\u798f",
		"\u6700\u540e\u6d3b\u8dc3",
		"BOSS\u5019\u9009\u4eba\uff1a",
	})
}

func desktopOCRUsefulLines(profile string, limit int) []string {
	lines := strings.Split(profile, "\n")
	useful := []string{}
	ignored := map[string]bool{
		"同意": true, "拒绝": true, "求简历": true, "换电话": true, "换微信": true, "我知道了": true, "已读": true,
		"沟通": true, "职位": true, "简历": true, "常用语": true, "表情": true, "发送": true, "更多": true,
	}
	for _, line := range lines {
		line = strings.TrimSpace(line)
		if line == "" || ignored[line] || desktopOCRIsControlLine(line) || desktopOCRIsStrictNoiseLine(line) || desktopOCRIsNoiseLine(line) {
			continue
		}
		useful = append(useful, line)
	}
	if limit > 0 && len(useful) > limit {
		useful = useful[len(useful)-limit:]
	}
	return useful
}

func desktopOCRIsNoiseLine(line string) bool {
	lower := strings.ToLower(strings.TrimSpace(line))
	if lower == "" || strings.HasPrefix(lower, "http") || strings.Contains(lower, "<div") || strings.Contains(lower, "<img") {
		return true
	}
	noiseSubstrings := []string{
		"BOSS直聘平台提交",
		"发布、展示的简历",
		"任何用户原则上仅可出于自身招聘",
		"不得将牛人在BOSS直聘平台",
		"隐私政策",
		"用户协议",
		"举报",
		"拉黑",
		"备注",
		"未选中联系人",
		"列表只展示近30天",
		"帮我问意向",
		"有效缩短",
		"招聘时间",
	}
	for _, item := range noiseSubstrings {
		if strings.Contains(line, item) {
			return true
		}
	}
	return false
}

func desktopOCRLooksLikeCandidateName(line string) bool {
	line = strings.TrimSpace(line)
	runes := []rune(line)
	if len(runes) < 2 || len(runes) > 12 {
		return false
	}
	if strings.ContainsAny(line, "0123456789:：/\\|,，.。()（）[]【】<>《》") {
		return false
	}
	if desktopOCRIsNoiseLine(line) {
		return false
	}
	for _, bad := range []string{"BOSS", "直聘", "平台", "招聘", "岗位", "沟通", "简历", "时间", "幸福"} {
		if strings.Contains(line, bad) {
			return false
		}
	}
	return true
}

func desktopOCRLooksLikeStrictCandidateName(line string) bool {
	if !desktopOCRLooksLikeCandidateName(line) {
		return false
	}
	if desktopOCRContainsAny(line, []string{
		"BOSS", "\u76f4\u8058", "\u5e73\u53f0", "\u62db\u8058", "\u5c97\u4f4d", "\u6c9f\u901a",
		"\u7b80\u5386", "\u65f6\u95f4", "\u5e78\u798f", "\u5e73\u5b89", "\u5019\u9009\u4eba",
	}) {
		return false
	}
	chinese := 0
	for _, r := range []rune(line) {
		if r >= '\u4e00' && r <= '\u9fff' {
			chinese++
		}
	}
	return chinese > 0
}

func desktopOCRContainsAny(value string, needles []string) bool {
	for _, needle := range needles {
		if needle != "" && strings.Contains(value, needle) {
			return true
		}
	}
	return false
}

func defaultString(value string, fallback string) string {
	if strings.TrimSpace(value) == "" {
		return fallback
	}
	return value
}
