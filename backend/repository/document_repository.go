package repository

import (
	"github.com/2930134478/AI-CS/backend/models"
	"gorm.io/gorm"
)

// DocumentRepository 封装与文档相关的数据库操作
type DocumentRepository struct {
	db *gorm.DB
}

// NewDocumentRepository 创建文档仓库实例
func NewDocumentRepository(db *gorm.DB) *DocumentRepository {
	return &DocumentRepository{db: db}
}

// Create 创建新的文档
func (r *DocumentRepository) Create(doc *models.Document) error {
	return r.db.Create(doc).Error
}

// GetByID 根据ID查询文档
func (r *DocumentRepository) GetByID(id uint) (*models.Document, error) {
	var doc models.Document
	if err := r.db.Where("id = ?", id).First(&doc).Error; err != nil {
		return nil, err
	}
	return &doc, nil
}

// GetByKnowledgeBaseID 根据知识库ID查询文档列表
func (r *DocumentRepository) GetByKnowledgeBaseID(knowledgeBaseID uint, page, pageSize int, keyword string, status string) ([]models.Document, int64, error) {
	var docs []models.Document
	var total int64

	query := r.db.Model(&models.Document{}).Where("knowledge_base_id = ?", knowledgeBaseID)

	// 关键词搜索
	if keyword != "" {
		query = query.Where("title LIKE ? OR content LIKE ?", "%"+keyword+"%", "%"+keyword+"%")
	}

	// 状态过滤
	if status != "" {
		query = query.Where("status = ?", status)
	}

	// 统计总数
	if err := query.Count(&total).Error; err != nil {
		return nil, 0, err
	}

	// 分页查询
	offset := (page - 1) * pageSize
	if err := query.Order("created_at DESC").Offset(offset).Limit(pageSize).Find(&docs).Error; err != nil {
		return nil, 0, err
	}

	return docs, total, nil
}

func (r *DocumentRepository) ListPublishedRAGDocs(limit int) ([]models.Document, error) {
	if limit <= 0 {
		limit = 5
	}
	var docs []models.Document
	err := r.db.
		Joins("JOIN knowledge_bases ON knowledge_bases.id = documents.knowledge_base_id").
		Where("documents.status = ? AND knowledge_bases.rag_enabled = ?", "published", true).
		Order("documents.updated_at DESC").
		Limit(limit).
		Find(&docs).Error
	return docs, err
}

// Update 更新文档
func (r *DocumentRepository) Update(doc *models.Document) error {
	return r.db.Save(doc).Error
}

// Delete 删除文档
func (r *DocumentRepository) Delete(id uint) error {
	return r.db.Delete(&models.Document{}, id).Error
}

// DeleteByKnowledgeBaseID 根据知识库ID删除所有文档
func (r *DocumentRepository) DeleteByKnowledgeBaseID(knowledgeBaseID uint) error {
	return r.db.Where("knowledge_base_id = ?", knowledgeBaseID).Delete(&models.Document{}).Error
}

// CountByKnowledgeBaseID 统计知识库的文档数量
func (r *DocumentRepository) CountByKnowledgeBaseID(knowledgeBaseID uint) (int64, error) {
	var count int64
	if err := r.db.Model(&models.Document{}).Where("knowledge_base_id = ?", knowledgeBaseID).Count(&count).Error; err != nil {
		return 0, err
	}
	return count, nil
}

// GetByIDs 根据ID列表查询文档
func (r *DocumentRepository) GetByIDs(ids []uint) ([]models.Document, error) {
	var docs []models.Document
	if err := r.db.Where("id IN ?", ids).Find(&docs).Error; err != nil {
		return nil, err
	}
	return docs, nil
}

// UpdateEmbeddingStatus 更新文档的向量化状态
func (r *DocumentRepository) UpdateEmbeddingStatus(id uint, status string) error {
	return r.db.Model(&models.Document{}).Where("id = ?", id).Update("embedding_status", status).Error
}

// UpdateStatus 更新文档的状态
func (r *DocumentRepository) UpdateStatus(id uint, status string) error {
	return r.db.Model(&models.Document{}).Where("id = ?", id).Update("status", status).Error
}
