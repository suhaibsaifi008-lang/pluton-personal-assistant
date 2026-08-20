# PLUTON V2 — OPEN-SOURCE ECOSYSTEM COMPREHENSIVE REUSE MATRIX

---

## 1. Executive Summary

Milestone 0.5 expands the third-party ecosystem evaluation across **19 specialized technical domains** to maximize development velocity, minimize architectural risk, and prevent Pluton from rebuilding mature, battle-tested solutions.

Every subsystem is evaluated against four strict criteria:
1. **Permissive Licensing** (MIT, Apache 2.0, BSD-3, or cleanly isolated LGPL/API).
2. **Native Windows Compatibility & Performance** (Sub-millisecond or low-latency async).
3. **Architectural Alignment** (Decoupled, typed interfaces with zero monolithic framework lock-in).
4. **Maintenance & Community Activity** (Active commit history, verified issues, proven real-world stability).

---

## 2. Comprehensive 19-Category Ecosystem Matrix

| Category ID | Subsystem Domain | Candidate 1 (Preferred) | Candidate 2 (Runner-Up) | Candidate 3 (Alternative) | Evaluated Alternatives |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **CAT-01** | **Windows Computer Control** | **Microsoft UFO / UFO²** (MIT) | **Agent-S / OSWorld ACI** (MIT) | **Windows-Use** (MIT) | `pywinauto`, `uiautomation`, Microsoft CUA Skill |
| **CAT-02** | **Browser Automation** | **Browser Use** (MIT) | **Playwright-Python** (Apache 2.0) | **Stagehand** (MIT) | `open-browser-use`, `Skyvern`, `Rustwright` |
| **CAT-03** | **Agent Orchestration** | **PydanticAI** (MIT) | **OpenHands Engine** (MIT) | **LangGraph** (MIT) | `smolagents`, `AutoGen`, `CrewAI` |
| **CAT-04** | **Personal Assistant Arch** | **PersonalJarvis Patterns** (MIT) | **Letta Stateful Harness** (Apache 2.0) | **Open-Assistant Core** (Apache 2.0) | `DAWN/OASIS`, `Jarvis-OS` |
| **CAT-05** | **Speech-to-Text (STT)** | **Faster-Whisper** (MIT) | **Whisper.cpp** (MIT) | **Deepgram SDK** (Commercial/Cloud) | `Vosk`, OpenAI Whisper (PyTorch) |
| **CAT-06** | **Text-to-Speech (TTS)** | **Kokoro-82M** (Apache 2.0) | **Edge-TTS** (Apache 2.0) | **Piper TTS** (MIT/GPL) | `Sherpa-ONNX`, `Coqui TTS` |
| **CAT-07** | **Wake Word / VAD** | **Silero VAD** (MIT) | **openWakeWord** (Apache 2.0 / CC) | **WebRTC VAD** (BSD-3) | `Porcupine` (Proprietary/Commercial) |
| **CAT-08** | **Memory & Context Graph** | **Graphiti** (Apache 2.0) | **Mem0** (Apache 2.0) | **SQLite-vec** (MIT) | `ChromaDB`, `Qdrant`, `LanceDB`, `Letta` |
| **CAT-09** | **Web Search & Extraction** | **Crawl4AI** (Apache 2.0) | **SearXNG API** (AGPL/API) | **Tavily API** (Commercial SDK) | `Trafilatura`, `Exa`, `Firecrawl` |
| **CAT-10** | **Document Intelligence** | **Docling** (MIT) | **PyMuPDF** (AGPL/Commercial) | **Marker** (GPL-3.0) | `Unstructured`, `pdfplumber`, `Tesseract` |
| **CAT-11** | **Automation & Scheduling** | **APScheduler 3/4** (MIT) | **Temporal Python SDK** (MIT) | **Windows Task Scheduler API** (Native) | `Prefect`, `Celery`, `n8n` |
| **CAT-12** | **Skills & Tool Registries** | **Model Context Protocol (MCP)** (MIT) | **OpenAI Tool Schema** (Standard) | **Semantic Kernel Skills** (MIT) | `LangChain Tools`, `CrewAI Tools` |
| **CAT-13** | **Model Routing & Local LLM** | **LiteLLM** (MIT) | **Ollama Local Engine** (MIT) | **vLLM / llama.cpp** (Apache 2.0 / MIT) | `Fast-Route`, `vLLM` |
| **CAT-14** | **Vision / Screen Grounding** | **OmniParser v2** (MIT) | **UI-TARS** (Apache 2.0) | **Florence-2** (MIT) | `Show-UI`, `SeeClick`, `Qwen2-VL` |
| **CAT-15** | **Observability & Tracing** | **Langfuse** (MIT) | **OpenTelemetry Python** (Apache 2.0) | **Phoenix (Arize)** (Apache 2.0) | `Logfire`, `Weights & Biases` |
| **CAT-16** | **Evaluation & Benchmarks** | **OSWorld / WinAgentArena** (MIT) | **BrowserGym** (MIT) | **WebArena** (Apache 2.0) | `AgentBench`, `WorkArena` |
| **CAT-17** | **Security & Sandboxing** | **Windows Job Objects (pywin32)** (PSF) | **AppContainer Isolation** (Native) | **Docker/WSL2 Sandbox** (Apache 2.0) | `gVisor`, `Firejail` |
| **CAT-18** | **Git / Code Intelligence** | **Aider Core / RepoMap** (Apache 2.0) | **OpenHands Workspace** (MIT) | **Continue Core** (Apache 2.0) | `Cline`, `Roo-Code` |
| **CAT-19** | **Connectors & Personal Data** | **MCP Prebuilt Connectors** (MIT) | **Composio Core** (Apache 2.0) | **Google Workspace Direct API** (Apache 2.0)| `Nango`, `Zapier NLA` |