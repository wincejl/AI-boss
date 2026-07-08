package service

import (
	"strings"
	"testing"
)

func TestWithKnowledgeHint(t *testing.T) {
	got := withKnowledgeHint("next", "BOSS rule\nmore")
	if !strings.Contains(got, "Knowledge hint: BOSS rule") {
		t.Fatalf("knowledge hint missing: %q", got)
	}
	if withKnowledgeHint("next", "  ") != "next" {
		t.Fatal("blank knowledge should not change action")
	}
}

func TestBossSearchCity(t *testing.T) {
	if got := bossSearchCity("福建省厦门市思明区"); got != "思明区" {
		t.Fatalf("unexpected city: %q", got)
	}
	if got := bossSearchCity("福建省莆田市城厢区"); got != "城厢区" {
		t.Fatalf("unexpected city: %q", got)
	}
	if got := bossSearchCity("北京市朝阳区"); got != "朝阳区" {
		t.Fatalf("unexpected city: %q", got)
	}
	if got := bossSearchCity("厦门市"); got != "厦门市" {
		t.Fatalf("unexpected city: %q", got)
	}
}

func TestBossSearchCategory(t *testing.T) {
	if got := bossSearchCategory("不限职位"); got != "不限职位" {
		t.Fatalf("unexpected category: %q", got)
	}
	if got := bossSearchCategory("服务员"); got != "服务员" {
		t.Fatalf("unexpected category: %q", got)
	}
	if got := bossSearchCategory("自定义"); got != "" {
		t.Fatalf("custom category should be skipped: %q", got)
	}
}

func TestBossSearchFilters(t *testing.T) {
	if got := bossSearchEducation("博士"); got != "博士" {
		t.Fatalf("unexpected education: %q", got)
	}
	if got := bossSearchEducation("大专"); got != "" {
		t.Fatalf("unsupported education should be skipped: %q", got)
	}
	if got := bossSearchAge("35-40"); got != "35-40" {
		t.Fatalf("unexpected age: %q", got)
	}
	if got := bossSearchAge("自定义"); got != "" {
		t.Fatalf("unsupported age should be skipped: %q", got)
	}
}
