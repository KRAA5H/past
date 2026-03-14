# CHRONOS

Gemini-powered historical scene generation and live voice interaction prototype.

Chronos lets a user type a historical prompt, generate a scene, render it in 3D, and optionally stream live voice to Gemini through the backend WebSocket.

## Table of Contents

1. Project Snapshot
2. Current Product Flow
3. Features
4. Architecture
5. Repository Structure
6. Backend API
7. Data Models
8. Local Setup
9. Run Instructions
10. Demo Flow
11. What Is Already Done
12. What Still Needs Building
13. Testing
14. Notes

## Project Snapshot

- Frontend: React + TypeScript + Vite + React Three Fiber
- Backend: FastAPI + google-genai + Pydantic v2 + SQLModel
- Scene generation supports two paths:
	- Legacy SceneState flow (currently used by frontend)
	- Structured ScenePlan JSON flow with validation, retry, and fallback
- Live voice path is wired over WebSocket with Gemini Live session bridging

## Current Product Flow

Implemented flow today:

1. User enters prompt in frontend.
2. Frontend sends scene_request over WebSocket.
3. Backend calls ScenePlanner.plan_scene and returns scene_update.
4. Frontend renders NPCs and objects from SceneState.
5. User can toggle microphone streaming.
6. Backend forwards audio and text to Gemini Live and returns transcripts and audio output.

Planned flow (not fully implemented yet):

Idea -> scene description -> structured JSON -> create render -> explore render -> press key to interact with NPC -> cutscene -> voice conversation with selected NPC -> leave -> exit scene.

## Features

### Implemented

- Prompt-based historical scene generation
- Real-time scene updates over WebSocket
- 3D rendering with dynamic NPC and object placement
- Live voice streaming pipeline (mic capture to backend, audio/text back to frontend)
- Structured ScenePlan backend route with strict schema validation
- Retry-on-validation-failure, then hardcoded Apollo 11 fallback
- Unit tests for models, planner logic, scene plan validation, and live session wrapper

### In Progress / Planned

- Frontend rendering from ScenePlan (instead of SceneState)
- Player exploration movement (WASD + bounds)
- Interaction prompt and key handling
- NPC-targeted cutscene transitions
- Character-specific live voice personas
- Runtime tool event channel (lighting, sound, highlight, spawn)

## Architecture

High-level architecture diagram:

		flowchart LR
			U[User] --> F[Frontend\nReact + R3F]
			F -->|WS scene_request| B[Backend FastAPI]
			B -->|Legacy planning| P1[ScenePlanner.plan_scene]
			B -->|Structured planning| P2[ScenePlanner.generate_scene_plan]
			P1 --> G1[Gemini Text Model\nFunction Calling]
			P2 --> G1
			B -->|WS text_input/audio_chunk| L[GeminiLiveSession]
			L --> G2[Gemini Live Model]
			G2 --> L
			L -->|transcript/audio_output| B
			B -->|WS scene_update/transcript/audio_output| F

Notes:

- The frontend currently consumes SceneState from the legacy flow.
- Structured ScenePlan generation exists in backend HTTP endpoints but is not yet connected to frontend rendering.

## Repository Structure

		past/
			backend/
				main.py
				scene_planner.py
				models.py
				gemini_live.py
				requirements.txt
				tests/
			frontend/
				src/
					App.tsx
					Scene.tsx
					useChronos.ts
					AudioManager.ts
				package.json

## Backend API

Current routes:

- GET /health
- POST /api/scene
	- Legacy generation path, returns SceneState
- GET /api/scene/{session_id}
	- Returns cached SceneState
- POST /api/scene/plan
	- Structured generation path, returns ScenePlan
- GET /api/scene/plan/{plan_id}
	- Returns cached ScenePlan
- WS /ws/{session_id}
	- Bidirectional WebSocket for scene requests + live text/audio streaming

WebSocket message types:

- Client to server:
	- scene_request
	- text_input
	- audio_chunk
- Server to client:
	- scene_update
	- transcript
	- audio_output
	- status
	- error

## Data Models

### Legacy runtime model

- SceneState
	- session_id
	- description
	- npcs
	- objects
	- ambient_sound
	- lighting

### Structured planning model

- ScenePlan
	- scene_id
	- event_name
	- dramatic_moment
	- room
	- lights (max 3)
	- props (max 6)
	- characters (max 3, exactly one primary)
	- ambient_sounds (max 2)
	- intro_narration (max 2 sentences)
	- camera_start (y must be 1.6)

Validation behavior:

1. Generate JSON from Gemini.
2. Validate against ScenePlan.
3. Retry once with validation errors.
4. If still invalid, return fallback Apollo 11 scene.

## Local Setup

Prerequisites:

- Python 3.11+
- Node.js 18+
- npm
- Gemini API key

Environment:

1. Create a file named .env in project root.
2. Add:

		GEMINI_API_KEY=your_key_here
		FRONTEND_ORIGIN=http://localhost:5173

Backend install:

		cd backend
		python -m venv .venv
		.venv\Scripts\activate
		pip install -r requirements.txt

Frontend install:

		cd frontend
		npm install

## Run Instructions

Start backend:

		cd backend
		.venv\Scripts\activate
		python main.py

Or with uvicorn:

		cd backend
		.venv\Scripts\activate
		uvicorn main:app --reload --host 0.0.0.0 --port 8000

Start frontend:

		cd frontend
		npm run dev

Open app:

		http://localhost:5173

## Demo Flow

Suggested demo script for current implementation:

1. Enter prompt such as:
	 Apollo 11 Mission Control, T-5 minutes to touchdown.
2. Click Generate.
3. Show scene update and NPC/object rendering.
4. Click Speak and ask a historical question.
5. Show transcript updates and returned audio output.
6. Explain that structured ScenePlan endpoint is implemented and can be connected next for fully data-driven scene schema rendering.

## What Is Already Done

- ScenePlanner legacy function-calling pipeline implemented.
- ScenePlanner structured JSON pipeline implemented.
- ScenePlan schema, validators, and error reporting implemented.
- Retry and fallback strategy implemented.
- FastAPI endpoints for both legacy and structured scene generation implemented.
- WebSocket handling for scene updates and live text/audio bridge implemented.
- Frontend WebSocket hook and real-time state update handling implemented.
- Frontend mic capture and PCM streaming implemented.
- Unit tests covering core backend modules implemented.

## What Still Needs Building

Frontend and interaction:

- Consume ScenePlan in frontend rendering pipeline.
- Room geometry from room dimensions.
- Scene lights from lights array.
- Primitive prop rendering from props with interactable behaviors.
- Character rendering from characters and portrait pipeline.
- Intro narration UI/audio flow.
- WASD and camera bounds movement system.
- Proximity + key interaction system.
- Cutscene camera transition in and out.
- Exit flow from conversation back to exploration.

Live NPC behavior:

- Character-specific live sessions using selected character persona_summary.
- Character selection handshake in WebSocket protocol.
- Runtime tool event path (tool messages from backend to frontend).

Persistence and productization:

- Durable storage for sessions, scenes, transcripts, and interaction events.
- Clear session lifecycle API for create, fetch, resume, close.
- README screenshots and short demo GIF/video.

## Testing

Run backend tests:

		cd backend
		.venv\Scripts\activate
		pytest -v

Focused test examples:

		pytest tests/test_scene_plan.py -v
		pytest tests/test_scene_planner.py -v
		pytest tests/test_gemini_live.py -v

## Notes

- Backend includes an in-memory store for active scene states and scene plans.
- Backend also initializes SQLModel tables, but current API flow primarily uses in-memory dictionaries for generated scene retrieval.
- Frontend currently uses WebSocket-first flow and does not yet call structured scene HTTP endpoints.

What Chronos Is Right Now
Chronos is a Gemini-powered historical scene prototype with:

Backend scene generation in two modes:
Legacy function-calling flow that outputs SceneState
New structured JSON flow that outputs validated ScenePlan
Frontend 3D rendering of legacy SceneState over WebSocket
Realtime Gemini Live voice/text streaming over WebSocket
Current UX is:
Idea -> text prompt -> scene update rendered -> optional live voice chat

It is not yet the full cutscene + NPC-targeted interaction loop.

Current Tech Stack
Frontend
React + TypeScript + Vite
@react-three/fiber
@react-three/drei
Native WebSocket
Web Audio API + getUserMedia for PCM mic capture/playback
Backend
Python 3.11+
FastAPI + uvicorn
google-genai SDK
Pydantic v2
SQLModel + SQLite setup utilities
python-dotenv
Gemini Models Currently Used in Code
Text planning model default: gemini-3.1-flash-lite-preview
Live voice model default: gemini-2.5-flash-native-audio-preview-12-2025
Repo Structure (Current)
main.py
scene_planner.py
models.py
gemini_live.py
App.tsx
Scene.tsx
useChronos.ts
AudioManager.ts
Files mentioned in earlier planning docs like FloatControls.tsx, useInteraction.ts, and CameraRig.tsx do not exist yet.

Scene Generation Pipeline (What Is Actually Implemented)
Path A: Legacy runtime path used by frontend today
Frontend sends WebSocket message type scene_request
Backend WebSocket handler calls ScenePlanner.plan_scene(prompt, session_id)
plan_scene uses Gemini function-calling tools:
set_scene_description
place_npc
place_object
clear_scene
Backend returns scene_update with SceneState
Frontend renders NPC capsules and box objects from SceneState
Path B: Structured JSON path implemented on backend, not wired to frontend
Client calls POST /api/scene/plan
Backend runs ScenePlanner.generate_scene_plan(user_input)
Gemini called in JSON mode
Pydantic ScenePlan validation runs
On failure, retry once with appended validation errors
On second failure, fallback Apollo 11 ScenePlan is returned
ScenePlan is stored in memory and retrievable by scene_id
Current Backend API (Code Truth)
GET /health
POST /api/scene -> returns SceneState (legacy flow)
GET /api/scene/{session_id} -> returns stored SceneState
POST /api/scene/plan -> returns ScenePlan (structured JSON flow)
GET /api/scene/plan/{plan_id} -> returns stored ScenePlan
WS /ws/{session_id} -> JSON WebSocket messages for:
scene_request
text_input
audio_chunk
scene_update
transcript
audio_output
status
error
There is no /sessions endpoint yet and no character query parameter on WebSocket.

Frontend Rendering State (Current)
Frontend consumes SceneState, not ScenePlan
Scene has:
Orbit camera controls
Ground plane
Simple NPC meshes + labels + optional dialogue bubble
Simple object meshes + labels
Prompt box sends scene requests
Speak/Stop toggles global microphone streaming to backend
Transcript and status are shown in HUD
There is no data-driven rendering yet for ScenePlan room/lights/props/characters/camera_start/intro_narration.

Cutscene + NPC Voice Flow (Current vs Planned)
Current:

Voice works as a global session chat channel
Not tied to selected NPC
No interaction key or proximity trigger
No cutscene transition camera
No enter/exit interaction mode state machine
Planned behavior from concept is still pending implementation.

What Is Already Done
Structured ScenePlan schema with strict constraints and validators:
shape enums
max counts
bounds checks
exactly one primary character
narration and word limits
ScenePlanner.generate_scene_plan with retry + fallback pipeline
Legacy ScenePlanner.plan_scene with function-call tool application
FastAPI routes for both legacy and structured generation
WebSocket bridge for Gemini Live audio/text
Frontend WebSocket integration with scene updates and transcript/audio playback
Frontend microphone capture and PCM streaming
Unit tests for:
models and validators
scene planner legacy behavior
structured scene-plan pipeline
GeminiLiveSession behavior

What Still Needs Building
Frontend migration from SceneState rendering to ScenePlan rendering
Character portrait image generation pipeline and URL injection
Intro narration playback/UX
WASD movement and room-bounds clamping
Interaction system:
hover/proximity
press E actions
per-prop interact modes
Primary NPC interaction flow:
select NPC
enter cutscene camera rig
disable movement during cutscene
Character-specific Gemini Live sessions using persona_summary
Runtime tool-call control channel from Live model to frontend (lighting, sound, highlight, spawn)
Exit cutscene and return-to-explore transition
Persistence for sessions/scenes/transcripts beyond in-memory dictionaries
API surface alignment if you want the /sessions contract described in your concept doc