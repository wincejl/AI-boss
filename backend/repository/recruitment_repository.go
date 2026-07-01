package repository

import (
	"github.com/2930134478/AI-CS/backend/models"
	"gorm.io/gorm"
)

type RecruitmentRepository struct {
	db *gorm.DB
}

func NewRecruitmentRepository(db *gorm.DB) *RecruitmentRepository {
	return &RecruitmentRepository{db: db}
}

func (r *RecruitmentRepository) ListRequirements() ([]models.RecruitmentRequirement, error) {
	var list []models.RecruitmentRequirement
	err := r.db.Order("updated_at DESC").Find(&list).Error
	return list, err
}

func (r *RecruitmentRepository) GetRequirement(id uint) (*models.RecruitmentRequirement, error) {
	var item models.RecruitmentRequirement
	if err := r.db.First(&item, id).Error; err != nil {
		return nil, err
	}
	return &item, nil
}

func (r *RecruitmentRepository) SaveRequirement(item *models.RecruitmentRequirement) error {
	return r.db.Save(item).Error
}

func (r *RecruitmentRepository) DeleteRequirement(id uint) error {
	return r.db.Transaction(func(tx *gorm.DB) error {
		candidates := tx.Model(&models.RecruitmentCandidate{}).Select("id").Where("requirement_id = ?", id)
		if err := tx.Where("candidate_id IN (?)", candidates).Delete(&models.RecruitmentTimelineEvent{}).Error; err != nil {
			return err
		}
		if err := tx.Where("requirement_id = ?", id).Delete(&models.RecruitmentCandidate{}).Error; err != nil {
			return err
		}
		return tx.Delete(&models.RecruitmentRequirement{}, id).Error
	})
}

func (r *RecruitmentRepository) DeleteAllRequirements() error {
	return r.db.Transaction(func(tx *gorm.DB) error {
		candidates := tx.Model(&models.RecruitmentCandidate{}).Select("id")
		if err := tx.Where("candidate_id IN (?)", candidates).Delete(&models.RecruitmentTimelineEvent{}).Error; err != nil {
			return err
		}
		if err := tx.Where("1 = 1").Delete(&models.RecruitmentCandidate{}).Error; err != nil {
			return err
		}
		return tx.Where("1 = 1").Delete(&models.RecruitmentRequirement{}).Error
	})
}

func (r *RecruitmentRepository) ListCandidates(requirementID uint) ([]models.RecruitmentCandidate, error) {
	var list []models.RecruitmentCandidate
	q := r.db.Order("match_score DESC, updated_at DESC")
	if requirementID > 0 {
		q = q.Where("requirement_id = ?", requirementID)
	}
	err := q.Find(&list).Error
	return list, err
}

func (r *RecruitmentRepository) GetCandidate(id uint) (*models.RecruitmentCandidate, error) {
	var item models.RecruitmentCandidate
	if err := r.db.First(&item, id).Error; err != nil {
		return nil, err
	}
	return &item, nil
}

func (r *RecruitmentRepository) SaveCandidate(item *models.RecruitmentCandidate) error {
	return r.db.Save(item).Error
}

func (r *RecruitmentRepository) ListTimelineEvents(candidateID uint) ([]models.RecruitmentTimelineEvent, error) {
	var list []models.RecruitmentTimelineEvent
	err := r.db.Where("candidate_id = ?", candidateID).Order("created_at DESC, id DESC").Find(&list).Error
	return list, err
}

func (r *RecruitmentRepository) SaveTimelineEvent(item *models.RecruitmentTimelineEvent) error {
	return r.db.Create(item).Error
}
