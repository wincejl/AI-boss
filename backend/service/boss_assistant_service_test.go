package service

import "testing"

func TestBossChatTargetFromNotes(t *testing.T) {
	name, role := BossChatTargetFromNotes("BOSS候选人：刘杰\n沟通岗位：锯床工\n其他")
	if name != "刘杰" || role != "锯床工" {
		t.Fatalf("got name=%q role=%q", name, role)
	}

	name, role = BossChatTargetFromNotes("BOSS候选人：李** · 服务员（11:25）")
	if name != "李**" || role != "" {
		t.Fatalf("got name=%q role=%q", name, role)
	}
}
