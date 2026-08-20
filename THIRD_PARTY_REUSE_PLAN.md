# PLUTON V2 — THIRD-PARTY OPEN SOURCE REUSE & PROVENANCE PLAN

---

## 1. Executive Summary

To accelerate Pluton development while maintaining strict architectural sovereignty, security, and license compliance, this document establishes the authoritative provenance, licensing, and integration policy for all third-party open-source candidate projects evaluated across 19 technical domains.

Every third-party component is audited for:
- **Permissive Licensing:** MIT, Apache 2.0, BSD-3, PSF, or cleanly isolated network/API boundaries.
- **Windows OS Native Integration:** High-performance async compatibility on Windows 10/11.
- **Architectural Fit:** Minimal dependency footprint with zero monolithic framework lock-in.
- **Strict Provenance & Attribution:** Complete compliance with open-source copyright notices.

---

## 2. Master Open-Source Provenance & Licensing Matrix

| Project Name | Upstream Repository | License | Integration Method | Provenance & Attribution Requirements |
| :--- | :--- | :---: | :--- | :--- |
| **Microsoft UFO / UFO²** | `microsoft/UFO` | **MIT** | Adapt UIA tree traversal and control binding patterns into `backend/app/tools/uia_engine.py`. | Retain Microsoft MIT copyright notice and license header in adapted modules. |
| **Browser Use** | `browser-use/browser-use` | **MIT** | Adapt CDP session attachment and DOM coordinate extraction into `backend/app/subsystems/computer/browser_engine.py`. | Retain MIT license attribution in browser engine module. |
| **Playwright-Python** | `microsoft/playwright-python` | **Apache 2.0** | Direct dependency for browser automation and CDP debugging connections. | Standard Apache 2.0 package attribution. |
| **PydanticAI** | `pydantic/pydantic-ai` | **MIT** | Adopt structured output validation and dependency injection patterns into `backend/app/core/`. | Retain MIT license header. |
| **Faster-Whisper** | `SYSTRAN/faster-whisper` | **MIT** | Direct dependency for local, high-speed CTranslate2 Speech-to-Text in `backend/app/voice/stt_engine.py`. | Standard pip package attribution. |
| **Kokoro-82M** | `hexgrad/kokoro` | **Apache 2.0** | Direct dependency / ONNX model runner for lightweight local neural TTS in `backend/app/voice/tts_engine.py`. | Retain Apache 2.0 license notice and model weights attribution. |
| **Edge-TTS** | `rany2/edge-tts` | **Apache 2.0** | Direct dependency for zero-configuration streaming cloud TTS fallback. | Standard package attribution. |
| **Silero VAD** | `snakers4/silero-vad` | **MIT** | Direct dependency via ONNX Runtime for sub-millisecond voice activity detection. | Retain MIT license header. |
| **openWakeWord** | `dscripka/openwakeword` | **Apache 2.0** | Direct dependency for local wake-word trigger detection in `backend/app/voice/wakeword.py`. | Apache 2.0 code attribution; models used under CC BY-NC-SA 4.0. |
| **Graphiti** | `getzep/graphiti` | **Apache 2.0** | Adapt temporal knowledge graph engine for evolving memory in `backend/app/memory/memory_manager.py`. | Retain Apache 2.0 notice. |
| **SQLite-vec** | `asg017/sqlite-vec` | **MIT** | Direct C extension dependency for zero-dependency vector search in SQLite. | Retain MIT copyright notice. |
| **Crawl4AI** | `unclecode/crawl4ai` | **Apache 2.0** | Direct dependency for asynchronous, LLM-optimized web extraction in `backend/app/subsystems/web/`. | Standard Apache 2.0 package attribution. |
| **Docling** | `DS4SD/docling` | **MIT** | Direct dependency for unified PDF, Office, and table extraction in `backend/app/subsystems/document/`. | Retain MIT license header. |
| **APScheduler** | `agronholm/apscheduler` | **MIT** | Direct dependency for asyncio task scheduling and persistent cron triggers in `backend/app/automation/`. | Standard MIT package attribution. |
| **Model Context Protocol (MCP)** | `modelcontextprotocol/python-sdk` | **MIT** | Direct dependency for modular client tool server integration in `backend/app/skills/mcp_adapter.py`. | Standard MIT package attribution. |
| **OmniParser v2** | `microsoft/OmniParser` | **MIT** | Adapt as visual UI grounding fallback worker in `backend/app/subsystems/computer/domains/vision.py`. | Retain Microsoft MIT copyright notice in visual grounding module. |
| **Langfuse** | `langfuse/langfuse-python` | **MIT** | Direct dependency for non-blocking agent step tracing and telemetry in `backend/app/core/telemetry.py`. | Standard MIT package attribution. |
| **OSWorld / WinAgentArena** | `xlang-ai/OSWorld` | **MIT** | Architectural reference and evaluation benchmark for desktop agent certification. | Research & benchmark attribution. |
| **Aider Core / RepoMap** | `paul-gauthier/aider` | **Apache 2.0** | Adapt repository mapping and AST code context extraction for future coding workflows. | Retain Apache 2.0 license notice. |

---

## 3. Strict Architectural Boundary & Anti-Patterns

1. **No Monolithic Framework Lock-In:** Monolithic frameworks (LangChain, AutoGen, CrewAI) introduce hidden abstraction layers, uncontrolled telemetry overhead, and unmanageable prompt injection chains. Pluton maintains its own lightweight, sub-millisecond deterministic core.
2. **Authoritative Runtime Safety Isolation:** Third-party skills and MCP servers execute inside strict token-gated boundaries managed by Pluton's `ControlKernel` and `InputInterceptor`.