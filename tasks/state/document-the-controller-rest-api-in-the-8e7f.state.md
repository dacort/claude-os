### Accomplished
Added comprehensive REST API documentation to the README.md file, immediately after the Task Format section. The documentation includes:

- Clear explanation of the /api/v1/ endpoint structure
- Environment variable convention (CONTROLLER_URL)
- All five endpoint groups documented:
  - POST /api/v1/tasks (create task with required/optional fields)
  - GET /api/v1/tasks/{id} (task details)
  - GET /api/v1/tasks/{id}/logs (logs with query params for tail/follow)
  - GET /api/v1/status (system status with recent tasks parameter)
  - GET/POST/DELETE /api/v1/signal (signal endpoints)
- Working curl examples for each major operation
- Clean, concise style matching the existing README

Committed directly to main as a non-breaking documentation-only change.

### Current state
Task is complete. The README now documents the controller REST API with all necessary information for users to understand:
- What the API endpoints are and what they do
- Required vs optional parameters
- How to set CONTROLLER_URL
- Real-world usage examples via curl

The documentation source was read directly from `controller/cosapi/handler.go` to ensure accuracy against the actual implementation.

### First thing next time
No follow-up work needed. Task is complete and shipped.
