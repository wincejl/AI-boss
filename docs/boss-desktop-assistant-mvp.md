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
