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

	got := desktopOCRParseChat(1, text, nil)
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

	got := desktopOCRParseChat(2, text, nil)
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

	got := desktopOCRParseChat(1, text, nil)
	if len(got.Messages) != 1 {
		t.Fatalf("expected one real message mentioning today, got %+v", got.Messages)
	}
	if !strings.Contains(got.Messages[0].Content, "\u4eca\u5929\u65b9\u4fbf") {
		t.Fatalf("message content was filtered incorrectly: %+v", got.Messages)
	}
}

func TestDesktopOCRParseChatSeparatesProfileFromMessages(t *testing.T) {
	text := strings.Join([]string{
		"\u6700\u540e\u6d3b\u8dc3 14:58",
		"2018.08-\u81f3\u4eca \u4e16\u7eaa\u597d\u672a\u6765\u6559\u80b2\u79d1\u6280\u00b7\u9500\u552e\u603b\u76d1",
		"2010-2013 \u9ad8\u4e2d\u00b7\u9ad8\u4e2d",
		"\u6c9f\u901a\u804c\u4f4d\uff1a\u4f9b\u5e94\u94fe\u91c7\u8d2d\u7ecf\u7406",
		"\u671f\u671b\uff1a\u53a6\u95e8\u00b7\u8de8\u5883\u7535\u5546\u8fd0\u8425\u9762\u8bae",
		"10:06",
		"7\u670814\u65e5 \u6c9f\u901a\u7684\u804c\u4f4d-\u4f9b\u5e94\u94fe\u91c7\u8d2d\u7ecf\u7406",
		"\u4f60\u597d\uff0c\u662f\u5426\u8fd8\u62db\u4eba\uff1f",
		"\u4f60\u597d\u554a\uff0c\u53ef\u4ee5\u804a\u4e00\u804a~",
	}, "\n")

	got := desktopOCRParseChat(1, text, nil)
	if got.Name != "\u4f9b\u5e94\u94fe\u91c7\u8d2d\u7ecf\u7406\u5019\u9009\u4eba" {
		t.Fatalf("expected role-based fallback name, got %q", got.Name)
	}
	if got.Role != "\u4f9b\u5e94\u94fe\u91c7\u8d2d\u7ecf\u7406" {
		t.Fatalf("expected communication role, got %q", got.Role)
	}
	if len(got.Messages) != 2 {
		t.Fatalf("expected only the two chat lines as messages, got %+v", got.Messages)
	}
	if got.Messages[0].Sender != "candidate" || got.Messages[1].Sender != "agent" {
		t.Fatalf("unexpected sender split: %+v", got.Messages)
	}
	for _, msg := range got.Messages {
		if strings.Contains(msg.Content, "2018.08") || strings.Contains(msg.Content, "\u671f\u671b") || strings.Contains(msg.Content, "\u6c9f\u901a\u7684\u804c\u4f4d") {
			t.Fatalf("profile line leaked into messages: %+v", got.Messages)
		}
	}
	if !strings.Contains(got.Profile, "\u671f\u671b") || !strings.Contains(got.Profile, "2018.08") {
		t.Fatalf("profile should keep resume and expectation lines: %q", got.Profile)
	}
}

func TestDesktopOCRParseChatUsesPaddleBlocksForBasics(t *testing.T) {
	boxes := []map[string]any{
		{"type": "paddle_result", "keys": []any{"layoutParsingResults"}},
		{"type": "paddle_block", "bbox": []any{20, 20, 260, 58}, "text": "\u738b\u6d4b\u8bd5 29\u5c81 \u672c\u79d1 6\u5e74\u7ecf\u9a8c"},
		{"type": "paddle_block", "bbox": []any{20, 90, 420, 124}, "text": "\u671f\u671b\uff1a\u53a6\u95e8\u00b7\u4f9b\u5e94\u94fe\u91c7\u8d2d\u7ecf\u7406\u00b718-25K"},
		{"type": "paddle_block", "bbox": []any{20, 170, 520, 205}, "text": "2020.06-\u81f3\u4eca \u793a\u4f8b\u79d1\u6280\u6709\u9650\u516c\u53f8\u00b7\u91c7\u8d2d\u4e3b\u7ba1"},
		{"type": "paddle_block", "bbox": []any{20, 230, 520, 265}, "text": "2014-2018 \u793a\u4f8b\u5927\u5b66\u00b7\u7269\u6d41\u7ba1\u7406\u00b7\u672c\u79d1"},
		{"type": "paddle_block", "bbox": []any{360, 60, 700, 96}, "text": "\u6c9f\u901a\u804c\u4f4d\uff1a\u4f9b\u5e94\u94fe\u91c7\u8d2d\u7ecf\u7406"},
		{"type": "paddle_block", "bbox": []any{400, 180, 700, 220}, "text": "\u4f60\u597d\uff0c\u662f\u5426\u8fd8\u62db\u4eba\uff1f"},
	}

	got := desktopOCRParseChat(1, "", boxes)
	if got.Name != "\u738b\u6d4b\u8bd5" {
		t.Fatalf("expected name from block basics, got %q", got.Name)
	}
	if got.Age != "29\u5c81" || got.Education != "\u672c\u79d1" || got.Experience != "6\u5e74\u7ecf\u9a8c" {
		t.Fatalf("expected basics from block text, got age=%q education=%q experience=%q", got.Age, got.Education, got.Experience)
	}
	if got.School != "\u793a\u4f8b\u5927\u5b66" {
		t.Fatalf("expected school from education history, got %q", got.School)
	}
	if got.CurrentCompany != "\u793a\u4f8b\u79d1\u6280\u6709\u9650\u516c\u53f8" || got.CurrentTitle != "\u91c7\u8d2d\u4e3b\u7ba1" {
		t.Fatalf("expected current company/title, got company=%q title=%q", got.CurrentCompany, got.CurrentTitle)
	}
	if len(got.WorkHistory) != 1 {
		t.Fatalf("expected one work history line, got %+v", got.WorkHistory)
	}
	if !strings.Contains(got.Profile, "\u5e74\u9f84\uff1a29\u5c81") || !strings.Contains(got.Profile, "\u5b66\u5386\uff1a\u672c\u79d1") {
		t.Fatalf("profile should include parsed basics: %q", got.Profile)
	}
}
