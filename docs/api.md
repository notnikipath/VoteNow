# API Overview

## Gateway

- `POST /auth/token`
- `POST /auth/verify`
- `GET /services/health`
- `GET /surveys/public/{public_token}`
- `POST /workflow/submit-response`
- `GET /dashboard/public/{public_token}`
- `POST /exports/{survey_id}/{file_format}`
- `GET /exports/tasks/{task_id}`

## Survey service

- `POST /surveys`
- `GET /surveys`
- `GET /surveys/{survey_id}`
- `GET /surveys/public/{public_token}`
- `PATCH /surveys/{survey_id}/state`
- `GET /surveys/{survey_id}/widget-snippet`

## Response service

- `POST /responses/save`
- `POST /responses/submit`
- `GET /responses/{survey_id}`
- `GET /responses/{survey_id}/count`

## Verification service

- `POST /verification/invites`
- `POST /verification/request-code`
- `POST /verification/confirm-code`
- `POST /verification/validate-voter`
- `POST /verification/check-duplicate`
- `POST /verification/register-duplicate`

## Analytics service

- `POST /analytics/live/update`
- `GET /analytics/{survey_id}/live`
- `GET /analytics/{survey_id}/charts`
- `GET /analytics/{survey_id}/tables`
- `GET /analytics/{survey_id}/forecast`

## Export service

- `POST /exports/{survey_id}/excel`
- `POST /exports/{survey_id}/pdf`
- `GET /exports/tasks/{task_id}`
- `GET /exports/files`

## Notification service

- `POST /notify/send`
- `GET /notify/history`
