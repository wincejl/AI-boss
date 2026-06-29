package models

import "time"

type RecruitmentRequirement struct {
	ID                    uint      `json:"id" gorm:"primaryKey"`
	Title                 string    `json:"title" gorm:"size:128;not null"`
	Role                  string    `json:"role" gorm:"size:128;not null;index"`
	JobCategory           string    `json:"job_category" gorm:"size:128"`
	Location              string    `json:"location" gorm:"size:128;index"`
	SearchKeyword         string    `json:"search_keyword" gorm:"size:128"`
	EducationRequirement  string    `json:"education_requirement" gorm:"size:64"`
	AgeRequirement        string    `json:"age_requirement" gorm:"size:64"`
	RecommendedFilters    string    `json:"recommended_filters" gorm:"type:text"`
	SortPreference        string    `json:"sort_preference" gorm:"size:64"`
	FilterViewed14Days    bool      `json:"filter_viewed_14_days" gorm:"default:false"`
	FilterExchanged30Days bool      `json:"filter_exchanged_30_days" gorm:"default:false"`
	BatchSize             int       `json:"batch_size" gorm:"default:10"`
	Tags                  string    `json:"tags" gorm:"type:text"`
	MustHave              string    `json:"must_have" gorm:"type:text"`
	NiceHave              string    `json:"nice_have" gorm:"type:text"`
	Description           string    `json:"description" gorm:"type:text"`
	Status                string    `json:"status" gorm:"size:32;index;default:active"`
	OwnerID               uint      `json:"owner_id" gorm:"index"`
	CreatedAt             time.Time `json:"created_at"`
	UpdatedAt             time.Time `json:"updated_at"`
}

type RecruitmentCandidate struct {
	ID               uint      `json:"id" gorm:"primaryKey"`
	RequirementID    uint      `json:"requirement_id" gorm:"not null;index"`
	OwnerID          uint      `json:"owner_id" gorm:"index"`
	Name             string    `json:"name" gorm:"size:128;not null"`
	Source           string    `json:"source" gorm:"size:64;index"`
	CurrentRole      string    `json:"current_role" gorm:"size:128"`
	Location         string    `json:"location" gorm:"size:128;index"`
	Tags             string    `json:"tags" gorm:"type:text"`
	Profile          string    `json:"profile" gorm:"type:text"`
	MatchScore       int       `json:"match_score" gorm:"index"`
	MatchReason      string    `json:"match_reason" gorm:"type:text"`
	ContactStatus    string    `json:"contact_status" gorm:"size:32;index;default:new"`
	ConsentToContact bool      `json:"consent_to_contact" gorm:"default:false"`
	PrivateContact   string    `json:"private_contact" gorm:"size:255"`
	GroupStatus      string    `json:"group_status" gorm:"size:32;index;default:not_invited"`
	LastMessage      string    `json:"last_message" gorm:"type:text"`
	NextAction       string    `json:"next_action" gorm:"type:text"`
	CreatedAt        time.Time `json:"created_at"`
	UpdatedAt        time.Time `json:"updated_at"`
}

type RecruitmentTimelineEvent struct {
	ID          uint      `json:"id" gorm:"primaryKey"`
	CandidateID uint      `json:"candidate_id" gorm:"not null;index"`
	OwnerID     uint      `json:"owner_id" gorm:"index"`
	EventType   string    `json:"event_type" gorm:"size:64;index"`
	Title       string    `json:"title" gorm:"size:128"`
	Content     string    `json:"content" gorm:"type:text"`
	FromStatus  string    `json:"from_status" gorm:"size:64"`
	ToStatus    string    `json:"to_status" gorm:"size:64"`
	CreatedAt   time.Time `json:"created_at"`
}
