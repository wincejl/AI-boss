package controller

import (
	"strings"
	"testing"
)

func TestDesktopOCRParseChatExtractsStructuredConversation(t *testing.T) {
	text := strings.Join([]string{
		"\u5f20\u4e09",
		"Java\u540e\u7aef\u5f00\u53d1\u5de5\u7a0b\u5e08",
		"10:31",
		"\u6211\u4eec\u8fd9\u8fb9\u5728\u62dbJava\u540e\u7aef\uff0c\u770b\u4e86\u60a8\u7684\u7b80\u5386\u6bd4\u8f83\u5339\u914d",
		"\u60a8\u597d\uff0c\u6211\u53ef\u4ee5\u5148\u4e86\u89e3\u4e00\u4e0b\u5c97\u4f4d\u60c5\u51b5",
		"\u540c\u610f",
	}, "\n")

	got := desktopOCRParseChat(1, text)
	if !got.Importable {
		t.Fatalf("expected structured OCR chat to be importable: %+v", got)
	}
	if got.Name != "\u5f20\u4e09" {
		t.Fatalf("expected candidate name, got %q", got.Name)
	}
	if got.Role != "Java\u540e\u7aef\u5f00\u53d1\u5de5\u7a0b\u5e08" {
		t.Fatalf("expected role line, got %q", got.Role)
	}
	if len(got.Messages) != 2 {
		t.Fatalf("expected 2 messages, got %+v", got.Messages)
	}
	if got.Messages[0].Sender != "agent" || got.Messages[1].Sender != "candidate" {
		t.Fatalf("unexpected sender guesses: %+v", got.Messages)
	}
	if strings.Contains(got.Profile, "\u540c\u610f") || strings.Contains(got.Profile, "10:31") {
		t.Fatalf("profile should not include controls or timestamps: %q", got.Profile)
	}
}

func TestDesktopOCRParseChatSkipsLegalNoise(t *testing.T) {
	text := strings.Join([]string{
		"\u7684\u4eba\u90fd\u5e73\u5b89\u5e78\u798f",
		"BOSS\u76f4\u8058\u5e73\u53f0\u63d0\u4ea4\u3001\u53d1\u5e03\u3001\u5c55\u793a\u7684\u7b80\u5386\u4e2d\u7684\u4e2a\u4eba\u4fe1\u606f",
		"<div><img src=\"x.jpg\" /></div>",
		"\u6709\u6548\u7f29\u77ed",
		"\u62db\u8058\u65f6\u95f4",
	}, "\n")

	got := desktopOCRParseChat(2, text)
	if got.Importable {
		t.Fatalf("expected pure legal/page noise to be skipped: %+v", got)
	}
	if got.Name != "BOSS Desktop OCR #2" {
		t.Fatalf("expected fallback name for noisy OCR, got %q", got.Name)
	}
	if len(got.Messages) != 0 {
		t.Fatalf("noise should not create messages: %+v", got.Messages)
	}
}

func TestDesktopOCRParseChatKeepsMessagesMentioningToday(t *testing.T) {
	text := strings.Join([]string{
		"\u674e\u56db",
		"\u4eca\u5929 10:31",
		"\u4eca\u5929\u65b9\u4fbf\u5148\u7535\u8bdd\u6c9f\u901a\u4e00\u4e0b\u5417",
	}, "\n")

	got := desktopOCRParseChat(1, text)
	if len(got.Messages) != 1 {
		t.Fatalf("expected one real message mentioning today, got %+v", got.Messages)
	}
	if !strings.Contains(got.Messages[0].Content, "\u4eca\u5929\u65b9\u4fbf") {
		t.Fatalf("message content was filtered incorrectly: %+v", got.Messages)
	}
}
