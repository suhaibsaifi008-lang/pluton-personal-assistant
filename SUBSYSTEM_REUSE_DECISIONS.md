# PLUTON V2 — SUBSYSTEM REUSE DECISIONS & ARCHITECTURAL SELECTIONS

---

## 1. WINDOWS COMPUTER CONTROL

- **Problem:** Native desktop automation requires discovering running windows, resolving UI elements across Win32/UIA/WinCOM, managing focus, and verifying action outcomes without hardcoding app names or coordinates.
- **Current Pluton Implementation:** `backend/app/subsystems/computer/domains/` (`app.py`, `window.py`, `keyboard.py`, `mouse.py`) with `TargetResolver` dynamic multi-source evidence scoring and `VerificationEngine`.
- **Candidates:**
  1. **Microsoft UFO / UFO²:** Dual-agent (HostAgent/AppAgent) architecture with deep Windows UIA tree traversal and WinCOM automation.
  2. **Agent-S / OSWorld ACI:** SOTA agent computer interface utilizing vision grounding and OSWorld benchmark integration.
  3. **Windows-Use:** Lightweight Python wrapper around pywinauto and accessibility trees.
- **Preferred:** **Microsoft UFO² (Patterns & UIA Tree Traversal Code)**
- **Why:** UFO is specifically engineered for Windows 10/11 UIA control tree inspection, control type mapping, and hierarchical App Worker orchestration. Adapting its UIA traversal algorithms directly strengthens Pluton's existing `uia_engine.py`.
- **License:** MIT License (Permissive).
- **Integration Method:** **Adapt Selected Modules** (Extract UIA tree traversal and control binding logic into `backend/app/tools/uia_engine.py` without adopting monolithic external framework dependencies).
- **Estimated Build-from-Scratch Time:** 4 weeks (160 hours).
- **Estimated Integration Time:** 4 days (32 hours).
- **Estimated Time Saved:** ~128 engineering hours (3.2 weeks).
- **Bugs Avoided:** Win32 `EnumWindows` z-order focus races, off-screen control coordinate miscalculations, UIA COM threading apartment deadlocks.
- **Risks:** LOW (Isolated Win32/UIA helper module; zero external runtime service dependencies).
- **Decision:** **ADAPT PATTERNS & CODE (Milestone 6)**.

---

## 2. BROWSER AUTOMATION & WEB RUNTIME

- **Problem:** Browser automation must support attaching to existing user browser sessions, multi-tab switching, omnibox navigation, DOM element coordinate extraction, and postcondition verification.
- **Current Pluton Implementation:** `NativeBrowserController` (`browser_engine.py`) using Windows UIA tab tree enumeration and hotkey navigation.
- **Candidates:**
  1. **Browser Use (`browser-use/browser-use`):** Modern 100k+ star agent framework utilizing Playwright/CDP for DOM extraction and multi-tab management.
  2. **Playwright-Python:** Standard headless/headed browser automation framework with robust CDP connections.
  3. **Stagehand (Browserbase):** AI-focused web automation framework with DOM caching and natural language actions.
- **Preferred:** **Browser Use + Playwright-Python**
- **Why:** Browser Use provides the gold-standard patterns for attaching to existing Chrome/Brave/Edge browser sessions over CDP (`--remote-debugging-port`), extracting interactive DOM element bounding boxes, and managing tab state without reloading.
- **License:** MIT License / Apache 2.0 (Permissive).
- **Integration Method:** **Adapt Patterns & Code** (Integrate CDP session attachment and DOM element coordinate extraction into `backend/app/subsystems/computer/browser_engine.py`).
- **Estimated Build-from-Scratch Time:** 3.5 weeks (140 hours).
- **Estimated Integration Time:** 3 days (24 hours).
- **Estimated Time Saved:** ~116 engineering hours (2.9 weeks).
- **Bugs Avoided:** CDP tab detachment crashes, stale DOM element reference errors, headless vs headed viewport scaling discrepancies.
- **Risks:** LOW (Wrapped cleanly behind Pluton's `BrowserEngine` interface).
- **Decision:** **ADAPT & INTEGRATE (Milestone 7)**.

---

## 3. AGENT ORCHESTRATION & STATE MACHINE

- **Problem:** The host agent needs structured typed outputs, validation, state management, asynchronous event streaming, and failure recovery without heavy black-box framework bloat.
- **Current Pluton Implementation:** `Universal AgentLoop` (`backend/app/core/agent_loop.py`) with Observe-Plan-Act-Verify-Replan lifecycle.
- **Candidates:**
  1. **PydanticAI:** Lightweight, production-grade agent framework built directly on Pydantic V2 with native dependency injection, type safety, and streaming.
  2. **OpenHands Engine:** Event-stream agent runtime designed for multi-turn software workflows.
  3. **LangGraph:** Graph-based state machine framework for agentic workflows.
- **Preferred:** **Pluton Native AgentLoop + PydanticAI Type Validation Patterns**
- **Why:** Pluton already possesses a proven sub-millisecond `AgentLoop` with strict verification and replanning. Adopting PydanticAI's lightweight typed schema validation patterns provides full type safety without introducing LangChain/LangGraph dependency lock-in.
- **License:** MIT License (Permissive).
- **Integration Method:** **Preserve Core Runtime & Adapt Pydantic Patterns**.
- **Estimated Build-from-Scratch Time:** 2.5 weeks (100 hours).
- **Estimated Integration Time:** 2 days (16 hours).
- **Estimated Time Saved:** ~84 engineering hours (2.1 weeks).
- **Bugs Avoided:** Uncontrolled cyclic graph execution loops, schema mismatch serialization errors, hidden telemetry latency overhead.
- **Risks:** LOW (Zero external dependency bloat).
- **Decision:** **PRESERVE PLUTON CORE + ADAPT PYDANTIC VALIDATION (Milestone 5)**.

---

## 4. VOICE SPEECH-TO-TEXT (STT)

- **Problem:** Jarvis-like voice interaction requires fast, offline-capable, high-accuracy speech transcription with minimal CPU/GPU overhead on Windows.
- **Current Pluton Implementation:** None (Voice I/O is a new capability planned for Milestone 9).
- **Candidates:**
  1. **Faster-Whisper (`SYSTRAN/faster-whisper`):** CTranslate2-accelerated Whisper implementation running 4x faster than standard Whisper with 50% less RAM/VRAM.
  2. **Whisper.cpp:** C/C++ port of OpenAI Whisper with high CPU efficiency.
  3. **Deepgram SDK:** Commercial high-speed cloud speech recognition API.
- **Preferred:** **Faster-Whisper (Primary Local) + Deepgram (Optional Cloud)**
- **Why:** Faster-Whisper provides instant local transcription on Windows (CPU or CUDA) with $< 300\text{ms}$ latency for short voice commands, zero cloud API costs, and full offline privacy.
- **License:** MIT License (Permissive).
- **Integration Method:** **Use Directly via Python Package** (Wrapped in `backend/app/voice/stt_engine.py`).
- **Estimated Build-from-Scratch Time:** 3 weeks (120 hours).
- **Estimated Integration Time:** 2 days (16 hours).
- **Estimated Time Saved:** ~104 engineering hours (2.6 weeks).
- **Bugs Avoided:** PyTorch VRAM leaks, audio stream buffer underruns, multi-threaded C API memory corruption.
- **Risks:** LOW (Standard pip package with pre-compiled CTranslate2 Windows wheels).
- **Decision:** **USE DIRECTLY (Milestone 9)**.

---

## 5. VOICE TEXT-TO-SPEECH (TTS)

- **Problem:** Conversational voice responses require ultra-low-latency, natural-sounding neural speech synthesis running locally on Windows with cloud fallback.
- **Current Pluton Implementation:** None (Voice I/O is planned for Milestone 9).
- **Candidates:**
  1. **Kokoro-82M (`hexgrad/kokoro`):** Apache 2.0 open-weight 82M neural TTS model delivering state-of-the-art natural voice quality in $< 150\text{ms}$ on CPU.
  2. **Edge-TTS (`rany2/edge-tts`):** Zero-configuration cloud streaming TTS with excellent voice quality.
  3. **Piper TTS (`rhasspy/piper`):** Fast local ONNX neural TTS engine.
- **Preferred:** **Kokoro-82M (Primary Local) + Edge-TTS (Cloud Fallback)**
- **Why:** Kokoro-82M is fully Apache 2.0 licensed, extremely lightweight (82M parameters), and produces superior natural speech quality compared to older local engines while generating audio in real-time on CPU.
- **License:** Apache License 2.0 (Permissive).
- **Integration Method:** **Use Directly / Adapt ONNX Model Runner** (Wrapped in `backend/app/voice/tts_engine.py`).
- **Estimated Build-from-Scratch Time:** 3 weeks (120 hours).
- **Estimated Integration Time:** 2 days (16 hours).
- **Estimated Time Saved:** ~104 engineering hours (2.6 weeks).
- **Bugs Avoided:** Windows audio device exclusive-mode locks, sample rate resampling artifacts, audio playback buffer clipping.
- **Risks:** LOW.
- **Decision:** **USE DIRECTLY / ADAPT (Milestone 9)**.

---

## 6. WAKE WORD & VOICE ACTIVITY DETECTION (VAD)

- **Problem:** Continuous audio listening requires high-precision voice activity detection to prevent processing background noise, plus local wake-word trigger detection.
- **Current Pluton Implementation:** None.
- **Candidates:**
  1. **Silero VAD (`snakers4/silero-vad`):** SOTA lightweight neural VAD model with $< 1\text{ms}$ processing latency per audio chunk.
  2. **openWakeWord (`dscripka/openwakeword`):** Apache 2.0 open-source wake-word detection engine with customizable models.
  3. **WebRTC VAD:** Traditional Gaussian Mixture Model energy-based VAD.
- **Preferred:** **Silero VAD (MIT) + openWakeWord (Apache 2.0)**
- **Why:** Silero VAD provides sub-millisecond speech chunk detection with near-zero false positive rates on non-speech noise, making it the industry standard for low-latency voice pipelines.
- **License:** MIT License (Silero VAD) / Apache 2.0 (openWakeWord).
- **Integration Method:** **Use Directly via ONNX Runtime**.
- **Estimated Build-from-Scratch Time:** 2.5 weeks (100 hours).
- **Estimated Integration Time:** 2 days (16 hours).
- **Estimated Time Saved:** ~84 engineering hours (2.1 weeks).
- **Bugs Avoided:** Infinite background noise recording loops, clipped start-of-speech audio buffers, high CPU utilization during idle listening.
- **Risks:** LOW.
- **Decision:** **USE DIRECTLY (Milestone 9)**.

---

## 7. HIERARCHICAL MEMORY & TEMPORAL CONTEXT GRAPH

- **Problem:** Personal assistant memory must track user preferences, episodic task history, and changing facts over time without suffering from stale or contradictory facts.
- **Current Pluton Implementation:** Basic SQLite conversation history in `backend/app/memory/`.
- **Candidates:**
  1. **Graphiti (`getzep/graphiti`):** Open-source temporal knowledge graph engine designed specifically for evolving dynamic agent memory and contradiction invalidation.
  2. **Mem0 (`mem0ai/mem0`):** Universal memory layer for personalized AI with user/agent ID partitioning.
  3. **SQLite-vec (`asg017/sqlite-vec`):** Lightweight, zero-dependency C vector search extension for SQLite.
- **Preferred:** **Graphiti (Temporal Graph) + SQLite-vec (Local Embedded Vector Storage)**
- **Why:** Graphiti solves the critical "stale fact" problem by maintaining an entity timeline with automated invalidation when user facts change (e.g. "I switched from VS Code to Cursor"). Combined with SQLite-vec, it runs 100% locally on Windows without requiring heavy external database services.
- **License:** Apache License 2.0 (Graphiti) / MIT (SQLite-vec).
- **Integration Method:** **Adapt & Integrate** into `backend/app/memory/memory_manager.py`.
- **Estimated Build-from-Scratch Time:** 4 weeks (160 hours).
- **Estimated Integration Time:** 4 days (32 hours).
- **Estimated Time Saved:** ~128 engineering hours (3.2 weeks).
- **Bugs Avoided:** Vector similarity hallucinating outdated user preferences, database connection lock contention in SQLite, runaway vector index sizes.
- **Risks:** LOW.
- **Decision:** **ADAPT & INTEGRATE (Milestone 10)**.

---

## 8. WEB EXTRACTION & WEB SEARCH

- **Problem:** Retrieving accurate web information requires extracting clean markdown from dynamic websites without blocking on heavy browser sessions or hitting rate limits.
- **Current Pluton Implementation:** Native browser search in `domains/browser.py`.
- **Candidates:**
  1. **Crawl4AI (`unclecode/crawl4ai`):** High-speed asynchronous web crawler/extractor designed specifically for LLM pipelines, producing structured markdown and metadata.
  2. **SearXNG:** Open-source, self-hosted metasearch engine combining results from 70+ search services.
  3. **Trafilatura:** Fast Python web text extraction library.
- **Preferred:** **Crawl4AI (Extraction) + Multi-Provider Search Adapter (SearXNG / DuckDuckGo / Tavily)**
- **Why:** Crawl4AI is Apache 2.0 licensed, highly optimized for LLMs, handles dynamic JavaScript rendering asynchronously, and strips noisy HTML/scripts into clean semantic markdown in $< 300\text{ms}$.
- **License:** Apache License 2.0 (Permissive).
- **Integration Method:** **Use Directly / Adapt** in `backend/app/subsystems/web/`.
- **Estimated Build-from-Scratch Time:** 2.5 weeks (100 hours).
- **Estimated Integration Time:** 2 days (16 hours).
- **Estimated Time Saved:** ~84 engineering hours (2.1 weeks).
- **Bugs Avoided:** Broken DOM scraping on dynamic React/Vue SPAs, bot detection Captcha lockouts, malformed HTML parsing exceptions.
- **Risks:** LOW.
- **Decision:** **USE DIRECTLY / ADAPT (Milestone 9 / 10)**.

---

## 9. DOCUMENT INTELLIGENCE & FILE PARSING

- **Problem:** Parsing PDFs, Word documents, Excel spreadsheets, and presentations into structured text, tables, and metadata for local retrieval.
- **Current Pluton Implementation:** Plaintext file reading in `domains/filesystem.py`.
- **Candidates:**
  1. **Docling (`DS4SD/docling`):** IBM-developed MIT-licensed document parser with advanced table extraction, multi-format parsing (PDF, DOCX, XLSX, PPTX), and markdown export.
  2. **PyMuPDF:** Fast PDF text extraction library.
  3. **Marker:** Deep learning-based PDF to markdown converter.
- **Preferred:** **Docling (MIT)**
- **Why:** Docling provides unified multi-format parsing (PDF, Office, HTML) with state-of-the-art table structure preservation and clean markdown output, all under a permissive MIT license.
- **License:** MIT License (Permissive).
- **Integration Method:** **Use Directly via Python SDK** in `backend/app/subsystems/document/`.
- **Estimated Build-from-Scratch Time:** 3 weeks (120 hours).
- **Estimated Integration Time:** 2 days (16 hours).
- **Estimated Time Saved:** ~104 engineering hours (2.6 weeks).
- **Bugs Avoided:** Scrambled multi-column PDF text ordering, lost Excel table borders, malformed Word document XML parsing errors.
- **Risks:** LOW.
- **Decision:** **USE DIRECTLY (Milestone 10)**.

---

## 10. AUTOMATION & TASK SCHEDULING

- **Problem:** Background tasks, reminders, and recurring cron jobs must run reliably without blocking the main conversational server or losing state upon application restarts.
- **Current Pluton Implementation:** None (Task automation is planned for Milestone 11).
- **Candidates:**
  1. **APScheduler 3/4:** Battle-tested Python asyncio scheduling library supporting one-shot timers, cron schedules, and persistent job stores (SQLite).
  2. **Temporal Python SDK:** Heavyweight distributed durable workflow execution system.
  3. **Windows Task Scheduler API:** Native Windows OS task scheduling via COM/Win32.
- **Preferred:** **APScheduler (Local AsyncIO & SQLite Store)**
- **Why:** APScheduler integrates seamlessly with FastAPI's `asyncio` event loop, supports standard 5-field cron expressions, persists scheduled jobs to SQLite, and requires zero external server daemons.
- **License:** MIT License (Permissive).
- **Integration Method:** **Use Directly via Python Package** in `backend/app/automation/scheduler.py`.
- **Estimated Build-from-Scratch Time:** 2 weeks (80 hours).
- **Estimated Integration Time:** 2 days (16 hours).
- **Estimated Time Saved:** ~64 engineering hours (1.6 weeks).
- **Bugs Avoided:** Timezone DST transition calculation bugs, missed cron triggers during system sleep/wake, event loop blocking timer deadlocks.
- **Risks:** LOW.
- **Decision:** **USE DIRECTLY (Milestone 11)**.

---

## 11. SKILLS & TOOL PROTOCOLS

- **Problem:** Extending Pluton with third-party tools, plugins, and custom integrations requires a standardized, secure capability discovery and execution protocol.
- **Current Pluton Implementation:** Hardened `CapabilityRegistry` schema provider (`capability_schema.py`).
- **Candidates:**
  1. **Model Context Protocol (MCP) Python SDK:** Open industry standard created by Anthropic for modular tool and resource servers.
  2. **Semantic Kernel Skills:** Microsoft's plugin architecture for AI agents.
  3. **OpenAI Function Calling Schemas:** Standard JSON schema tool specifications.
- **Preferred:** **Model Context Protocol (MCP) + Pluton Native Capability Registry**
- **Why:** MCP is rapidly becoming the universal ecosystem standard for AI tool integrations. Implementing an MCP client adapter allows Pluton to instantly leverage hundreds of prebuilt community tool servers (GitHub, Slack, Google Drive, Postgres) without writing custom API adapters.
- **License:** MIT License (Permissive).
- **Integration Method:** **Implement MCP Client Adapter** in `backend/app/skills/mcp_adapter.py`.
- **Estimated Build-from-Scratch Time:** 3 weeks (120 hours).
- **Estimated Integration Time:** 3 days (24 hours).
- **Estimated Time Saved:** ~96 engineering hours (2.4 weeks).
- **Bugs Avoided:** Custom API schema divergence, broken authentication credential handshakes, unisolated subprocess tool crashes.
- **Risks:** LOW.
- **Decision:** **ADAPT & INTEGRATE (Milestone 12)**.

---

## 12. VISION GROUNDING & SCREEN PARSING

- **Problem:** When native Windows UIA accessibility trees are absent (e.g. legacy software, custom games, canvas apps), the agent must visually ground UI elements to pixel coordinates.
- **Current Pluton Implementation:** `domains/vision.py` screen capture primitive.
- **Candidates:**
  1. **OmniParser v2 (`microsoft/OmniParser`):** Microsoft's screen parsing model that detects interactable UI icon/text bounding boxes and converts screenshots into structured action spaces.
  2. **UI-TARS:** ByteDance vision-language model trained for end-to-end GUI interaction.
  3. **Florence-2:** Lightweight Microsoft vision model for object detection and visual grounding.
- **Preferred:** **OmniParser v2 (Visual Grounding Fallback)**
- **Why:** OmniParser produces exact interactable bounding boxes with numeric IDs, allowing structured coordinate clicks without requiring expensive multimodal full-screen reasoning on every step.
- **License:** MIT License (Core Codebase).
- **Integration Method:** **Adapt as Visual Fallback Worker** in `backend/app/subsystems/computer/domains/vision.py`.
- **Estimated Build-from-Scratch Time:** 4 weeks (160 hours).
- **Estimated Integration Time:** 4 days (32 hours).
- **Estimated Time Saved:** ~128 engineering hours (3.2 weeks).
- **Bugs Avoided:** Coordinate scaling errors on High-DPI Windows displays, multi-monitor coordinate offsets, click misses on unlabelled icon buttons.
- **Risks:** MEDIUM (Requires ONNX/PyTorch vision runtime; should remain strictly a fallback when UIA fails).
- **Decision:** **ADAPT AS FALLBACK (Milestone 14)**.

---

## 13. OBSERVABILITY & TRACING

- **Problem:** Debugging complex multi-step agent trajectories, tool invocations, and latency bottlenecks requires granular, non-blocking telemetry.
- **Current Pluton Implementation:** Sub-millisecond latency profiler and shadow evaluation JSONL logger.
- **Candidates:**
  1. **Langfuse:** Open-source, self-hostable LLM engineering platform for tracing, evals, and prompt management.
  2. **OpenTelemetry Python:** Vendor-neutral industry standard telemetry framework.
  3. **Phoenix (Arize):** Open-source AI observability platform with trace visualization.
- **Preferred:** **Langfuse (Local/Cloud Tracing) + OpenTelemetry Standards**
- **Why:** Langfuse is MIT-licensed, lightweight, provides native async Python decorators, captures full agent step trajectories, and can run 100% locally via Docker.
- **License:** MIT License (Permissive).
- **Integration Method:** **Use Directly via Python SDK** in `backend/app/core/telemetry.py`.
- **Estimated Build-from-Scratch Time:** 2 weeks (80 hours).
- **Estimated Integration Time:** 1 day (8 hours).
- **Estimated Time Saved:** ~72 engineering hours (1.8 weeks).
- **Bugs Avoided:** Lost trace context across async tasks, unformatted prompt logging leaks, telemetry overhead slowing down interactive loops.
- **Risks:** LOW.
- **Decision:** **USE DIRECTLY (Milestone 15 / 16)**.