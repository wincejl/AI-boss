package controller

import (
	"testing"
	"time"

	"github.com/2930134478/AI-CS/backend/service"
)

func TestLatestImportedBossVisitorMessages(t *testing.T) {
	items := []service.ImportedBossVisitorMessage{
		{ConversationID: 1, Content: "old"},
		{ConversationID: 2, Content: "hello"},
		{ConversationID: 1, Content: "latest"},
		{ConversationID: 3, Content: "  "},
	}
	got := latestImportedBossVisitorMessages(items)
	if len(got) != 2 {
		t.Fatalf("expected 2 conversations, got %d", len(got))
	}
	if got[0].ConversationID != 1 || got[0].Content != "latest" {
		t.Fatalf("conversation 1 should keep latest message, got %+v", got[0])
	}
	if got[1].ConversationID != 2 || got[1].Content != "hello" {
		t.Fatalf("conversation 2 mismatch: %+v", got[1])
	}
}

func TestBossAIDraftReplyEnabled(t *testing.T) {
	t.Setenv("BOSS_AI_DRAFT_REPLY", "")
	if !bossAIDraftReplyEnabled() {
		t.Fatal("expected draft reply to be enabled by default")
	}
	t.Setenv("BOSS_AI_DRAFT_REPLY", "false")
	if bossAIDraftReplyEnabled() {
		t.Fatal("expected draft reply to be disabled")
	}
}

func TestBossAIAutoReplyEnabled(t *testing.T) {
	t.Setenv("BOSS_AI_AUTO_REPLY_ENABLED", "")
	if bossAIAutoReplyEnabled() {
		t.Fatal("expected auto reply to be disabled by default")
	}
	t.Setenv("BOSS_AI_AUTO_REPLY_ENABLED", "true")
	if !bossAIAutoReplyEnabled() {
		t.Fatal("expected auto reply to be enabled")
	}
}

func TestBossAutoSyncEnabledFollowsAutoReply(t *testing.T) {
	t.Setenv("BOSS_AUTO_SYNC_ENABLED", "")
	t.Setenv("BOSS_AI_AUTO_REPLY_ENABLED", "")
	if bossAutoSyncEnabled() {
		t.Fatal("expected auto sync to be disabled when auto reply is disabled")
	}
	t.Setenv("BOSS_AI_AUTO_REPLY_ENABLED", "true")
	if !bossAutoSyncEnabled() {
		t.Fatal("expected auto sync to follow auto reply")
	}
	t.Setenv("BOSS_AUTO_SYNC_ENABLED", "false")
	if bossAutoSyncEnabled() {
		t.Fatal("expected explicit auto sync false to win")
	}
}

func TestBossAutoSyncInterval(t *testing.T) {
	t.Setenv("BOSS_AUTO_SYNC_INTERVAL_SECONDS", "")
	if got := bossAutoSyncInterval(); got != 5*time.Second {
		t.Fatalf("unexpected default interval: %s", got)
	}
	t.Setenv("BOSS_AUTO_SYNC_INTERVAL_SECONDS", "8")
	if got := bossAutoSyncInterval(); got != 8*time.Second {
		t.Fatalf("unexpected custom interval: %s", got)
	}
	t.Setenv("BOSS_AUTO_SYNC_INTERVAL_SECONDS", "1")
	if got := bossAutoSyncInterval(); got != 5*time.Second {
		t.Fatalf("too small interval should fall back: %s", got)
	}
}
