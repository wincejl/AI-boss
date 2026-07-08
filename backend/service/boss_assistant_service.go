package service

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"runtime"
	"strings"
	"time"

	"github.com/2930134478/AI-CS/backend/models"
	"github.com/2930134478/AI-CS/backend/repository"
)

type BossAssistantService struct {
	settings *repository.AppSettingRepository
}

type BossAssistantStatus struct {
	Detected      bool   `json:"detected"`
	SavedExePath  string `json:"saved_exe_path"`
	ExePath       string `json:"exe_path"`
	ProcessID     int    `json:"process_id"`
	ProcessName   string `json:"process_name"`
	WindowTitle   string `json:"window_title"`
	Visible       bool   `json:"visible"`
	Minimized     bool   `json:"minimized"`
	WindowLeft    int    `json:"window_left"`
	WindowTop     int    `json:"window_top"`
	WindowWidth   int    `json:"window_width"`
	WindowHeight  int    `json:"window_height"`
	LastCheckedAt string `json:"last_checked_at"`
	Message       string `json:"message"`
}

type SaveBossAssistantConfigInput struct {
	ExePath string `json:"exe_path"`
}

type ClickBossMenuInput struct {
	Menu string `json:"menu"`
}

type BossSearchInput struct {
	Role                  string `json:"role"`
	JobCategory           string `json:"job_category"`
	Location              string `json:"location"`
	SearchKeyword         string `json:"search_keyword"`
	EducationRequirement  string `json:"education_requirement"`
	AgeRequirement        string `json:"age_requirement"`
	RecommendedFilters    string `json:"recommended_filters"`
	SortPreference        string `json:"sort_preference"`
	FilterViewed14Days    bool   `json:"filter_viewed_14_days"`
	FilterExchanged30Days bool   `json:"filter_exchanged_30_days"`
	BatchSize             int    `json:"batch_size"`
}

type ClickBossMenuResult struct {
	Menu    string `json:"menu"`
	Output  string `json:"output"`
	Message string `json:"message"`
}

type BossSearchResult struct {
	Output  string `json:"output"`
	Message string `json:"message"`
}

type BossCandidateDraft struct {
	Name        string `json:"name"`
	Source      string `json:"source"`
	CurrentRole string `json:"current_role"`
	Location    string `json:"location"`
	Tags        string `json:"tags"`
	Profile     string `json:"profile"`
}

type BossCandidatesResult struct {
	Candidates []BossCandidateDraft `json:"candidates"`
	Message    string               `json:"message"`
}

type BossChatDraft struct {
	Key         string                   `json:"key"`
	Name        string                   `json:"name"`
	Role        string                   `json:"role"`
	LastMessage string                   `json:"last_message"`
	LastSender  string                   `json:"last_sender"`
	TimeText    string                   `json:"time_text"`
	Profile     string                   `json:"profile"`
	Messages    []BossChatHistoryMessage `json:"messages"`
}

type BossChatHistoryMessage struct {
	Sender   string `json:"sender"`
	Content  string `json:"content"`
	TimeText string `json:"time_text"`
}

type BossChatsResult struct {
	Chats   []BossChatDraft `json:"chats"`
	Message string          `json:"message"`
}

type BossChatMessageInput struct {
	Name    string
	Role    string
	Content string
}

type BossChatMessageResult struct {
	Message string `json:"message"`
	Target  string `json:"target"`
}

type BossChatDeleteResult struct {
	Message string `json:"message"`
	Target  string `json:"target"`
}

type bossSearchPayload struct {
	City                  string `json:"city"`
	Category              string `json:"category"`
	Keyword               string `json:"keyword"`
	Education             string `json:"education"`
	Age                   string `json:"age"`
	RecommendedFilters    string `json:"recommended_filters"`
	SortPreference        string `json:"sort_preference"`
	FilterViewed14Days    bool   `json:"filter_viewed_14_days"`
	FilterExchanged30Days bool   `json:"filter_exchanged_30_days"`
}

type bossProcessProbe struct {
	Detected     bool   `json:"detected"`
	ExePath      string `json:"exe_path"`
	ProcessID    int    `json:"process_id"`
	ProcessName  string `json:"process_name"`
	WindowTitle  string `json:"window_title"`
	Visible      bool   `json:"visible"`
	Minimized    bool   `json:"minimized"`
	WindowLeft   int    `json:"window_left"`
	WindowTop    int    `json:"window_top"`
	WindowWidth  int    `json:"window_width"`
	WindowHeight int    `json:"window_height"`
	Message      string `json:"message"`
}

type bossChatMessagePayload struct {
	Name    string `json:"name"`
	Role    string `json:"role"`
	Content string `json:"content"`
}

type bossChatsPayload struct {
	Limit       int  `json:"limit"`
	Incremental bool `json:"incremental"`
}

func NewBossAssistantService(settings *repository.AppSettingRepository) *BossAssistantService {
	return &BossAssistantService{settings: settings}
}

func (s *BossAssistantService) GetStatus() (*BossAssistantStatus, error) {
	status := s.detectBossClient()
	saved, err := s.getSavedExePath()
	if err != nil {
		return nil, err
	}
	status.SavedExePath = saved
	return status, nil
}

func (s *BossAssistantService) DetectAndSave() (*BossAssistantStatus, error) {
	status := s.detectBossClient()
	if status.ExePath != "" && strings.EqualFold(status.ProcessName, "boss-zhipin") {
		if err := s.settings.SetValue(models.AppSettingKeyBossExePath, status.ExePath); err != nil {
			return nil, err
		}
		status.SavedExePath = status.ExePath
	} else {
		saved, err := s.getSavedExePath()
		if err != nil {
			return nil, err
		}
		status.SavedExePath = saved
	}
	return status, nil
}

func (s *BossAssistantService) SaveConfig(input SaveBossAssistantConfigInput) (*BossAssistantStatus, error) {
	exePath := strings.TrimSpace(input.ExePath)
	if exePath == "" {
		return nil, fmt.Errorf("exe_path is required")
	}
	if err := s.settings.SetValue(models.AppSettingKeyBossExePath, exePath); err != nil {
		return nil, err
	}
	status := s.detectBossClient()
	status.SavedExePath = exePath
	return status, nil
}

func (s *BossAssistantService) ClickMenu(input ClickBossMenuInput) (*ClickBossMenuResult, error) {
	menu := strings.TrimSpace(input.Menu)
	allowed := map[string]bool{"job": true, "recommend": true, "search": true, "chat": true}
	if !allowed[menu] {
		return nil, fmt.Errorf("unsupported BOSS menu")
	}
	if runtime.GOOS != "windows" {
		return nil, fmt.Errorf("BOSS menu click is only available on Windows")
	}

	output, err := runPowerShell(fmt.Sprintf(clickBossMenuScript, menu))
	if err != nil {
		return nil, err
	}
	return &ClickBossMenuResult{
		Menu:    menu,
		Output:  output,
		Message: "BOSS menu click executed; confirm the BOSS page changed",
	}, nil
}

func (s *BossAssistantService) SearchCandidates(input BossSearchInput) (*BossSearchResult, error) {
	if runtime.GOOS != "windows" {
		return nil, fmt.Errorf("BOSS search sync is only available on Windows")
	}
	category := bossSearchCategory(input.JobCategory)
	keyword := strings.TrimSpace(input.SearchKeyword)
	if keyword == "" && category != "" && !strings.Contains(category, "不限") {
		keyword = category
	}
	payload := bossSearchPayload{
		City:                  bossSearchCity(input.Location),
		Category:              category,
		Keyword:               keyword,
		Education:             bossSearchEducation(input.EducationRequirement),
		Age:                   bossSearchAge(input.AgeRequirement),
		RecommendedFilters:    strings.TrimSpace(input.RecommendedFilters),
		SortPreference:        strings.TrimSpace(input.SortPreference),
		FilterViewed14Days:    input.FilterViewed14Days,
		FilterExchanged30Days: input.FilterExchanged30Days,
	}
	if strings.TrimSpace(payload.Keyword) == "" && strings.TrimSpace(payload.Category) == "" {
		return nil, fmt.Errorf("search keyword or job category is required")
	}
	if result, err := runBossBrowserAgentSearch(payload); err == nil {
		return result, nil
	} else if strings.Contains(err.Error(), "city=") && strings.Contains(err.Error(), ":not-found") {
		return nil, err
	}
	raw, err := json.Marshal(payload)
	if err != nil {
		return nil, err
	}
	output, err := runPowerShell(fmt.Sprintf(bossSearchScript, base64.StdEncoding.EncodeToString(raw)))
	if err != nil {
		return nil, err
	}
	return &BossSearchResult{
		Output:  output,
		Message: "BOSS search fields filled; confirm the result list in BOSS",
	}, nil
}

func (s *BossAssistantService) ReadCandidates(limit int) (*BossCandidatesResult, error) {
	if runtime.GOOS != "windows" {
		return nil, fmt.Errorf("BOSS candidate import is only available on Windows")
	}
	return runBossBrowserAgentCandidates(normalizeBossCandidateLimit(limit))
}

func (s *BossAssistantService) ReadChats(limit int, incremental bool) (*BossChatsResult, error) {
	if runtime.GOOS != "windows" {
		return nil, fmt.Errorf("BOSS chat import is only available on Windows")
	}
	return runBossBrowserAgentChats(normalizeBossCandidateLimit(limit), incremental)
}

func (s *BossAssistantService) SendChatMessage(input BossChatMessageInput) (*BossChatMessageResult, error) {
	name := strings.TrimSpace(input.Name)
	content := strings.TrimSpace(input.Content)
	if name == "" {
		return nil, fmt.Errorf("BOSS chat target name is required")
	}
	if content == "" {
		return nil, fmt.Errorf("BOSS message content is required")
	}
	if runtime.GOOS != "windows" {
		return nil, fmt.Errorf("BOSS message sync is only available on Windows")
	}
	return runBossBrowserAgentSendMessage(bossChatMessagePayload{
		Name:    name,
		Role:    strings.TrimSpace(input.Role),
		Content: content,
	})
}

func (s *BossAssistantService) DeleteChat(input BossChatMessageInput) (*BossChatDeleteResult, error) {
	name := strings.TrimSpace(input.Name)
	if name == "" {
		return nil, fmt.Errorf("BOSS chat target name is required")
	}
	if runtime.GOOS != "windows" {
		return nil, fmt.Errorf("BOSS chat delete is only available on Windows")
	}
	return runBossBrowserAgentDeleteChat(bossChatMessagePayload{
		Name: name,
		Role: strings.TrimSpace(input.Role),
	})
}

func runBossBrowserAgentSearch(payload bossSearchPayload) (*BossSearchResult, error) {
	baseURL := strings.TrimRight(strings.TrimSpace(os.Getenv("RECRUITMENT_AGENT_URL")), "/")
	if baseURL == "" {
		return nil, fmt.Errorf("recruitment agent url is not configured")
	}
	raw, err := json.Marshal(payload)
	if err != nil {
		return nil, err
	}
	ctx, cancel := context.WithTimeout(context.Background(), 45*time.Second)
	defer cancel()
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, baseURL+"/v1/boss/search", bytes.NewReader(raw))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(io.LimitReader(resp.Body, 16*1024))
	if err != nil {
		return nil, err
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil, fmt.Errorf("boss browser search failed: %s", strings.TrimSpace(string(body)))
	}
	var out struct {
		Output  string `json:"output"`
		Message string `json:"message"`
	}
	if err := json.Unmarshal(body, &out); err != nil {
		return nil, err
	}
	if strings.TrimSpace(out.Message) == "" {
		out.Message = "BOSS browser search executed"
	}
	return &BossSearchResult{Output: out.Output, Message: out.Message}, nil
}

func runBossBrowserAgentSendMessage(payload bossChatMessagePayload) (*BossChatMessageResult, error) {
	baseURL := strings.TrimRight(strings.TrimSpace(os.Getenv("RECRUITMENT_AGENT_URL")), "/")
	if baseURL == "" {
		return nil, fmt.Errorf("recruitment agent url is not configured")
	}
	raw, err := json.Marshal(payload)
	if err != nil {
		return nil, err
	}
	ctx, cancel := context.WithTimeout(context.Background(), 45*time.Second)
	defer cancel()
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, baseURL+"/v1/boss/send-message", bytes.NewReader(raw))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(io.LimitReader(resp.Body, 32*1024))
	if err != nil {
		return nil, err
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil, fmt.Errorf("boss browser message send failed: %s", strings.TrimSpace(string(body)))
	}
	var out BossChatMessageResult
	if err := json.Unmarshal(body, &out); err != nil {
		return nil, err
	}
	if strings.TrimSpace(out.Message) == "" {
		out.Message = "BOSS message sent"
	}
	return &out, nil
}

func runBossBrowserAgentDeleteChat(payload bossChatMessagePayload) (*BossChatDeleteResult, error) {
	baseURL := strings.TrimRight(strings.TrimSpace(os.Getenv("RECRUITMENT_AGENT_URL")), "/")
	if baseURL == "" {
		return nil, fmt.Errorf("recruitment agent url is not configured")
	}
	raw, err := json.Marshal(payload)
	if err != nil {
		return nil, err
	}
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, baseURL+"/v1/boss/delete-chat", bytes.NewReader(raw))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(io.LimitReader(resp.Body, 256*1024))
	if err != nil {
		return nil, err
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil, fmt.Errorf("boss browser delete chat failed: %s", strings.TrimSpace(string(body)))
	}
	var out BossChatDeleteResult
	if err := json.Unmarshal(body, &out); err != nil {
		return nil, err
	}
	if strings.TrimSpace(out.Message) == "" {
		out.Message = "BOSS chat deleted"
	}
	return &out, nil
}

func runBossBrowserAgentCandidates(limit int) (*BossCandidatesResult, error) {
	baseURL := strings.TrimRight(strings.TrimSpace(os.Getenv("RECRUITMENT_AGENT_URL")), "/")
	if baseURL == "" {
		return nil, fmt.Errorf("recruitment agent url is not configured")
	}
	raw, err := json.Marshal(map[string]int{"limit": limit})
	if err != nil {
		return nil, err
	}
	ctx, cancel := context.WithTimeout(context.Background(), 45*time.Second)
	defer cancel()
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, baseURL+"/v1/boss/candidates", bytes.NewReader(raw))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(io.LimitReader(resp.Body, 256*1024))
	if err != nil {
		return nil, err
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil, fmt.Errorf("boss browser candidates import failed: %s", strings.TrimSpace(string(body)))
	}
	var out BossCandidatesResult
	if err := json.Unmarshal(body, &out); err != nil {
		return nil, err
	}
	if strings.TrimSpace(out.Message) == "" {
		out.Message = "BOSS candidates read"
	}
	return &out, nil
}

func runBossBrowserAgentChats(limit int, incremental bool) (*BossChatsResult, error) {
	baseURL := strings.TrimRight(strings.TrimSpace(os.Getenv("RECRUITMENT_AGENT_URL")), "/")
	if baseURL == "" {
		return nil, fmt.Errorf("recruitment agent url is not configured")
	}
	raw, err := json.Marshal(bossChatsPayload{Limit: limit, Incremental: incremental})
	if err != nil {
		return nil, err
	}
	ctx, cancel := context.WithTimeout(context.Background(), 45*time.Second)
	defer cancel()
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, baseURL+"/v1/boss/chats", bytes.NewReader(raw))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(io.LimitReader(resp.Body, 256*1024))
	if err != nil {
		return nil, err
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil, fmt.Errorf("boss browser chats import failed: %s", strings.TrimSpace(string(body)))
	}
	var out BossChatsResult
	if err := json.Unmarshal(body, &out); err != nil {
		return nil, err
	}
	if strings.TrimSpace(out.Message) == "" {
		out.Message = "BOSS chats read"
	}
	return &out, nil
}

func normalizeBossCandidateLimit(value int) int {
	if value <= 0 {
		return 10
	}
	if value > 50 {
		return 50
	}
	return value
}

func BossChatTargetFromNotes(notes string) (string, string) {
	var name, role string
	for _, line := range strings.Split(notes, "\n") {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		if name == "" && strings.Contains(line, "候选人") {
			name = cleanBossChatTargetValue(afterAnyColon(line))
		}
		if role == "" && strings.Contains(line, "岗位") {
			role = strings.TrimSpace(afterAnyColon(line))
		}
	}
	return name, role
}

func afterAnyColon(value string) string {
	if _, after, ok := strings.Cut(value, "："); ok {
		return after
	}
	if _, after, ok := strings.Cut(value, ":"); ok {
		return after
	}
	return value
}

func cleanBossChatTargetValue(value string) string {
	value = strings.TrimSpace(value)
	for _, sep := range []string{"·", "（", "(", "|"} {
		if before, _, ok := strings.Cut(value, sep); ok {
			value = strings.TrimSpace(before)
		}
	}
	return value
}

func (s *BossAssistantService) getSavedExePath() (string, error) {
	row, err := s.settings.Get(models.AppSettingKeyBossExePath)
	if err != nil || row == nil {
		return "", err
	}
	return row.Value, nil
}

func bossSearchCategory(category string) string {
	category = strings.TrimSpace(category)
	if category == "" || category == "自定义" {
		return ""
	}
	return category
}

func bossSearchCity(location string) string {
	location = strings.TrimSpace(location)
	for _, marker := range []string{"特别行政区", "自治区", "省"} {
		if index := strings.LastIndex(location, marker); index >= 0 && index+len(marker) < len(location) {
			location = location[index+len(marker):]
			break
		}
	}
	return strings.TrimSpace(location)
}

func bossSearchEducation(value string) string {
	value = strings.TrimSpace(value)
	if value == "" || strings.Contains(value, "不限") {
		return "不限"
	}
	for _, allowed := range []string{"本科及以上", "硕士及以上", "博士"} {
		if value == allowed {
			return value
		}
	}
	if strings.Contains(value, "-") {
		return value
	}
	return ""
}

func bossSearchAge(value string) string {
	value = strings.TrimSpace(value)
	if value == "" || strings.Contains(value, "不限") {
		return "不限"
	}
	for _, allowed := range []string{"20-25", "25-30", "30-35", "35-40", "40-50", "50以上"} {
		if value == allowed {
			return value
		}
	}
	return ""
}

const clickBossMenuScript = `
$ErrorActionPreference = 'Stop'
$menu = '%s'
$points = @{
  job = @(100, 170)
  recommend = @(105, 207)
  search = @(85, 240)
  chat = @(85, 273)
}
Add-Type @'
using System;
using System.Text;
using System.Runtime.InteropServices;
public static class BossClickWin32 {
  public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out int processId);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowTextLength(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr hWnd, IntPtr hWndInsertAfter, int x, int y, int cx, int cy, uint flags);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int command);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
  [DllImport("user32.dll")] public static extern void mouse_event(uint flags, uint dx, uint dy, uint data, UIntPtr extraInfo);
  public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
  public static string GetTitle(IntPtr hWnd) {
    int len = GetWindowTextLength(hWnd);
    if (len <= 0) return "";
    var sb = new StringBuilder(len + 1);
    GetWindowText(hWnd, sb, sb.Capacity);
    return sb.ToString();
  }
}
'@
$bossWindow = $null
[BossClickWin32]::EnumWindows({
  param([IntPtr]$hWnd, [IntPtr]$lParam)
  if (-not [BossClickWin32]::IsWindowVisible($hWnd)) { return $true }
  $windowPid = 0
  [BossClickWin32]::GetWindowThreadProcessId($hWnd, [ref]$windowPid) | Out-Null
  $proc = Get-Process -Id $windowPid -ErrorAction SilentlyContinue
  if ($proc -and $proc.ProcessName -eq 'chrome') {
    $title = [BossClickWin32]::GetTitle($hWnd)
    if ($title -match 'BOSS|zhipin') {
      $script:bossWindow = [pscustomobject]@{ Process = $proc; Handle = $hWnd; Title = $title }
      return $false
    }
  }
  return $true
}, [IntPtr]::Zero) | Out-Null
if (-not $bossWindow) { throw 'BOSS Chrome window not found. Open BOSS in Chrome first.' }
$rect = New-Object BossClickWin32+RECT
[BossClickWin32]::ShowWindow($bossWindow.Handle, 9) | Out-Null
[BossClickWin32]::SetForegroundWindow($bossWindow.Handle) | Out-Null
[BossClickWin32]::BringWindowToTop($bossWindow.Handle) | Out-Null
$focusFlags = 0x0001 -bor 0x0002 -bor 0x0040
[BossClickWin32]::SetWindowPos($bossWindow.Handle, [IntPtr]::new(-1), 0, 0, 0, 0, $focusFlags) | Out-Null
Start-Sleep -Milliseconds 100
[BossClickWin32]::SetWindowPos($bossWindow.Handle, [IntPtr]::new(-2), 0, 0, 0, 0, $focusFlags) | Out-Null
[BossClickWin32]::SetForegroundWindow($bossWindow.Handle) | Out-Null
Start-Sleep -Milliseconds 300
if ([BossClickWin32]::GetForegroundWindow() -ne $bossWindow.Handle) { throw 'BOSS Chrome window is not foreground. Click the BOSS window once, then retry.' }
[BossClickWin32]::GetWindowRect($bossWindow.Handle, [ref]$rect) | Out-Null
$point = $points[$menu]
$x = $rect.Left + $point[0]
$y = $rect.Top + 40 + $point[1]
# ponytail: coordinate fallback for BOSS pages that block DevTools/DOM reads; replace with DOM locators if the page becomes stable.
[BossClickWin32]::SetCursorPos($x, $y) | Out-Null
Start-Sleep -Milliseconds 100
[BossClickWin32]::mouse_event(0x0002, 0, 0, 0, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 80
[BossClickWin32]::mouse_event(0x0004, 0, 0, 0, [UIntPtr]::Zero)
"menu=$menu click=($x,$y) window='$($bossWindow.Title)'"
`

const bossSearchScript = `
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.Windows.Forms
$payloadJson = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('%s'))
$payload = $payloadJson | ConvertFrom-Json
$points = @{
  searchMenu = @(85, 240)
  city = @(345, 85)
  category = @(520, 85)
  keyword = @(760, 85)
  searchButton = @(1110, 85)
}
$educationPoints = @{
  '不限' = @(214, 246)
  '本科及以上' = @(333, 246)
  '硕士及以上' = @(493, 246)
  '博士' = @(598, 246)
}
$agePoints = @{
  '不限' = @(214, 306)
  '20-25' = @(300, 306)
  '25-30' = @(397, 306)
  '30-35' = @(493, 306)
  '35-40' = @(589, 306)
  '40-50' = @(684, 306)
  '50以上' = @(781, 306)
}
Add-Type @'
using System;
using System.Text;
using System.Runtime.InteropServices;
public static class BossSearchWin32 {
  public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out int processId);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowTextLength(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr hWnd, IntPtr hWndInsertAfter, int x, int y, int cx, int cy, uint flags);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int command);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
  [DllImport("user32.dll")] public static extern void mouse_event(uint flags, uint dx, uint dy, uint data, UIntPtr extraInfo);
  public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
  public static string GetTitle(IntPtr hWnd) {
    int len = GetWindowTextLength(hWnd);
    if (len <= 0) return "";
    var sb = new StringBuilder(len + 1);
    GetWindowText(hWnd, sb, sb.Capacity);
    return sb.ToString();
  }
}
'@
$bossWindow = $null
[BossSearchWin32]::EnumWindows({
  param([IntPtr]$hWnd, [IntPtr]$lParam)
  if (-not [BossSearchWin32]::IsWindowVisible($hWnd)) { return $true }
  $windowPid = 0
  [BossSearchWin32]::GetWindowThreadProcessId($hWnd, [ref]$windowPid) | Out-Null
  $proc = Get-Process -Id $windowPid -ErrorAction SilentlyContinue
  if ($proc -and $proc.ProcessName -eq 'chrome') {
    $title = [BossSearchWin32]::GetTitle($hWnd)
    if ($title -match 'BOSS|zhipin') {
      $script:bossWindow = [pscustomobject]@{ Process = $proc; Handle = $hWnd; Title = $title }
      return $false
    }
  }
  return $true
}, [IntPtr]::Zero) | Out-Null
if (-not $bossWindow) { throw 'BOSS Chrome window not found. Open BOSS in Chrome first.' }
$rect = New-Object BossSearchWin32+RECT
[BossSearchWin32]::ShowWindow($bossWindow.Handle, 9) | Out-Null
[BossSearchWin32]::SetForegroundWindow($bossWindow.Handle) | Out-Null
[BossSearchWin32]::BringWindowToTop($bossWindow.Handle) | Out-Null
$focusFlags = 0x0001 -bor 0x0002 -bor 0x0040
[BossSearchWin32]::SetWindowPos($bossWindow.Handle, [IntPtr]::new(-1), 0, 0, 0, 0, $focusFlags) | Out-Null
Start-Sleep -Milliseconds 100
[BossSearchWin32]::SetWindowPos($bossWindow.Handle, [IntPtr]::new(-2), 0, 0, 0, 0, $focusFlags) | Out-Null
[BossSearchWin32]::SetForegroundWindow($bossWindow.Handle) | Out-Null
Start-Sleep -Milliseconds 300
if ([BossSearchWin32]::GetForegroundWindow() -ne $bossWindow.Handle) { throw 'BOSS Chrome window is not foreground. Click the BOSS window once, then retry.' }
[BossSearchWin32]::GetWindowRect($bossWindow.Handle, [ref]$rect) | Out-Null
function ClickPoint($point) {
  $x = $rect.Left + $point[0]
  $y = $rect.Top + 90 + $point[1]
  [BossSearchWin32]::SetCursorPos($x, $y) | Out-Null
  Start-Sleep -Milliseconds 80
  [BossSearchWin32]::mouse_event(0x0002, 0, 0, 0, [UIntPtr]::Zero)
  Start-Sleep -Milliseconds 60
  [BossSearchWin32]::mouse_event(0x0004, 0, 0, 0, [UIntPtr]::Zero)
  Start-Sleep -Milliseconds 160
}
function ClickMenuPoint($point) {
  $x = $rect.Left + $point[0]
  $y = $rect.Top + 40 + $point[1]
  [BossSearchWin32]::SetCursorPos($x, $y) | Out-Null
  Start-Sleep -Milliseconds 80
  [BossSearchWin32]::mouse_event(0x0002, 0, 0, 0, [UIntPtr]::Zero)
  Start-Sleep -Milliseconds 60
  [BossSearchWin32]::mouse_event(0x0004, 0, 0, 0, [UIntPtr]::Zero)
  Start-Sleep -Milliseconds 160
}
function PasteValue([string]$value) {
  if ([string]::IsNullOrWhiteSpace($value)) { return }
  Set-Clipboard -Value $value
  Start-Sleep -Milliseconds 80
  [System.Windows.Forms.SendKeys]::SendWait('^a')
  Start-Sleep -Milliseconds 50
  [System.Windows.Forms.SendKeys]::SendWait('^v')
  Start-Sleep -Milliseconds 120
}
function PasteValueAndPick([string]$value) {
  if ([string]::IsNullOrWhiteSpace($value)) { return }
  PasteValue $value
  Start-Sleep -Milliseconds 250
  [System.Windows.Forms.SendKeys]::SendWait('{DOWN}')
  Start-Sleep -Milliseconds 80
  [System.Windows.Forms.SendKeys]::SendWait('{ENTER}')
  Start-Sleep -Milliseconds 200
  [System.Windows.Forms.SendKeys]::SendWait('{ESC}')
  Start-Sleep -Milliseconds 120
}
function ClickFilterValue($map, [string]$value) {
  if ([string]::IsNullOrWhiteSpace($value)) { return }
  if (-not $map.ContainsKey($value)) { return }
  ClickPoint $map[$value]
  Start-Sleep -Milliseconds 180
}
$oldClipboard = $null
try { $oldClipboard = Get-Clipboard -Raw -ErrorAction SilentlyContinue } catch {}
try {
  ClickMenuPoint $points.searchMenu
  Start-Sleep -Milliseconds 900
  if (-not [string]::IsNullOrWhiteSpace([string]$payload.category) -and ([string]$payload.category) -notmatch '不限') {
    ClickPoint $points.category
    PasteValueAndPick ([string]$payload.category)
    Start-Sleep -Milliseconds 250
  }
  if (-not [string]::IsNullOrWhiteSpace([string]$payload.city)) {
    ClickPoint $points.city
    PasteValueAndPick ([string]$payload.city)
    Start-Sleep -Milliseconds 350
  }
  ClickPoint $points.keyword
  PasteValue ([string]$payload.keyword)
  ClickFilterValue $educationPoints ([string]$payload.education)
  ClickFilterValue $agePoints ([string]$payload.age)
  ClickPoint $points.keyword
  [System.Windows.Forms.SendKeys]::SendWait('{ENTER}')
  Start-Sleep -Milliseconds 250
  ClickPoint $points.searchButton
  Start-Sleep -Milliseconds 250
  [System.Windows.Forms.SendKeys]::SendWait('{ENTER}')
} finally {
  if ($null -ne $oldClipboard) {
    Set-Clipboard -Value $oldClipboard
  }
}
"window='$($bossWindow.Title)' city='$($payload.city)' category='$($payload.category)' keyword='$($payload.keyword)' education='$($payload.education)' age='$($payload.age)'"
`

func (s *BossAssistantService) detectBossClient() *BossAssistantStatus {
	now := time.Now().Format("2006-01-02 15:04:05")
	status := &BossAssistantStatus{
		LastCheckedAt: now,
		Message:       "manual login required before using BOSS assistant",
	}
	if runtime.GOOS != "windows" {
		status.Message = "BOSS desktop detection is only available on Windows"
		return status
	}

	probe, err := probeBossProcess()
	if err != nil {
		status.Message = err.Error()
		return status
	}
	status.Detected = probe.Detected
	status.ExePath = probe.ExePath
	status.ProcessID = probe.ProcessID
	status.ProcessName = probe.ProcessName
	status.WindowTitle = probe.WindowTitle
	status.Visible = probe.Visible
	status.Minimized = probe.Minimized
	status.WindowLeft = probe.WindowLeft
	status.WindowTop = probe.WindowTop
	status.WindowWidth = probe.WindowWidth
	status.WindowHeight = probe.WindowHeight
	status.Message = probe.Message
	if status.Message == "" && status.Detected {
		if strings.EqualFold(status.ProcessName, "chrome") {
			status.Message = "BOSS web page detected in Chrome; please confirm it is manually logged in"
		} else {
			status.Message = "BOSS desktop client detected; please confirm it is manually logged in"
		}
	}
	return status
}

func probeBossProcess() (*bossProcessProbe, error) {
	const script = `
$ErrorActionPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type @'
using System;
using System.Text;
using System.Runtime.InteropServices;
public class Win32WindowProbe {
  public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out int processId);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowTextLength(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
  public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
  public static string GetTitle(IntPtr hWnd) {
    int len = GetWindowTextLength(hWnd);
    if (len <= 0) return "";
    var sb = new StringBuilder(len + 1);
    GetWindowText(hWnd, sb, sb.Capacity);
    return sb.ToString();
  }
}
'@
$p = Get-Process -Name 'boss-zhipin' -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
if (-not $p) {
  $p = Get-Process -Name 'boss-zhipin' -ErrorAction SilentlyContinue | Select-Object -First 1
}
$handle = if ($p) { $p.MainWindowHandle } else { [IntPtr]::Zero }
$title = if ($p) { $p.MainWindowTitle } else { '' }
if (-not $p) {
  $bossWindow = $null
  [Win32WindowProbe]::EnumWindows({
    param([IntPtr]$hWnd, [IntPtr]$lParam)
    if (-not [Win32WindowProbe]::IsWindowVisible($hWnd)) { return $true }
    $windowPid = 0
    [Win32WindowProbe]::GetWindowThreadProcessId($hWnd, [ref]$windowPid) | Out-Null
    $proc = Get-Process -Id $windowPid -ErrorAction SilentlyContinue
    if ($proc -and $proc.ProcessName -eq 'chrome') {
      $windowTitle = [Win32WindowProbe]::GetTitle($hWnd)
      if ($windowTitle -match 'BOSS|zhipin') {
        $script:bossWindow = [pscustomobject]@{ Process = $proc; Handle = $hWnd; Title = $windowTitle }
        return $false
      }
    }
    return $true
  }, [IntPtr]::Zero) | Out-Null
  if ($bossWindow) {
    $p = $bossWindow.Process
    $handle = $bossWindow.Handle
    $title = $bossWindow.Title
  }
}
if (-not $p) {
  $p = Get-Process -Name 'chrome' -ErrorAction SilentlyContinue |
    Where-Object { $_.MainWindowHandle -ne 0 -and $_.MainWindowTitle -match 'BOSS|zhipin|直聘' } |
    Select-Object -First 1
}
if ($p -and $handle -eq [IntPtr]::Zero) {
  $handle = $p.MainWindowHandle
  $title = $p.MainWindowTitle
}
if (-not $p) {
  [pscustomobject]@{
    detected = $false
    message = 'BOSS desktop client or current Chrome BOSS tab not found'
  } | ConvertTo-Json -Compress
  exit 0
}
$rect = New-Object Win32WindowProbe+RECT
$hasRect = $false
$visible = $false
$minimized = $false
if ($handle -ne [IntPtr]::Zero) {
  $hasRect = [Win32WindowProbe]::GetWindowRect($handle, [ref]$rect)
  $visible = [Win32WindowProbe]::IsWindowVisible($handle)
  $minimized = [Win32WindowProbe]::IsIconic($handle)
}
$path = ''
try { $path = $p.Path } catch { $path = '' }
[pscustomobject]@{
  detected = $true
  exe_path = $path
  process_id = $p.Id
  process_name = $p.ProcessName
  window_title = $title
  visible = $visible
  minimized = $minimized
  window_left = $(if ($hasRect) { $rect.Left } else { 0 })
  window_top = $(if ($hasRect) { $rect.Top } else { 0 })
  window_width = $(if ($hasRect) { $rect.Right - $rect.Left } else { 0 })
  window_height = $(if ($hasRect) { $rect.Bottom - $rect.Top } else { 0 })
  message = ''
} | ConvertTo-Json -Compress
`
	output, err := runPowerShell(script)
	if err != nil {
		return nil, err
	}
	var probe bossProcessProbe
	if err := json.Unmarshal([]byte(output), &probe); err != nil {
		return nil, fmt.Errorf("failed to parse BOSS detection output: %w", err)
	}
	return &probe, nil
}

func runPowerShell(script string) (string, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	commands := [][]string{
		{"powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script},
		{"pwsh.exe", "-NoProfile", "-Command", script},
	}
	var lastErr error
	for _, parts := range commands {
		cmd := exec.CommandContext(ctx, parts[0], parts[1:]...)
		out, err := cmd.CombinedOutput()
		text := strings.TrimSpace(string(out))
		if err == nil && text != "" {
			return text, nil
		}
		if err != nil {
			lastErr = fmt.Errorf("%s failed: %v %s", parts[0], err, text)
		} else {
			lastErr = fmt.Errorf("%s returned empty output", parts[0])
		}
	}
	if lastErr != nil {
		return "", lastErr
	}
	return "", fmt.Errorf("PowerShell is unavailable")
}
