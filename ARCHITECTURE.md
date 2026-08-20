# PLUTON V2 Canonical Architecture Specification

PLUTON V2 is a deterministic, evidence-based computer automation and agentic pairing substrate. Reasoning, planning, target resolution, execution domains, and postcondition verification are strictly decoupled.

---

## 1. System Topology & Core Subsystems

```mermaid
graph TD
    UserReq["Natural Language Request Intake (/api/chat)"] --> Compiler["Universal Intent & Plan Compiler"]
    Compiler --> Plan["Deterministic Multi-Step Plan (Actions & Verification Strategies)"]
    Plan --> Loop["Universal Agent Loop (Observe-Act-Verify-Replan)"]
    
    subgraph "Execution & Safety Pipeline"
        Loop --> PreWorld["WorldState.capture()"]
        Loop --> SafetyGate{"Control Kernel (Permissions & Confirmation)"}
        SafetyGate --> DomainRouter["Capability Domain Dispatch"]
        DomainRouter --> AppDom["App Domain (Win32 Lifecycle & HWND Binding)"]
        DomainRouter --> BrowserDom["Browser Domain (Native Tabs & Navigation)"]
        DomainRouter --> FSDom["Filesystem Domain (Workspace-Gated I/O)"]
        DomainRouter --> TermDom["Terminal Domain (Security-Filtered Execution)"]
    end
    
    subgraph "Verification & Adaptive Replanning"
        AppDom --> PostWorld["WorldState.capture()"]
        BrowserDom --> PostWorld
        FSDom --> PostWorld
        TermDom --> PostWorld
        
        PostWorld --> Verifier["Verification Engine (Mandatory Postcondition Readback)"]
        Verifier -->|PASS| NextStep["Step Completed -> Next Step"]
        Verifier -->|FAIL| Classifier["Failure Classifier (Taxonomy Mapping)"]
        Classifier --> WSReconcile["WorldState Targeted Refresh & Invalidation"]
        WSReconcile --> ReplanEngine["Adaptive Replan Engine (Max 3 Attempts)"]
        ReplanEngine -->|New Valid Strategy| DomainRouter
        ReplanEngine -->|Budget Exhausted / Safety Gated| TaskHalt["Task Halted with Honest Diagnostic"]
    end
```

---

## 2. Core Architecture Tenets

1. **Zero Hardcoding**: No application names, URLs, arithmetic expressions, process names, or UI element selectors are hardwired into procedural decision logic.
2. **Action vs Target Separation**: Targets represent addressable entities (applications, URLs, HWNDs, tabs, files). Actions represent capabilities (`app.launch`, `keyboard.type`, `browser.navigate`). Actions and parameters are never falsely routed through `TargetResolver`.
3. **Mandatory Postcondition Verification**: No tool call is considered complete merely because `tool_res.status == "completed"`. Physical evidence must be confirmed in the environment (`UIA_READBACK`, `WINDOW_PRESENCE`, `BROWSER_TAB_PRESENCE`, `FILESYSTEM_CHECK`, `DOM_VALUE_MATCH`).
4. **Bounded Adaptive Replanning**: Step verification failures trigger automated failure classification, state refresh, and materially different alternative strategy selection (capped strictly at 3 attempts per step). Safety confirmations and ambiguous target refusals cannot be bypassed by replanning.
5. **Universal Multi-Source Target Resolution**: Target discovery dynamically probes live windows, browser tabs, loopback web services (e.g. `http://127.0.0.1:5173`), desktop registry paths, and filesystem items using evidence scoring and ambiguity gating.