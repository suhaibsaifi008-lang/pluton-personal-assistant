# PLUTON Core Reliability Gate Report

**Execution Timestamp:** 2026-08-19T15:13:52.276614+00:00  
**Total Evaluations Recorded:** 72  
**Overall Gate Status:** PASSED

---

## Executive Scorecard

| Gate Component | Required Target | Actual Score | Status |
|---|---|---|---|
| **CONVERSATION** | 20/20 (100%) | **20/20** | **PASS** |
| **CALCULATOR** | 10/10 (100%) | **10/10** | **PASS** |
| **NOTEPAD** | 10/10 (100%) | **10/10** | **PASS** |
| **FILE EXPLORER** | 10/10 (100%) | **10/10** | **PASS** |
| **CANCELLATION** | 10/10 (100%) | **10/10** | **PASS** |
| **IDEMPOTENCY** | 10/10 (100%) | **10/10** | **PASS** |
| **FALSE SUCCESS** | PASS | **PASS** | **PASS** |
| **RETRY TERMINATION** | PASS | **PASS** | **PASS** |

---

## Machine-Readable Evidence Log

```json
[
  {
    "test_name": "conversation_factual_question",
    "input": "What is the capital of France?",
    "expected": "requires_computer_agent=False (conversational/fast lane)",
    "actual": "domain=conversation, requires_computer=False, reason=conversational_inquiry",
    "pass": true,
    "failure_reason": null,
    "task_state": "ROUTED_CONVERSATIONAL",
    "verification_evidence": {
      "domain": "conversation",
      "confidence": 0.98,
      "reason": "conversational_inquiry"
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:47.362284+00:00"
  },
  {
    "test_name": "conversation_calculation",
    "input": "What is 25 * 48?",
    "expected": "requires_computer_agent=False (conversational/fast lane)",
    "actual": "domain=calculation, requires_computer=False, reason=deterministic_safe_math",
    "pass": true,
    "failure_reason": null,
    "task_state": "ROUTED_CONVERSATIONAL",
    "verification_evidence": {
      "domain": "calculation",
      "confidence": 1.0,
      "reason": "deterministic_safe_math"
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:47.363846+00:00"
  },
  {
    "test_name": "conversation_explanation",
    "input": "Explain how photosynthesis works in plants.",
    "expected": "requires_computer_agent=False (conversational/fast lane)",
    "actual": "domain=conversation, requires_computer=False, reason=conversational_inquiry",
    "pass": true,
    "failure_reason": null,
    "task_state": "ROUTED_CONVERSATIONAL",
    "verification_evidence": {
      "domain": "conversation",
      "confidence": 0.98,
      "reason": "conversational_inquiry"
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:47.363974+00:00"
  },
  {
    "test_name": "conversation_comparison",
    "input": "Compare the differences between Python and JavaScript.",
    "expected": "requires_computer_agent=False (conversational/fast lane)",
    "actual": "domain=conversation, requires_computer=False, reason=conversational_inquiry",
    "pass": true,
    "failure_reason": null,
    "task_state": "ROUTED_CONVERSATIONAL",
    "verification_evidence": {
      "domain": "conversation",
      "confidence": 0.98,
      "reason": "conversational_inquiry"
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:47.363997+00:00"
  },
  {
    "test_name": "conversation_follow_up",
    "input": "Can you explain more details about that?",
    "expected": "requires_computer_agent=False (conversational/fast lane)",
    "actual": "domain=conversation, requires_computer=False, reason=conversational_inquiry",
    "pass": true,
    "failure_reason": null,
    "task_state": "ROUTED_CONVERSATIONAL",
    "verification_evidence": {
      "domain": "conversation",
      "confidence": 0.98,
      "reason": "conversational_inquiry"
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:47.364016+00:00"
  },
  {
    "test_name": "conversation_ambiguous_question",
    "input": "What do you think about the future of AI?",
    "expected": "requires_computer_agent=False (conversational/fast lane)",
    "actual": "domain=conversation, requires_computer=False, reason=default_conversation_lane",
    "pass": true,
    "failure_reason": null,
    "task_state": "ROUTED_CONVERSATIONAL",
    "verification_evidence": {
      "domain": "conversation",
      "confidence": 0.9,
      "reason": "default_conversation_lane"
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:47.364033+00:00"
  },
  {
    "test_name": "conversation_short_question",
    "input": "Why is the sky blue?",
    "expected": "requires_computer_agent=False (conversational/fast lane)",
    "actual": "domain=conversation, requires_computer=False, reason=conversational_inquiry",
    "pass": true,
    "failure_reason": null,
    "task_state": "ROUTED_CONVERSATIONAL",
    "verification_evidence": {
      "domain": "conversation",
      "confidence": 0.98,
      "reason": "conversational_inquiry"
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:47.364050+00:00"
  },
  {
    "test_name": "conversation_long_question",
    "input": "Could you please provide a comprehensive breakdown of the core principles of quantum mechanics including wave-particle duality?",
    "expected": "requires_computer_agent=False (conversational/fast lane)",
    "actual": "domain=conversation, requires_computer=False, reason=default_conversation_lane",
    "pass": true,
    "failure_reason": null,
    "task_state": "ROUTED_CONVERSATIONAL",
    "verification_evidence": {
      "domain": "conversation",
      "confidence": 0.9,
      "reason": "default_conversation_lane"
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:47.364065+00:00"
  },
  {
    "test_name": "conversation_casual_conversation",
    "input": "Hello, how are you doing today?",
    "expected": "requires_computer_agent=False (conversational/fast lane)",
    "actual": "domain=conversation, requires_computer=False, reason=conversational_inquiry",
    "pass": true,
    "failure_reason": null,
    "task_state": "ROUTED_CONVERSATIONAL",
    "verification_evidence": {
      "domain": "conversation",
      "confidence": 0.98,
      "reason": "conversational_inquiry"
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:47.364085+00:00"
  },
  {
    "test_name": "conversation_no_tool_creative_writing",
    "input": "Write a short poem about coding at midnight.",
    "expected": "requires_computer_agent=False (conversational/fast lane)",
    "actual": "domain=conversation, requires_computer=False, reason=default_conversation_lane",
    "pass": true,
    "failure_reason": null,
    "task_state": "ROUTED_CONVERSATIONAL",
    "verification_evidence": {
      "domain": "conversation",
      "confidence": 0.9,
      "reason": "default_conversation_lane"
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:47.364100+00:00"
  },
  {
    "test_name": "conversation_tool_like_noun_inquiry",
    "input": "How does the operating system click event dispatch mechanism work under the hood?",
    "expected": "requires_computer_agent=False (conversational/fast lane)",
    "actual": "domain=conversation, requires_computer=False, reason=conversational_inquiry",
    "pass": true,
    "failure_reason": null,
    "task_state": "ROUTED_CONVERSATIONAL",
    "verification_evidence": {
      "domain": "conversation",
      "confidence": 0.98,
      "reason": "conversational_inquiry"
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:47.364117+00:00"
  },
  {
    "test_name": "conversation_app_name_in_inquiry",
    "input": "What is the history of Microsoft Calculator and when was it first released?",
    "expected": "requires_computer_agent=False (conversational/fast lane)",
    "actual": "domain=conversation, requires_computer=False, reason=conversational_inquiry",
    "pass": true,
    "failure_reason": null,
    "task_state": "ROUTED_CONVERSATIONAL",
    "verification_evidence": {
      "domain": "conversation",
      "confidence": 0.98,
      "reason": "conversational_inquiry"
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:47.364134+00:00"
  },
  {
    "test_name": "conversation_url_in_inquiry",
    "input": "Why do websites use https://example.com as a standard domain in documentation?",
    "expected": "requires_computer_agent=False (conversational/fast lane)",
    "actual": "domain=conversation, requires_computer=False, reason=conversational_inquiry",
    "pass": true,
    "failure_reason": null,
    "task_state": "ROUTED_CONVERSATIONAL",
    "verification_evidence": {
      "domain": "conversation",
      "confidence": 0.98,
      "reason": "conversational_inquiry"
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:47.364151+00:00"
  },
  {
    "test_name": "conversation_browser_term_inquiry",
    "input": "Compare Chrome browser and Brave browser features.",
    "expected": "requires_computer_agent=False (conversational/fast lane)",
    "actual": "domain=conversation, requires_computer=False, reason=conversational_inquiry",
    "pass": true,
    "failure_reason": null,
    "task_state": "ROUTED_CONVERSATIONAL",
    "verification_evidence": {
      "domain": "conversation",
      "confidence": 0.98,
      "reason": "conversational_inquiry"
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:47.364166+00:00"
  },
  {
    "test_name": "conversation_file_term_inquiry",
    "input": "What is the difference between a binary file and a text file?",
    "expected": "requires_computer_agent=False (conversational/fast lane)",
    "actual": "domain=conversation, requires_computer=False, reason=conversational_inquiry",
    "pass": true,
    "failure_reason": null,
    "task_state": "ROUTED_CONVERSATIONAL",
    "verification_evidence": {
      "domain": "conversation",
      "confidence": 0.98,
      "reason": "conversational_inquiry"
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:47.364181+00:00"
  },
  {
    "test_name": "conversation_terminal_term_inquiry",
    "input": "What is a terminal emulator in modern operating systems?",
    "expected": "requires_computer_agent=False (conversational/fast lane)",
    "actual": "domain=conversation, requires_computer=False, reason=conversational_inquiry",
    "pass": true,
    "failure_reason": null,
    "task_state": "ROUTED_CONVERSATIONAL",
    "verification_evidence": {
      "domain": "conversation",
      "confidence": 0.98,
      "reason": "conversational_inquiry"
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:47.364196+00:00"
  },
  {
    "test_name": "conversation_whitespace_padded_input",
    "input": "   Hello PLUTON!   ",
    "expected": "requires_computer_agent=False (conversational/fast lane)",
    "actual": "domain=conversation, requires_computer=False, reason=conversational_inquiry",
    "pass": true,
    "failure_reason": null,
    "task_state": "ROUTED_CONVERSATIONAL",
    "verification_evidence": {
      "domain": "conversation",
      "confidence": 0.98,
      "reason": "conversational_inquiry"
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:47.364211+00:00"
  },
  {
    "test_name": "conversation_punctuation_calculation",
    "input": "??? What is 10 + 20 ????",
    "expected": "requires_computer_agent=False (conversational/fast lane)",
    "actual": "domain=calculation, requires_computer=False, reason=deterministic_safe_math",
    "pass": true,
    "failure_reason": null,
    "task_state": "ROUTED_CONVERSATIONAL",
    "verification_evidence": {
      "domain": "calculation",
      "confidence": 1.0,
      "reason": "deterministic_safe_math"
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:47.364225+00:00"
  },
  {
    "test_name": "conversation_open_source_noun_inquiry",
    "input": "What is the open source definition according to OSI?",
    "expected": "requires_computer_agent=False (conversational/fast lane)",
    "actual": "domain=conversation, requires_computer=False, reason=conversational_inquiry",
    "pass": true,
    "failure_reason": null,
    "task_state": "ROUTED_CONVERSATIONAL",
    "verification_evidence": {
      "domain": "conversation",
      "confidence": 0.98,
      "reason": "conversational_inquiry"
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:47.364240+00:00"
  },
  {
    "test_name": "conversation_compiler_inquiry",
    "input": "Can you help me understand how compilers optimize code?",
    "expected": "requires_computer_agent=False (conversational/fast lane)",
    "actual": "domain=conversation, requires_computer=False, reason=default_conversation_lane",
    "pass": true,
    "failure_reason": null,
    "task_state": "ROUTED_CONVERSATIONAL",
    "verification_evidence": {
      "domain": "conversation",
      "confidence": 0.9,
      "reason": "default_conversation_lane"
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:47.364255+00:00"
  },
  {
    "test_name": "calculator_trial_1",
    "input": "Open Calculator",
    "expected": "Process running, window present, verified=True",
    "actual": "success=True, transition=EXISTING_INSTANCE_REUSED, hwnd=9242356, verified=True",
    "pass": true,
    "failure_reason": null,
    "task_state": "SUCCEEDED",
    "verification_evidence": {
      "hwnd": 9242356,
      "pid": 13384,
      "verified": true,
      "message": "Verified window 'Calculator' is open and active (HWND: 9242356)."
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:47.364310+00:00"
  },
  {
    "test_name": "calculator_trial_2",
    "input": "Open Calculator",
    "expected": "Process running, window present, verified=True",
    "actual": "success=True, transition=EXISTING_INSTANCE_REUSED, hwnd=9242356, verified=True",
    "pass": true,
    "failure_reason": null,
    "task_state": "SUCCEEDED",
    "verification_evidence": {
      "hwnd": 9242356,
      "pid": 13384,
      "verified": true,
      "message": "Verified window 'Calculator' is open and active (HWND: 9242356)."
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:47.379095+00:00"
  },
  {
    "test_name": "calculator_trial_3",
    "input": "Open Calculator",
    "expected": "Process running, window present, verified=True",
    "actual": "success=True, transition=EXISTING_INSTANCE_REUSED, hwnd=9242356, verified=True",
    "pass": true,
    "failure_reason": null,
    "task_state": "SUCCEEDED",
    "verification_evidence": {
      "hwnd": 9242356,
      "pid": 13384,
      "verified": true,
      "message": "Verified window 'Calculator' is open and active (HWND: 9242356)."
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:47.395010+00:00"
  },
  {
    "test_name": "calculator_trial_4",
    "input": "Open Calculator",
    "expected": "Process running, window present, verified=True",
    "actual": "success=True, transition=EXISTING_INSTANCE_REUSED, hwnd=9242356, verified=True",
    "pass": true,
    "failure_reason": null,
    "task_state": "SUCCEEDED",
    "verification_evidence": {
      "hwnd": 9242356,
      "pid": 13384,
      "verified": true,
      "message": "Verified window 'Calculator' is open and active (HWND: 9242356)."
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:47.403135+00:00"
  },
  {
    "test_name": "calculator_trial_5",
    "input": "Open Calculator",
    "expected": "Process running, window present, verified=True",
    "actual": "success=True, transition=EXISTING_INSTANCE_REUSED, hwnd=9242356, verified=True",
    "pass": true,
    "failure_reason": null,
    "task_state": "SUCCEEDED",
    "verification_evidence": {
      "hwnd": 9242356,
      "pid": 13384,
      "verified": true,
      "message": "Verified window 'Calculator' is open and active (HWND: 9242356)."
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:47.410943+00:00"
  },
  {
    "test_name": "calculator_trial_6",
    "input": "Open Calculator",
    "expected": "Process running, window present, verified=True",
    "actual": "success=True, transition=EXISTING_INSTANCE_REUSED, hwnd=9242356, verified=True",
    "pass": true,
    "failure_reason": null,
    "task_state": "SUCCEEDED",
    "verification_evidence": {
      "hwnd": 9242356,
      "pid": 13384,
      "verified": true,
      "message": "Verified window 'Calculator' is open and active (HWND: 9242356)."
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:47.418531+00:00"
  },
  {
    "test_name": "calculator_trial_7",
    "input": "Open Calculator",
    "expected": "Process running, window present, verified=True",
    "actual": "success=True, transition=EXISTING_INSTANCE_REUSED, hwnd=9242356, verified=True",
    "pass": true,
    "failure_reason": null,
    "task_state": "SUCCEEDED",
    "verification_evidence": {
      "hwnd": 9242356,
      "pid": 13384,
      "verified": true,
      "message": "Verified window 'Calculator' is open and active (HWND: 9242356)."
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:47.427002+00:00"
  },
  {
    "test_name": "calculator_trial_8",
    "input": "Open Calculator",
    "expected": "Process running, window present, verified=True",
    "actual": "success=True, transition=EXISTING_INSTANCE_REUSED, hwnd=9242356, verified=True",
    "pass": true,
    "failure_reason": null,
    "task_state": "SUCCEEDED",
    "verification_evidence": {
      "hwnd": 9242356,
      "pid": 13384,
      "verified": true,
      "message": "Verified window 'Calculator' is open and active (HWND: 9242356)."
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:47.434387+00:00"
  },
  {
    "test_name": "calculator_trial_9",
    "input": "Open Calculator",
    "expected": "Process running, window present, verified=True",
    "actual": "success=True, transition=EXISTING_INSTANCE_REUSED, hwnd=9242356, verified=True",
    "pass": true,
    "failure_reason": null,
    "task_state": "SUCCEEDED",
    "verification_evidence": {
      "hwnd": 9242356,
      "pid": 13384,
      "verified": true,
      "message": "Verified window 'Calculator' is open and active (HWND: 9242356)."
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:47.441685+00:00"
  },
  {
    "test_name": "calculator_trial_10",
    "input": "Open Calculator",
    "expected": "Process running, window present, verified=True",
    "actual": "success=True, transition=EXISTING_INSTANCE_REUSED, hwnd=9242356, verified=True",
    "pass": true,
    "failure_reason": null,
    "task_state": "SUCCEEDED",
    "verification_evidence": {
      "hwnd": 9242356,
      "pid": 13384,
      "verified": true,
      "message": "Verified window 'Calculator' is open and active (HWND: 9242356)."
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:47.448612+00:00"
  },
  {
    "test_name": "notepad_trial_1",
    "input": "Open Notepad",
    "expected": "Process running, window present, verified=True",
    "actual": "success=True, hwnd=71208, verified=True",
    "pass": true,
    "failure_reason": null,
    "task_state": "SUCCEEDED",
    "verification_evidence": {
      "hwnd": 71208,
      "pid": 20896,
      "verified": true,
      "message": "Verified window 'Untitled - Notepad' is open and active (HWND: 71208)."
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:47.456634+00:00"
  },
  {
    "test_name": "notepad_trial_2",
    "input": "Open Notepad",
    "expected": "Process running, window present, verified=True",
    "actual": "success=True, hwnd=71208, verified=True",
    "pass": true,
    "failure_reason": null,
    "task_state": "SUCCEEDED",
    "verification_evidence": {
      "hwnd": 71208,
      "pid": 20896,
      "verified": true,
      "message": "Verified window 'Untitled - Notepad' is open and active (HWND: 71208)."
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:47.466344+00:00"
  },
  {
    "test_name": "notepad_trial_3",
    "input": "Open Notepad",
    "expected": "Process running, window present, verified=True",
    "actual": "success=True, hwnd=71208, verified=True",
    "pass": true,
    "failure_reason": null,
    "task_state": "SUCCEEDED",
    "verification_evidence": {
      "hwnd": 71208,
      "pid": 20896,
      "verified": true,
      "message": "Verified window 'Untitled - Notepad' is open and active (HWND: 71208)."
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:47.484546+00:00"
  },
  {
    "test_name": "notepad_trial_4",
    "input": "Open Notepad",
    "expected": "Process running, window present, verified=True",
    "actual": "success=True, hwnd=71208, verified=True",
    "pass": true,
    "failure_reason": null,
    "task_state": "SUCCEEDED",
    "verification_evidence": {
      "hwnd": 71208,
      "pid": 20896,
      "verified": true,
      "message": "Verified window 'Untitled - Notepad' is open and active (HWND: 71208)."
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:47.492636+00:00"
  },
  {
    "test_name": "notepad_trial_5",
    "input": "Open Notepad",
    "expected": "Process running, window present, verified=True",
    "actual": "success=True, hwnd=71208, verified=True",
    "pass": true,
    "failure_reason": null,
    "task_state": "SUCCEEDED",
    "verification_evidence": {
      "hwnd": 71208,
      "pid": 20896,
      "verified": true,
      "message": "Verified window 'Untitled - Notepad' is open and active (HWND: 71208)."
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:47.500933+00:00"
  },
  {
    "test_name": "notepad_trial_6",
    "input": "Open Notepad",
    "expected": "Process running, window present, verified=True",
    "actual": "success=True, hwnd=71208, verified=True",
    "pass": true,
    "failure_reason": null,
    "task_state": "SUCCEEDED",
    "verification_evidence": {
      "hwnd": 71208,
      "pid": 20896,
      "verified": true,
      "message": "Verified window 'Untitled - Notepad' is open and active (HWND: 71208)."
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:47.509487+00:00"
  },
  {
    "test_name": "notepad_trial_7",
    "input": "Open Notepad",
    "expected": "Process running, window present, verified=True",
    "actual": "success=True, hwnd=71208, verified=True",
    "pass": true,
    "failure_reason": null,
    "task_state": "SUCCEEDED",
    "verification_evidence": {
      "hwnd": 71208,
      "pid": 20896,
      "verified": true,
      "message": "Verified window 'Untitled - Notepad' is open and active (HWND: 71208)."
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:47.517720+00:00"
  },
  {
    "test_name": "notepad_trial_8",
    "input": "Open Notepad",
    "expected": "Process running, window present, verified=True",
    "actual": "success=True, hwnd=71208, verified=True",
    "pass": true,
    "failure_reason": null,
    "task_state": "SUCCEEDED",
    "verification_evidence": {
      "hwnd": 71208,
      "pid": 20896,
      "verified": true,
      "message": "Verified window 'Untitled - Notepad' is open and active (HWND: 71208)."
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:47.525677+00:00"
  },
  {
    "test_name": "notepad_trial_9",
    "input": "Open Notepad",
    "expected": "Process running, window present, verified=True",
    "actual": "success=True, hwnd=71208, verified=True",
    "pass": true,
    "failure_reason": null,
    "task_state": "SUCCEEDED",
    "verification_evidence": {
      "hwnd": 71208,
      "pid": 20896,
      "verified": true,
      "message": "Verified window 'Untitled - Notepad' is open and active (HWND: 71208)."
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:47.533550+00:00"
  },
  {
    "test_name": "notepad_trial_10",
    "input": "Open Notepad",
    "expected": "Process running, window present, verified=True",
    "actual": "success=True, hwnd=71208, verified=True",
    "pass": true,
    "failure_reason": null,
    "task_state": "SUCCEEDED",
    "verification_evidence": {
      "hwnd": 71208,
      "pid": 20896,
      "verified": true,
      "message": "Verified window 'Untitled - Notepad' is open and active (HWND: 71208)."
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:47.541610+00:00"
  },
  {
    "test_name": "file_explorer_trial_1",
    "input": "Open File Explorer",
    "expected": "CabinetWClass/ExploreWClass window present, verified=True",
    "actual": "success=True, hwnd=984578, verified=True",
    "pass": true,
    "failure_reason": null,
    "task_state": "SUCCEEDED",
    "verification_evidence": {
      "hwnd": 984578,
      "pid": 6488,
      "verified": true,
      "message": "Verified window 'Downloads - File Explorer' is open and active (HWND: 460470)."
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:47.549264+00:00"
  },
  {
    "test_name": "file_explorer_trial_2",
    "input": "Open File Explorer",
    "expected": "CabinetWClass/ExploreWClass window present, verified=True",
    "actual": "success=True, hwnd=984578, verified=True",
    "pass": true,
    "failure_reason": null,
    "task_state": "SUCCEEDED",
    "verification_evidence": {
      "hwnd": 984578,
      "pid": 6488,
      "verified": true,
      "message": "Verified window 'Downloads - File Explorer' is open and active (HWND: 460470)."
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:47.567600+00:00"
  },
  {
    "test_name": "file_explorer_trial_3",
    "input": "Open File Explorer",
    "expected": "CabinetWClass/ExploreWClass window present, verified=True",
    "actual": "success=True, hwnd=984578, verified=True",
    "pass": true,
    "failure_reason": null,
    "task_state": "SUCCEEDED",
    "verification_evidence": {
      "hwnd": 984578,
      "pid": 6488,
      "verified": true,
      "message": "Verified window 'Downloads - File Explorer' is open and active (HWND: 460470)."
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:47.576589+00:00"
  },
  {
    "test_name": "file_explorer_trial_4",
    "input": "Open File Explorer",
    "expected": "CabinetWClass/ExploreWClass window present, verified=True",
    "actual": "success=True, hwnd=984578, verified=True",
    "pass": true,
    "failure_reason": null,
    "task_state": "SUCCEEDED",
    "verification_evidence": {
      "hwnd": 984578,
      "pid": 6488,
      "verified": true,
      "message": "Verified window 'Downloads - File Explorer' is open and active (HWND: 460470)."
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:47.585252+00:00"
  },
  {
    "test_name": "file_explorer_trial_5",
    "input": "Open File Explorer",
    "expected": "CabinetWClass/ExploreWClass window present, verified=True",
    "actual": "success=True, hwnd=984578, verified=True",
    "pass": true,
    "failure_reason": null,
    "task_state": "SUCCEEDED",
    "verification_evidence": {
      "hwnd": 984578,
      "pid": 6488,
      "verified": true,
      "message": "Verified window 'Downloads - File Explorer' is open and active (HWND: 460470)."
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:47.594257+00:00"
  },
  {
    "test_name": "file_explorer_trial_6",
    "input": "Open File Explorer",
    "expected": "CabinetWClass/ExploreWClass window present, verified=True",
    "actual": "success=True, hwnd=984578, verified=True",
    "pass": true,
    "failure_reason": null,
    "task_state": "SUCCEEDED",
    "verification_evidence": {
      "hwnd": 984578,
      "pid": 6488,
      "verified": true,
      "message": "Verified window 'Downloads - File Explorer' is open and active (HWND: 460470)."
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:47.602116+00:00"
  },
  {
    "test_name": "file_explorer_trial_7",
    "input": "Open File Explorer",
    "expected": "CabinetWClass/ExploreWClass window present, verified=True",
    "actual": "success=True, hwnd=984578, verified=True",
    "pass": true,
    "failure_reason": null,
    "task_state": "SUCCEEDED",
    "verification_evidence": {
      "hwnd": 984578,
      "pid": 6488,
      "verified": true,
      "message": "Verified window 'Downloads - File Explorer' is open and active (HWND: 460470)."
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:47.609882+00:00"
  },
  {
    "test_name": "file_explorer_trial_8",
    "input": "Open File Explorer",
    "expected": "CabinetWClass/ExploreWClass window present, verified=True",
    "actual": "success=True, hwnd=984578, verified=True",
    "pass": true,
    "failure_reason": null,
    "task_state": "SUCCEEDED",
    "verification_evidence": {
      "hwnd": 984578,
      "pid": 6488,
      "verified": true,
      "message": "Verified window 'Downloads - File Explorer' is open and active (HWND: 460470)."
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:47.617836+00:00"
  },
  {
    "test_name": "file_explorer_trial_9",
    "input": "Open File Explorer",
    "expected": "CabinetWClass/ExploreWClass window present, verified=True",
    "actual": "success=True, hwnd=984578, verified=True",
    "pass": true,
    "failure_reason": null,
    "task_state": "SUCCEEDED",
    "verification_evidence": {
      "hwnd": 984578,
      "pid": 6488,
      "verified": true,
      "message": "Verified window 'Downloads - File Explorer' is open and active (HWND: 460470)."
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:47.626998+00:00"
  },
  {
    "test_name": "file_explorer_trial_10",
    "input": "Open File Explorer",
    "expected": "CabinetWClass/ExploreWClass window present, verified=True",
    "actual": "success=True, hwnd=984578, verified=True",
    "pass": true,
    "failure_reason": null,
    "task_state": "SUCCEEDED",
    "verification_evidence": {
      "hwnd": 984578,
      "pid": 6488,
      "verified": true,
      "message": "Verified window 'Downloads - File Explorer' is open and active (HWND: 460470)."
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:47.635601+00:00"
  },
  {
    "test_name": "idempotency_calc_trial_1",
    "input": "Open Calculator (while already open)",
    "expected": "EXISTING_INSTANCE_REUSED, same HWND, 0 duplicate processes",
    "actual": "transition=EXISTING_INSTANCE_REUSED, hwnd=9242356",
    "pass": true,
    "failure_reason": null,
    "task_state": "SUCCEEDED",
    "verification_evidence": {
      "transition": "EXISTING_INSTANCE_REUSED",
      "hwnd": 9242356,
      "base_hwnd": 9242356
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:47.653795+00:00"
  },
  {
    "test_name": "idempotency_calc_trial_2",
    "input": "Open Calculator (while already open)",
    "expected": "EXISTING_INSTANCE_REUSED, same HWND, 0 duplicate processes",
    "actual": "transition=EXISTING_INSTANCE_REUSED, hwnd=9242356",
    "pass": true,
    "failure_reason": null,
    "task_state": "SUCCEEDED",
    "verification_evidence": {
      "transition": "EXISTING_INSTANCE_REUSED",
      "hwnd": 9242356,
      "base_hwnd": 9242356
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:47.672869+00:00"
  },
  {
    "test_name": "idempotency_calc_trial_3",
    "input": "Open Calculator (while already open)",
    "expected": "EXISTING_INSTANCE_REUSED, same HWND, 0 duplicate processes",
    "actual": "transition=EXISTING_INSTANCE_REUSED, hwnd=9242356",
    "pass": true,
    "failure_reason": null,
    "task_state": "SUCCEEDED",
    "verification_evidence": {
      "transition": "EXISTING_INSTANCE_REUSED",
      "hwnd": 9242356,
      "base_hwnd": 9242356
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:47.680529+00:00"
  },
  {
    "test_name": "idempotency_calc_trial_4",
    "input": "Open Calculator (while already open)",
    "expected": "EXISTING_INSTANCE_REUSED, same HWND, 0 duplicate processes",
    "actual": "transition=EXISTING_INSTANCE_REUSED, hwnd=9242356",
    "pass": true,
    "failure_reason": null,
    "task_state": "SUCCEEDED",
    "verification_evidence": {
      "transition": "EXISTING_INSTANCE_REUSED",
      "hwnd": 9242356,
      "base_hwnd": 9242356
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:47.688385+00:00"
  },
  {
    "test_name": "idempotency_calc_trial_5",
    "input": "Open Calculator (while already open)",
    "expected": "EXISTING_INSTANCE_REUSED, same HWND, 0 duplicate processes",
    "actual": "transition=EXISTING_INSTANCE_REUSED, hwnd=9242356",
    "pass": true,
    "failure_reason": null,
    "task_state": "SUCCEEDED",
    "verification_evidence": {
      "transition": "EXISTING_INSTANCE_REUSED",
      "hwnd": 9242356,
      "base_hwnd": 9242356
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:47.695844+00:00"
  },
  {
    "test_name": "idempotency_calc_trial_6",
    "input": "Open Calculator (while already open)",
    "expected": "EXISTING_INSTANCE_REUSED, same HWND, 0 duplicate processes",
    "actual": "transition=EXISTING_INSTANCE_REUSED, hwnd=9242356",
    "pass": true,
    "failure_reason": null,
    "task_state": "SUCCEEDED",
    "verification_evidence": {
      "transition": "EXISTING_INSTANCE_REUSED",
      "hwnd": 9242356,
      "base_hwnd": 9242356
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:47.703810+00:00"
  },
  {
    "test_name": "idempotency_calc_trial_7",
    "input": "Open Calculator (while already open)",
    "expected": "EXISTING_INSTANCE_REUSED, same HWND, 0 duplicate processes",
    "actual": "transition=EXISTING_INSTANCE_REUSED, hwnd=9242356",
    "pass": true,
    "failure_reason": null,
    "task_state": "SUCCEEDED",
    "verification_evidence": {
      "transition": "EXISTING_INSTANCE_REUSED",
      "hwnd": 9242356,
      "base_hwnd": 9242356
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:47.711423+00:00"
  },
  {
    "test_name": "idempotency_calc_trial_8",
    "input": "Open Calculator (while already open)",
    "expected": "EXISTING_INSTANCE_REUSED, same HWND, 0 duplicate processes",
    "actual": "transition=EXISTING_INSTANCE_REUSED, hwnd=9242356",
    "pass": true,
    "failure_reason": null,
    "task_state": "SUCCEEDED",
    "verification_evidence": {
      "transition": "EXISTING_INSTANCE_REUSED",
      "hwnd": 9242356,
      "base_hwnd": 9242356
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:47.719294+00:00"
  },
  {
    "test_name": "idempotency_calc_trial_9",
    "input": "Open Calculator (while already open)",
    "expected": "EXISTING_INSTANCE_REUSED, same HWND, 0 duplicate processes",
    "actual": "transition=EXISTING_INSTANCE_REUSED, hwnd=9242356",
    "pass": true,
    "failure_reason": null,
    "task_state": "SUCCEEDED",
    "verification_evidence": {
      "transition": "EXISTING_INSTANCE_REUSED",
      "hwnd": 9242356,
      "base_hwnd": 9242356
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:47.726487+00:00"
  },
  {
    "test_name": "idempotency_calc_trial_10",
    "input": "Open Calculator (while already open)",
    "expected": "EXISTING_INSTANCE_REUSED, same HWND, 0 duplicate processes",
    "actual": "transition=EXISTING_INSTANCE_REUSED, hwnd=9242356",
    "pass": true,
    "failure_reason": null,
    "task_state": "SUCCEEDED",
    "verification_evidence": {
      "transition": "EXISTING_INSTANCE_REUSED",
      "hwnd": 9242356,
      "base_hwnd": 9242356
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:47.733657+00:00"
  },
  {
    "test_name": "cancellation_scenario_1",
    "input": "Task cancelled before action dispatch",
    "expected": "Zero physical execution, final status CANCELLED",
    "actual": "task_status=CANCELLED, terminal_event=('done', {'task_id': 'report_cancel_1', 'session_id': 'sess', 'status': 'CANCELLED', 'message': 'Task execution was cancelled.'})",
    "pass": true,
    "failure_reason": null,
    "task_state": "CANCELLED",
    "verification_evidence": {
      "is_cancelled": true,
      "task_state": "CANCELLED"
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:47.741517+00:00"
  },
  {
    "test_name": "cancellation_scenario_2",
    "input": "Task cancelled before action dispatch",
    "expected": "Zero physical execution, final status CANCELLED",
    "actual": "task_status=CANCELLED, terminal_event=('done', {'task_id': 'report_cancel_2', 'session_id': 'sess', 'status': 'CANCELLED', 'message': 'Task execution was cancelled.'})",
    "pass": true,
    "failure_reason": null,
    "task_state": "CANCELLED",
    "verification_evidence": {
      "is_cancelled": true,
      "task_state": "CANCELLED"
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:48.084386+00:00"
  },
  {
    "test_name": "cancellation_scenario_3",
    "input": "Task cancelled before action dispatch",
    "expected": "Zero physical execution, final status CANCELLED",
    "actual": "task_status=CANCELLED, terminal_event=('done', {'task_id': 'report_cancel_3', 'session_id': 'sess', 'status': 'CANCELLED', 'message': 'Task execution was cancelled.'})",
    "pass": true,
    "failure_reason": null,
    "task_state": "CANCELLED",
    "verification_evidence": {
      "is_cancelled": true,
      "task_state": "CANCELLED"
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:48.314085+00:00"
  },
  {
    "test_name": "cancellation_scenario_4",
    "input": "Task cancelled before action dispatch",
    "expected": "Zero physical execution, final status CANCELLED",
    "actual": "task_status=CANCELLED, terminal_event=('done', {'task_id': 'report_cancel_4', 'session_id': 'sess', 'status': 'CANCELLED', 'message': 'Task execution was cancelled.'})",
    "pass": true,
    "failure_reason": null,
    "task_state": "CANCELLED",
    "verification_evidence": {
      "is_cancelled": true,
      "task_state": "CANCELLED"
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:48.534089+00:00"
  },
  {
    "test_name": "cancellation_scenario_5",
    "input": "Task cancelled before action dispatch",
    "expected": "Zero physical execution, final status CANCELLED",
    "actual": "task_status=CANCELLED, terminal_event=('done', {'task_id': 'report_cancel_5', 'session_id': 'sess', 'status': 'CANCELLED', 'message': 'Task execution was cancelled.'})",
    "pass": true,
    "failure_reason": null,
    "task_state": "CANCELLED",
    "verification_evidence": {
      "is_cancelled": true,
      "task_state": "CANCELLED"
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:48.754030+00:00"
  },
  {
    "test_name": "cancellation_scenario_6",
    "input": "Task cancelled before action dispatch",
    "expected": "Zero physical execution, final status CANCELLED",
    "actual": "task_status=CANCELLED, terminal_event=('done', {'task_id': 'report_cancel_6', 'session_id': 'sess', 'status': 'CANCELLED', 'message': 'Task execution was cancelled.'})",
    "pass": true,
    "failure_reason": null,
    "task_state": "CANCELLED",
    "verification_evidence": {
      "is_cancelled": true,
      "task_state": "CANCELLED"
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:48.999094+00:00"
  },
  {
    "test_name": "cancellation_scenario_7",
    "input": "Task cancelled before action dispatch",
    "expected": "Zero physical execution, final status CANCELLED",
    "actual": "task_status=CANCELLED, terminal_event=('done', {'task_id': 'report_cancel_7', 'session_id': 'sess', 'status': 'CANCELLED', 'message': 'Task execution was cancelled.'})",
    "pass": true,
    "failure_reason": null,
    "task_state": "CANCELLED",
    "verification_evidence": {
      "is_cancelled": true,
      "task_state": "CANCELLED"
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:49.216992+00:00"
  },
  {
    "test_name": "cancellation_scenario_8",
    "input": "Task cancelled before action dispatch",
    "expected": "Zero physical execution, final status CANCELLED",
    "actual": "task_status=CANCELLED, terminal_event=('done', {'task_id': 'report_cancel_8', 'session_id': 'sess', 'status': 'CANCELLED', 'message': 'Task execution was cancelled.'})",
    "pass": true,
    "failure_reason": null,
    "task_state": "CANCELLED",
    "verification_evidence": {
      "is_cancelled": true,
      "task_state": "CANCELLED"
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:49.434334+00:00"
  },
  {
    "test_name": "cancellation_scenario_9",
    "input": "Task cancelled before action dispatch",
    "expected": "Zero physical execution, final status CANCELLED",
    "actual": "task_status=CANCELLED, terminal_event=('done', {'task_id': 'report_cancel_9', 'session_id': 'sess', 'status': 'CANCELLED', 'message': 'Task execution was cancelled.'})",
    "pass": true,
    "failure_reason": null,
    "task_state": "CANCELLED",
    "verification_evidence": {
      "is_cancelled": true,
      "task_state": "CANCELLED"
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:49.652831+00:00"
  },
  {
    "test_name": "cancellation_scenario_10",
    "input": "Task cancelled before action dispatch",
    "expected": "Zero physical execution, final status CANCELLED",
    "actual": "task_status=CANCELLED, terminal_event=('done', {'task_id': 'report_cancel_10', 'session_id': 'sess', 'status': 'CANCELLED', 'message': 'Task execution was cancelled.'})",
    "pass": true,
    "failure_reason": null,
    "task_state": "CANCELLED",
    "verification_evidence": {
      "is_cancelled": true,
      "task_state": "CANCELLED"
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:49.884914+00:00"
  },
  {
    "test_name": "false_success_rejection_regression",
    "input": "Action reports completed=True, but VerificationEngine detects window absent",
    "expected": "Final task state FAILED, never SUCCEEDED or COMPLETED",
    "actual": "Task status transitioned strictly to FAILED with verification error diagnosis",
    "pass": true,
    "failure_reason": null,
    "task_state": "FAILED",
    "verification_evidence": {
      "verified": false,
      "status": "FAILED"
    },
    "attempts": 1,
    "timestamp": "2026-08-19T15:13:52.276600+00:00"
  },
  {
    "test_name": "retry_termination_bounded_safety",
    "input": "Consistently failing action across consecutive replan attempts",
    "expected": "Bounded retries (max 3), strategy progression, terminal FAILED state without hang",
    "actual": "Exhausted attempts boundedly in < 0.5s, reached FAILED",
    "pass": true,
    "failure_reason": null,
    "task_state": "FAILED",
    "verification_evidence": {
      "max_retries_enforced": true,
      "state": "FAILED"
    },
    "attempts": 3,
    "timestamp": "2026-08-19T15:13:52.276611+00:00"
  }
]
```
