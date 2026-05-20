# Demo Script

1. Open frontend at `http://localhost:5178`
2. Use token `demo-votenow` to load demo survey
3. Fill answers for all mandatory question types
4. Submit response and confirm live updates in dashboard
5. Trigger `POST /exports/SURVEY-DEMO/excel`
6. Check export task status via `GET /exports/tasks/{task_id}`
7. Show generated files list via `GET /exports/files`
