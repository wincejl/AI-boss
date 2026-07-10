package service

import (
	"reflect"
	"testing"

	"github.com/2930134478/AI-CS/backend/models"
)

func TestIsBossEchoMessage(t *testing.T) {
	if !isBossEchoMessage(&models.Message{
		SenderIsAgent: true,
		MessageType:   "user_message",
		Content:       "你好",
	}, " 你好 ") {
		t.Fatal("agent text echoed from BOSS should be skipped")
	}
	if isBossEchoMessage(&models.Message{SenderIsAgent: false, Content: "你好"}, "你好") {
		t.Fatal("candidate text should not be skipped")
	}
	if isBossEchoMessage(&models.Message{SenderIsAgent: true, MessageType: "system_message", Content: "你好"}, "你好") {
		t.Fatal("system messages should not be treated as BOSS echoes")
	}
}

func TestShouldImportBossListMessage(t *testing.T) {
	if shouldImportBossListMessage("agent", nil, "你好", "候选人 你好") {
		t.Fatal("agent-side BOSS list message should not be imported as candidate message")
	}
	if !shouldImportBossListMessage("candidate", nil, "你好", "候选人 你好") {
		t.Fatal("candidate-side BOSS list message should be imported")
	}
	if shouldImportBossListMessage("", &models.Message{SenderIsAgent: true, MessageType: "user_message", Content: "你好"}, "你好", "候选人 你好") {
		t.Fatal("agent echo should not be imported")
	}
	if shouldImportBossListMessage("candidate", &models.Message{SenderIsAgent: false, MessageType: "user_message", Content: "工作地点呢"}, "工作地点呢", "BOSS候选人：ccccccc\n工作地点呢") {
		t.Fatal("duplicate candidate list message should not be imported")
	}
}

func TestHasBossListMessageFindsOlderCandidateMessage(t *testing.T) {
	messages := []models.Message{
		{SenderIsAgent: false, MessageType: "user_message", Content: "BOSS candidate\nsame"},
		{SenderIsAgent: true, MessageType: "ai_draft", Content: "draft"},
	}
	if !hasBossListMessage(messages, "same", "BOSS candidate\nsame") {
		t.Fatal("existing candidate list message should block repeat import")
	}
}

func TestCleanBossHistoryContent(t *testing.T) {
	if got := cleanBossHistoryContent(" 已读 你好 "); got != "你好" {
		t.Fatalf("expected cleaned read status, got %q", got)
	}
	if got := cleanBossHistoryContent("送达 1"); got != "1" {
		t.Fatalf("expected cleaned delivery status, got %q", got)
	}
}

func TestConsumeBossHistorySeenKeepsDuplicateCounts(t *testing.T) {
	seen := map[string]int{"candidate|same": 1}
	if !consumeBossHistorySeen(seen, "candidate|same") {
		t.Fatal("expected first matching existing message to be consumed")
	}
	if consumeBossHistorySeen(seen, "candidate|same") {
		t.Fatal("second identical BOSS message should be imported, not collapsed")
	}
}

func TestIsBossHistoryNoise(t *testing.T) {
	for _, text := range []string{"未选中联系人", "列表只展示近30天的联系人", "表情", "09:36 1", "BOSS候选人：张三\n你好"} {
		if !isBossHistoryNoise(text) {
			t.Fatalf("expected noise text to be filtered: %q", text)
		}
	}
	if isBossHistoryNoise("你好") {
		t.Fatal("real chat text should not be treated as noise")
	}
}

func TestMissingBossConversationIDs(t *testing.T) {
	active := map[string]struct{}{
		"boss://chat/live": {},
	}
	got := missingBossConversationIDs([]models.Conversation{
		{ID: 1, Referrer: "boss://chat/live"},
		{ID: 2, Referrer: "boss://chat/deleted"},
		{ID: 3, Referrer: "https://example.com"},
	}, active)
	want := []uint{2}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("missing ids = %v, want %v", got, want)
	}
}

func TestIsBossConversationReferrer(t *testing.T) {
	if !isBossConversationReferrer("boss://chat/abc") {
		t.Fatal("expected BOSS chat referrer")
	}
	if isBossConversationReferrer("https://example.com") {
		t.Fatal("web visitor referrer should not be treated as BOSS")
	}
}
