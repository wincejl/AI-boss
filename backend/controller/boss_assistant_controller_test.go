package controller

import (
	"strings"
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
	if got := bossAutoSyncInterval(); got != 60*time.Second {
		t.Fatalf("unexpected default interval: %s", got)
	}
	t.Setenv("BOSS_AUTO_SYNC_INTERVAL_SECONDS", "45")
	if got := bossAutoSyncInterval(); got != 45*time.Second {
		t.Fatalf("unexpected custom interval: %s", got)
	}
	t.Setenv("BOSS_AUTO_SYNC_INTERVAL_SECONDS", "1")
	if got := bossAutoSyncInterval(); got != 60*time.Second {
		t.Fatalf("too small interval should fall back: %s", got)
	}
}

func TestBossMessageSendEnabled(t *testing.T) {
	t.Setenv("BOSS_MESSAGE_SEND_ENABLED", "")
	if bossMessageSendEnabled() {
		t.Fatal("expected BOSS message send to be disabled by default")
	}
	t.Setenv("BOSS_MESSAGE_SEND_ENABLED", "true")
	if !bossMessageSendEnabled() {
		t.Fatal("expected explicit BOSS message send to be enabled")
	}
}

func TestDesktopOCRProfileKeyNormalizesText(t *testing.T) {
	a := desktopOCRProfileKey(" hello\n  world ")
	b := desktopOCRProfileKey("hello world")
	if a == "" || a != b {
		t.Fatalf("expected normalized keys to match, got %q vs %q", a, b)
	}
}

func TestDesktopOCRLatestMessageFiltersButtons(t *testing.T) {
	text := "23岁\n同意\n拒绝\n候选人说下周到岗\n<div>image</div>\n现在在厦门"
	got := desktopOCRLatestMessage(text)
	if strings.Contains(got, "同意") || strings.Contains(got, "拒绝") || strings.Contains(got, "<div") {
		t.Fatalf("latest message should filter controls and image markup: %q", got)
	}
	if !strings.Contains(got, "候选人说下周到岗") || !strings.Contains(got, "现在在厦门") {
		t.Fatalf("latest message should keep useful lines: %q", got)
	}
}

func TestDesktopOCRCleanTextFiltersLegalAndImageNoise(t *testing.T) {
	text := "张三\nBOSS直聘平台提交、发布、展示的简历中的个人信息\n<div><img src=\"x.jpg\" /></div>\n候选人说下周到岗\n有效缩短\n招聘时间"
	got := desktopOCRCleanText(text)
	if strings.Contains(got, "BOSS直聘平台提交") || strings.Contains(got, "<img") || strings.Contains(got, "有效缩短") {
		t.Fatalf("clean text should remove legal, image, and page chrome noise: %q", got)
	}
	if !strings.Contains(got, "张三") || !strings.Contains(got, "候选人说下周到岗") {
		t.Fatalf("clean text should keep candidate content: %q", got)
	}
}

func TestDesktopOCRConversationNameRejectsNoisyText(t *testing.T) {
	if got := desktopOCRConversationName(2, "的人都平安幸福\n招聘时间"); got != "BOSS Desktop OCR #2" {
		t.Fatalf("expected noisy text to use fallback name, got %q", got)
	}
	if got := desktopOCRConversationName(1, "李四\n候选人说下周到岗"); got != "李四" {
		t.Fatalf("expected short candidate-like name, got %q", got)
	}
}
