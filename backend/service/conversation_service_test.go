package service

import (
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

func TestCleanBossHistoryContent(t *testing.T) {
	if got := cleanBossHistoryContent(" 已读 你好 "); got != "你好" {
		t.Fatalf("expected cleaned read status, got %q", got)
	}
	if got := cleanBossHistoryContent("送达 1"); got != "1" {
		t.Fatalf("expected cleaned delivery status, got %q", got)
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
