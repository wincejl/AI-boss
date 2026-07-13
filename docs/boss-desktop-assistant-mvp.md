# BOSS Desktop Assistant MVP

This document defines the desktop-assisted BOSS workflow for Agent 1.

## Operating Boundary

The project does not store or manage BOSS credentials.

Each use starts with the recruiter manually opening BOSS and completing login in the official BOSS desktop client. The project only assists after the recruiter confirms the BOSS client is logged in.

The project must not:

- Store BOSS account passwords.
- Store BOSS cookies, tokens, or local session files.
- Bypass CAPTCHA, QR code login, risk control, or device verification.
- Reverse engineer private BOSS APIs.
- Run unattended bulk messaging.
- Collect or store private contact information before explicit candidate consent.

The project may:

- Store the local BOSS exe path if the user wants one-click launch later.
- Store the last known connection/check status.
- Store search preferences such as role, city, district, and keywords.
- Assist with visible-screen data extraction after login.
- Generate AI match analysis and message drafts.
- Let a human confirm before copying or sending message text.

## Manual-Login Workflow

1. Recruiter opens the official BOSS desktop client.
2. Recruiter manually logs in.
3. Recruiter opens AI-CS recruitment Agent.
4. Recruiter selects a recruitment requirement.
5. Project shows suggested BOSS search parameters:
   - role
   - city
   - district
   - keywords
   - must-have conditions
6. Recruiter searches in BOSS.
7. Recruiter chooses visible candidate profiles.
8. Project imports or helps paste candidate profile text into the candidate pool.
9. Kimi generates:
   - match score
   - match reason
   - risk points
   - first-contact draft
   - next-question draft
10. Recruiter reviews and sends messages in BOSS.
11. Recruiter records reply status, consent status, private contact, and group status in AI-CS.

## Recommended MVP Features

### Desktop UIA Not Used

Current Windows validation result:

- `boss-zhipin.exe` processes can be detected.
- If all BOSS processes report `MainWindowHandle=0` and no UIA window is visible, the desktop client is treated as running but not automatable.
- The UI Automation probe path has been removed from the codebase. In this state the project should continue using the browser automation path, manual paste workflow, or the supervised visual fallback below.

### Windows Graphics Capture Path

Current Windows validation result:

- BOSS desktop client can be detected as a `Chrome_WidgetWin_0` window titled `BOSS直聘`.
- `tools/wgc-capture/wgc-capture.exe --auto-boss boss-auto.png` captures the BOSS desktop client with Windows Graphics Capture.
- `tools/wgc-capture/wgc-capture.exe --scan boss-scan 3` can click the visible chat-list rows and save one screenshot per selected conversation.
- The helper uses Windows Graphics Capture for frames and Win32 mouse clicks only for visible chat-list navigation. It does not type, paste, send messages, read local BOSS data, hook processes, sniff traffic, or call private BOSS APIs.

Service endpoints:

- `GET /v1/boss/desktop/wgc-status`
- `POST /v1/boss/desktop/capture`
- `POST /v1/boss/desktop/scan` with `{ "count": 3 }`

Safety switches:

```env
BOSS_VISUAL_SCREENSHOT_PROBE=true
BOSS_DESKTOP_CLICK_PROBE=true
```

`BOSS_DESKTOP_CLICK_PROBE` must stay `false` by default. Enable it only during a visible, supervised desktop test.

Recommended desktop MVP:

1. User opens BOSS desktop client and logs in manually.
2. Helper detects the BOSS window and captures it with WGC.
3. Helper clicks only visible chat-list rows to inspect conversations.
4. OCR extracts visible candidate/chat text from screenshots.
5. AI generates match analysis and reply drafts.
6. Human reviews the draft before any copy/paste/send action.

### Visual Automation Fallback

If UI Automation cannot see the desktop client, the next fallback is visual automation. This is less stable and has higher privacy risk, so it must start as capability probing only:

- `agent-service/app/boss_visual.py` checks whether PyAutoGUI, Pillow, MSS, OpenCV, NumPy, pytesseract, and the Tesseract engine are available.
- By default it does not take screenshots and does not run OCR.
- Any screenshot probe must be explicitly enabled with `BOSS_VISUAL_SCREENSHOT_PROBE=true`.
- The bounded probe `/v1/boss/visual/region-probe` returns only region metadata and average color; it does not store or return screenshots.
- On Windows, bounded screenshots may fail from a background service with `BitBlt: access denied`; run visual probes only in the user's interactive desktop session with explicit approval.
- OCR must be separately enabled with `BOSS_VISUAL_OCR_PROBE=true`.
- Cloud OCR is available only as an explicit, supervised test path. PaddleOCR cloud is the preferred test provider for now, and requires all of these switches:
  - `BOSS_VISUAL_SCREENSHOT_PROBE=true`
  - `BOSS_VISUAL_OCR_PROBE=true`
  - `OCR_PROVIDER=paddle_cloud`
  - `OCR_CLOUD_ENABLED=true`
  - `OCR_PADDLE_TOKEN`
- The OCR endpoint accepts only a bounded rectangle, never a full-screen upload by default, and it does not save or return the captured image.
- Cloud OCR can expose names, messages, and contact details to the provider. Use it only for short manual tests; prefer a future local PaddleOCR provider for routine use.
- Prefer template matching for fixed buttons/regions before OCR; OCR should be used only on a small user-confirmed rectangle.
- Never run visual click/send actions in the background. Require a human-visible preview and confirmation first.

Recommended dependency levels:

- Basic screen probe: `pyautogui`, `pillow`, `mss`.
- Template matching: add `opencv-python-headless`, `numpy`.
- Local OCR: add `pytesseract` plus a separately installed Tesseract OCR engine, or add a future PaddleOCR provider for better Chinese recognition.
- Cloud OCR test: configure the PaddleOCR cloud provider above; keep `OCR_SAVE_IMAGES=false`.

Direct BOSS message sending is disabled by default. Enable it only for a controlled manual test with:

```env
BOSS_MESSAGE_SEND_ENABLED=true
```

Background BOSS sync is also disabled by default and should not run faster than the guarded interval:

```env
BOSS_AUTO_SYNC_ENABLED=false
BOSS_AUTO_SYNC_INTERVAL_SECONDS=60
```

### Phase 1: Manual Paste

- Add "Paste BOSS Profile" panel in Recruitment Agent.
- User pastes candidate profile text copied from BOSS.
- AI extracts structured candidate fields.
- Candidate is saved into the selected requirement.
- AI generates first-contact draft.

This phase requires no desktop automation and is the safest first step.

### Phase 2: Local Window Helper

- Add a local helper process for Windows.
- User confirms BOSS is already open and logged in.
- Helper detects the BOSS window.
- Helper can copy visible profile text or take OCR screenshots.
- Helper sends extracted profile text to AI-CS through localhost.

### Phase 3: Assisted Messaging

- Project generates a draft.
- User reviews the draft.
- Project copies the draft to clipboard.
- User pastes/sends it in BOSS, or the helper pastes only after explicit click confirmation.

## Project State To Store

Safe to store:

- `boss_exe_path`
- `boss_window_detected`
- `boss_last_checked_at`
- `default_search_role`
- `default_search_location`
- `default_search_keywords`
- `last_imported_candidate_at`

Do not store:

- BOSS password
- BOSS cookies
- BOSS access tokens
- BOSS local session files
- CAPTCHA or login verification data

## Consent Rule

Private contact fields can be saved only when the candidate has explicitly agreed.

Required candidate fields:

- `consent_to_contact`
- `private_contact`
- `group_status`
- `last_message`
- `next_action`

The first-contact draft should stay inside the platform and ask whether the candidate is interested. It should not directly ask for phone, WeChat, or group joining.

## Next Implementation Step

Implement Phase 1 first:

1. Add "Paste BOSS Profile" input on the Recruitment Agent page.
2. Add backend endpoint to call Kimi and extract candidate fields from pasted text.
3. Save the parsed candidate into the selected requirement.
4. Generate a compliant first-contact draft.
