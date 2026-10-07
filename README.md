# Lore AI Builder — Hexagonal DDD Worldbuilding Engine

> **High-Performance AI Lore & Worldbuilding Generation System**  
> Governed by **[JobObjects_RD](JobObjects_RD)** (macOS Darwin Kernel & Windows `_EJOB` OS Resource Shield) and **[TencentDB-Agent-Memory](TencentDB-Agent-Memory)** (L0–L3 Hierarchical Memory & Wiki Link Graph).

---

## 📖 Overview

**Lore AI Builder** is an enterprise-grade worldbuilding and canon generation platform engineered using **Hexagonal Architecture (Ports & Adapters)** and **Domain-Driven Design (DDD)**. 

Generating rich, multi-epoch fictional or game universes poses two critical engineering bottlenecks:
1. **Context Window Drift & Canon Inconsistency:** Unconstrained LLMs frequently introduce hallucinations, chronological paradoxes, or break established natural and magical laws.
2. **High Memory Overhead & Swarm Contention:** Running multi-agent generation swarms consumes massive RAM during long LLM inference phases (30–90s), causing memory bloat and CPU starvation.

**Lore AI Builder** solves both problems by pairing a **4-layer hierarchical memory model** with a **native OS-level kernel resource controller** operating under a **strict Zero-Fallbacks policy**.

---

## 🏛 Architecture: Hexagonal (Ports & Adapters) + DDD

The codebase strictly decouples business domain rules from OS infrastructure, databases, and LLM providers.

```text
lore_builder/
├── domain/                                  # 1. PURE DOMAIN CORE (No external framework dependencies)
│   ├── model/
│   │   ├── aggregate.py                     # WorldBibleAggregate (L3), LoreEntityAggregate
│   │   ├── entity.py                        # LoreFact (L1 atomic canon fact)
│   │   ├── value_objects.py                 # EntityType, CanonStatus, RelationType, TimelinePoint
│   │   └── events.py                        # Domain Events (EntityDraftCreated, AuditPassed, etc.)
│   ├── services/
│   │   └── consistency_checker.py           # Domain Consistency Service (Axiom & Fact conflict audit)
│   └── exceptions.py                        # Domain Exceptions (LoreCanonConflictError)
│
├── application/                             # 2. APPLICATION LAYER (Use Cases & Ports)
│   ├── dto/
│   │   └── entity_dto.py                    # GenerateEntityCommand, EntityResponseDTO, AuditResultDTO
│   ├── ports/
│   │   ├── inbound/                         # Driving Ports (API / UI interfaces)
│   │   │   ├── generate_lore_port.py        # GenerateLoreUseCasePort
│   │   │   └── audit_lore_port.py           # AuditLoreUseCasePort
│   │   └── outbound/                        # Driven Ports (SPI interfaces)
│   │       ├── memory_port.py               # MemoryPort (Abstraction for L0-L3 & Wiki Knowledge)
│   │       ├── resource_port.py             # ResourceControllerPort (OS Kernel Controller abstraction)
│   │       ├── llm_port.py                  # LLMProviderPort (Inference provider abstraction)
│   │       └── event_publisher_port.py      # EventPublisherPort (Domain event dispatcher)
│   └── use_cases/
│       ├── generate_entity_use_case.py      # End-to-end entity generation use case
│       └── audit_entity_use_case.py         # Canon consistency audit use case
│
├── infrastructure/                          # 3. INFRASTRUCTURE LAYER (Secondary Adapters)
│   └── adapters/
│       ├── resource/
│       │   └── job_objects_adapter.py       # Bridges to native C++ libAgentJobEngineC.dylib (JobObjects_RD)
│       ├── memory/
│       │   ├── tencent_memory_adapter.py    # Bridges to TencentDB-Agent-Memory v3 SDK
│       │   └── in_memory_adapter.py         # In-memory L0-L3 & Wiki Graph (for unit tests / local dev)
│       └── llm/
│           ├── openai_compatible_adapter.py # Strict OpenRouter / OpenAI / Ollama adapter
│           └── mock_llm_adapter.py          # Deterministic fixture generator for unit testing
│
└── presentation/                            # 4. PRESENTATION LAYER (Primary Adapters)
    ├── cli.py                               # Production Command-Line Interface
    └── demo.py                              # End-to-end automated demonstration
```

---

## ⚡ Core Pillars

### 1. OS Kernel Resource Shield ([JobObjects_RD](JobObjects_RD))
Integrates directly with the native C++ `AgentJobEngine` library via 64-bit `ctypes`:
* **Idle Working Set Compression (`TrimWorkingSetToCompressStore`):** While an agent awaits cloud LLM streaming responses, the OS memory manager compresses the agent runtime heap from **~180 MB down to < 15 MB** using macOS Darwin QoS (`PRIO_DARWIN_BG`) and Windows `_EJOB` Page Priority limits.
* **Process Tree Freezing (`FreezeJobTree` / `ThawJobTree`):** Synchronizes generation pipelines. Downstream worker processes are frozen via `SIGSTOP` during canon audits with **0% CPU consumption**, preventing race conditions before being thawed via `SIGCONT`.
* **Zero-Fallbacks Native Enforcement:** Native library loading and kernel calls are strictly enforced. Any kernel-level failure triggers explicit exceptions rather than silent simulated fallbacks.

### 2. Hierarchical Memory ([TencentDB-Agent-Memory](TencentDB-Agent-Memory))
Structured knowledge flow preventing context window degradation:

| Memory Layer | Domain Purpose | Storage & Retrieval |
| :--- | :--- | :--- |
| **L3 Core** | **World Bible:** Immutable cosmic rules, physics, theology, and aesthetic tone. | Injected into all system prompts. |
| **L2 Scenario** | **Historical & Regional Dossiers:** Era overviews, kingdom histories. | Scoped by Era / Continent. |
| **L1 Atomic** | **Verified Canon Facts:** Discrete verified assertions (e.g., dates, deaths, artifacts). | Vector embeddings + BM25 + Reciprocal Rank Fusion (RRF). |
| **Wiki + Link Graph** | **Entity Network:** Bidirectional connections between characters, factions, and places. | Backlinks, Outbound links, graph traversal. |
| **L0 Conversation** | **Audit Trail:** Raw generation prompts and assistant drafts. | Session-scoped conversation logs. |

### 3. Canon Consistency Defense
Before any entity draft is committed to canon, `DomainConsistencyPolicy`:
1. Audits statements against all **L3 World Bible Immutable Laws** (e.g. mortality rules, law of conservation of magic).
2. Verifies assertions against known **L1 Atomic Facts**.
3. Rejects conflicting proposals with `LoreCanonConflictError` before they can corrupt the lore graph.

---

## 🚀 Getting Started

### Prerequisites
* **macOS** (Apple Silicon or Intel) or **Windows 11 / Server**
* **Python 3.10+** (tested up to Python 3.14)
* **CMake 3.20+** and a C++17 compiler (AppleClang or MSVC)

### 1. Clone & Initialize Submodules
```bash
git clone --recurse-submodules https://github.com/bivex/lore_ai_builder.git
cd lore_ai_builder
```

### 2. Build the Native C++ Engine (`JobObjects_RD`)
```bash
cd JobObjects_RD
cmake -B out/build -DCMAKE_BUILD_TYPE=Release
cmake --build out/build
cd ..
```
*Verification:* The build produces `JobObjects_RD/out/build/lib/libAgentJobEngineC.dylib` (macOS) or `AgentJobEngineC.dll` (Windows).

### 3. Configure Environment Variables
Create a `.env` file in the project root:
```env
OPENROUTER_API_KEY=your_openrouter_api_key_here
OPENROUTER_MODEL=nvidia/nemotron-3-ultra-550b-a55b:free
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
```

---

## 🧪 Testing

Run the full unit test suite (100% pass):
```bash
python3 -m pytest tests/unit/test_lore_pipeline.py -v
```

Tests validate:
* `test_domain_entity_lifecycle`: Aggregate state transitions (`DRAFT` → `AUDITING` → `CANONICAL`).
* `test_consistency_policy_detects_violation`: Domain service catching canon breaches.
* `test_end_to_end_generation_with_job_objects_shield`: End-to-end generation under native OS memory trim.
* `test_canon_violation_triggers_rejection`: Automatic rejection of contradicting lore drafts.

---

## 🎮 Running the System

### 1. Run the End-to-End Architectural Demo
```bash
python3 lore_builder/presentation/demo.py
```
This demonstrates:
1. Initializing the L3 World Bible (*Aethelgard*).
2. Generating a canonical character (*Kaelen Voss*) under OS resource control.
3. Automatically intercepting and rejecting an invalid entity (*Malakor the Undying*, which attempts to bypass mortality rules).
4. Querying the resulting Wiki Link Graph.

### 2. Live Generation via OpenRouter (`nvidia/nemotron-3-ultra-550b-a55b:free`)
```bash
python3 test_openrouter_nemotron.py
```

### 3. CLI Usage

#### View Active World Bible (L3):
```bash
python3 lore_builder/presentation/cli.py show-world
```

#### Generate a New Lore Entity:
```bash
python3 lore_builder/presentation/cli.py generate \
  --name "The Iron Archon" \
  --type character \
  --prompt "A mechanical golem general powered by blood sacrifice" \
  --era "First Age" \
  --year 100
```

#### Run Full Multi-Agent Swarm DAG Pipeline:
```bash
python3 lore_builder/presentation/cli.py swarm \
  --prompt "Create the northern necromancer clan, their ancient feud with the sun paladins, and the war that changed their lands"
```

#### Inspect Entity Wiki Link Graph:
```bash
python3 lore_builder/presentation/cli.py graph --name "The Iron Archon"
```

---

## 📦 Submodules

* **[JobObjects_RD](JobObjects_RD)** (`branch: f/macos`) — High-Density AI Agent OS Resource Controller leveraging Darwin Kernel QoS and Windows `_EJOB` primitives.
* **[TencentDB-Agent-Memory](TencentDB-Agent-Memory)** (`v2.0.2`) — Hierarchical memory infrastructure providing L0–L3 isolation, Vector/BM25 retrieval, and Wiki Knowledge graphs.

---

## 📜 License

Licensed under the MIT License.
