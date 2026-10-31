# n8n workflows

Two workflows share the same Planner → Critic → Revise core:

| File | Workflow | Purpose |
|---|---|---|
| `travel_planner_evaluation.json` | Travel Planner Evaluation | Upload a CSV of test trips, download a CSV of plans to grade |
| `trip_planner_api.json` | Trip Planner API | Webhook in from the Wayfare page, formatted plan back |

To import: in n8n, choose **Import from File**, then select your own OpenAI credential on every model node. Exports contain credential names only, never API keys.
