# BOSS Integration Requirements

This document defines the minimum API capabilities needed for the recruitment Agent 1 workflow in this project.

## Goal

Agent 1 helps recruiters create a hiring requirement, find matching candidates on BOSS, start compliant conversations, track replies, request contact consent, and invite candidates into a private group only after explicit consent.

The integration must use official or explicitly authorized BOSS interfaces. It must not bypass platform login, anti-bot controls, privacy controls, or candidate consent rules.

## Required API Capabilities

### 1. Authentication And Tenant Scope

Required information from BOSS:

- API base URL for production and sandbox.
- Authentication method: OAuth2, app key/secret, access token, or other signed request method.
- Token lifecycle: expiration, refresh flow, revoke flow.
- Enterprise account scope: company ID, recruiter ID, store/brand ID if applicable.
- Permission scopes required for candidate search, job search, messaging, and webhooks.
- Rate limits per enterprise, recruiter, endpoint, and time window.
- Sandbox/test account availability.

### 2. Job And Requirement Sync

Needed endpoints:

- List active jobs under the enterprise account.
- Get one job detail.
- Optional: create/update a job if BOSS permits this through API.

Minimum fields:

- `boss_job_id`
- `title`
- `role`
- `city`
- `district`
- `salary_range`
- `experience_required`
- `education_required`
- `skills`
- `description`
- `job_status`
- `recruiter_id`
- `updated_at`

Project mapping:

- BOSS job maps to `recruitment_requirements`.
- `title`, `role`, `location`, `tags`, `must_have`, `nice_have`, `description`, `status` should be populated from BOSS job data.

### 3. Candidate Search

Needed endpoint:

- Search candidates by job, keyword, city, district, experience, skill tags, active time, and availability.

Minimum request filters:

- `job_id` or custom role keyword.
- `city`
- `district`
- `keywords`
- `skills`
- `experience_min`
- `experience_max`
- `availability`
- `page`
- `page_size`

Minimum response fields:

- `boss_candidate_id`
- `display_name` or masked name if real name is unavailable.
- `current_role`
- `city`
- `district`
- `experience_years`
- `skills`
- `profile_summary`
- `resume_text` if authorized.
- `last_active_at`
- `can_message`
- `privacy_level`
- `source_url` if allowed.

Project mapping:

- BOSS candidate maps to `recruitment_candidates`.
- `boss_candidate_id` should be stored for deduplication.
- `profile_summary`, skills, role, and location are used by AI scoring and draft generation.

### 4. Candidate Detail

Needed endpoint:

- Get authorized candidate profile detail by `boss_candidate_id`.

Important questions for BOSS:

- Which fields are available before candidate reply?
- Which fields require candidate authorization?
- Which fields are masked?
- Can resume text be used for automated scoring?
- Can profile data be stored in our system? If yes, for how long?

Minimum response fields:

- Basic profile fields from candidate search.
- Work experience.
- Certifications.
- Expected role.
- Expected city.
- Self introduction.
- Resume attachment URL if allowed.
- Data retention rules.

### 5. Messaging

Needed endpoints:

- Send message to candidate.
- List conversation threads.
- Get conversation messages.
- Mark messages read if supported.

Minimum send request:

- `boss_candidate_id`
- `boss_job_id`
- `recruiter_id`
- `message`
- `client_message_id` for idempotency.

Minimum message response:

- `boss_conversation_id`
- `boss_message_id`
- `sender_type`
- `message_type`
- `content`
- `created_at`
- `send_status`
- `failure_reason`

Compliance requirements:

- API must specify whether template messages are required.
- API must specify message frequency limits.
- API must specify whether AI-generated text needs human confirmation.
- The project should support human review before sending unless BOSS explicitly allows automated sends.

### 6. Webhooks Or Polling

Preferred capability:

- Webhook for candidate replies, message delivery status, authorization changes, and candidate privacy/consent events.

Webhook events needed:

- `conversation.created`
- `message.received`
- `message.sent`
- `message.failed`
- `candidate.replied`
- `candidate.consent.updated`
- `candidate.profile.updated`

Webhook requirements:

- Signature verification method.
- Retry policy.
- Event ID for idempotency.
- Event timestamp.
- Sandbox event testing.

If webhooks are unavailable:

- Provide polling endpoint and recommended polling interval.
- Provide cursor-based incremental sync.

### 7. Contact Consent And Private Contact

Needed capabilities:

- Determine whether the candidate has explicitly allowed contact exchange.
- Receive or query consent status.
- Read private contact information only after authorized consent, if BOSS permits.

Minimum fields:

- `contact_consent_status`: `unknown`, `requested`, `granted`, `denied`, `revoked`.
- `consent_granted_at`
- `consent_source`
- `allowed_contact_fields`
- `private_contact`, only when allowed.

Project rule:

- The system should not store phone, WeChat, or enterprise WeChat information unless `contact_consent_status=granted`.
- Group invitation status should be tracked separately from consent status.

### 8. Attachments And Resume Files

Needed endpoints:

- Download resume attachment if authorized.
- Download chat attachment if supported.

Required information:

- Temporary URL expiration.
- Allowed storage duration.
- File type and size limits.
- Whether text extraction and AI parsing are permitted.

### 9. Error Codes And Limits

Required documentation:

- Full error code list.
- Authentication errors.
- Permission errors.
- Candidate privacy errors.
- Message rate limit errors.
- Duplicate message/idempotency behavior.
- Account risk control errors.
- Daily/monthly quota rules.

### 10. Audit And Compliance

Needed information:

- Whether every API action must be attributable to a recruiter account.
- Whether BOSS requires message content audit before send.
- Whether AI-generated messages need labels or disclosure.
- Data retention requirements.
- Candidate deletion or privacy request handling.
- Logs BOSS expects us to keep.

## Recommended Project-Side Data Additions

To support direct BOSS integration, add these fields later:

### Recruitment Requirement

- `boss_job_id`
- `boss_recruiter_id`
- `sync_status`
- `last_synced_at`

### Recruitment Candidate

- `boss_candidate_id`
- `boss_conversation_id`
- `source_url`
- `last_active_at`
- `privacy_level`
- `contact_consent_status`
- `contact_consent_at`
- `sync_status`
- `last_synced_at`

### Message Sync

Add a dedicated BOSS message table or extend messages with:

- `boss_message_id`
- `boss_conversation_id`
- `client_message_id`
- `send_status`
- `failure_reason`

## Minimum Acceptance Test

Before enabling production use, the integration should pass:

1. Connect sandbox account and refresh token successfully.
2. Pull active BOSS jobs into recruitment requirements.
3. Search candidates for one requirement.
4. Import candidates without duplicates.
5. Generate AI match score and draft message.
6. Send one human-approved message through BOSS API.
7. Receive candidate reply by webhook or polling.
8. Request contact consent through compliant message flow.
9. Store private contact only after consent is granted.
10. Record all API actions in project logs.

## Questions To Send To BOSS

1. Do you provide an official API for enterprise recruitment system integration?
2. Can we search candidates by job, city, skill, and active time?
3. Can candidate profiles or resume text be stored in our system? What is the retention limit?
4. Can messages be sent by API? Are AI-generated drafts allowed if a human confirms before sending?
5. Do you provide webhooks for replies and message status?
6. How do you expose candidate consent for phone, WeChat, or enterprise WeChat exchange?
7. What are the rate limits and anti-spam rules?
8. Do API actions need to bind to a specific recruiter account?
9. Is there a sandbox environment?
10. What compliance text, labels, or audit logs are required for AI-assisted recruiting?
