package service

import (
	"os"
	"strings"

	"github.com/2930134478/AI-CS/backend/models"
	"github.com/2930134478/AI-CS/backend/repository"
)

const (
	recruitmentTalkKBName       = "招聘客服话术"
	recruitmentTalkDocumentName = "招聘客服话术知识库种子"
)

func SeedRecruitmentTalkScripts(kbRepo *repository.KnowledgeBaseRepository, docRepo *repository.DocumentRepository, seedPath string) error {
	contentBytes, err := os.ReadFile(seedPath)
	if err != nil {
		return err
	}
	content := strings.TrimSpace(string(contentBytes))
	if content == "" {
		return nil
	}

	kb, err := findKnowledgeBaseByName(kbRepo, recruitmentTalkKBName)
	if err != nil {
		return err
	}
	if kb == nil {
		kb = &models.KnowledgeBase{
			Name:          recruitmentTalkKBName,
			Description:   "招聘 Agent 自动回复使用的话术知识库",
			RAGEnabled:    true,
			DocumentCount: 0,
		}
		if err := kbRepo.Create(kb); err != nil {
			return err
		}
	}

	docs, _, err := docRepo.GetByKnowledgeBaseID(kb.ID, 1, 100, "", "")
	if err != nil {
		return err
	}
	for _, doc := range docs {
		if doc.Title != recruitmentTalkDocumentName {
			continue
		}
		if doc.Content != content || doc.Status != "published" {
			doc.Content = content
			doc.Status = "published"
			doc.EmbeddingStatus = "pending"
			if err := docRepo.Update(&doc); err != nil {
				return err
			}
		}
		_ = kbRepo.UpdateDocumentCount(kb.ID, len(docs))
		return nil
	}

	if err := docRepo.Create(&models.Document{
		KnowledgeBaseID: kb.ID,
		Title:           recruitmentTalkDocumentName,
		Content:         content,
		Summary:         "30条招聘客服沟通话术，供 Kimi 自动回复候选人时检索引用。",
		Type:            "document",
		Status:          "published",
		EmbeddingStatus: "pending",
	}); err != nil {
		return err
	}
	return kbRepo.UpdateDocumentCount(kb.ID, len(docs)+1)
}

func findKnowledgeBaseByName(kbRepo *repository.KnowledgeBaseRepository, name string) (*models.KnowledgeBase, error) {
	kbs, err := kbRepo.List()
	if err != nil {
		return nil, err
	}
	for i := range kbs {
		if kbs[i].Name == name {
			return &kbs[i], nil
		}
	}
	return nil, nil
}
