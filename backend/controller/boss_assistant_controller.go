package controller

import (
	"net/http"

	"github.com/2930134478/AI-CS/backend/service"
	"github.com/gin-gonic/gin"
)

type BossAssistantController struct {
	service *service.BossAssistantService
	users   *service.UserService
}

func NewBossAssistantController(s *service.BossAssistantService, users *service.UserService) *BossAssistantController {
	return &BossAssistantController{service: s, users: users}
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
