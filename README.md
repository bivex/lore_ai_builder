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
│   │   ├── events.py                        # Domain Events (EntityDraftCreated, AuditPassed, etc.)
│   │   └── jev_decisions.py                 # Typed System-1 decisions (Noul, Choice, Score)
│   ├── services/
│   │   ├── consistency_checker.py           # Domain Consistency Service (Semantic Axiom & Fact audit)
│   │   ├── temporal_validator.py            # Allen's Interval Algebra consistency engine
│   │   ├── entity_resolver.py               # Jaro-Winkler entity resolution & alias deduplication
│   │   ├── dag_decomposer.py                # Kahn's Topological Sort & Task DAG decomposition
│   │   └── triplet_extractor.py             # OpenIE triplet extraction & graph distillation
│   └── exceptions.py                        # Domain Exceptions (LoreCanonConflictError)
│
├── application/                             # 2. APPLICATION LAYER (Use Cases & Ports)
│   ├── dto/
│   │   ├── entity_dto.py                    # GenerateEntityCommand, EntityResponseDTO, AuditResultDTO
│   │   └── workflow_dto.py                  # Declarative YAML workflow contracts and task DTOs
│   ├── ports/
│   │   ├── inbound/                         # Driving Ports (API / UI interfaces)
│   │   │   ├── generate_lore_port.py        # GenerateLoreUseCasePort
│   │   │   └── audit_lore_port.py           # AuditLoreUseCasePort
│   │   └── outbound/                        # Driven Ports (SPI interfaces)
│   │       ├── memory_port.py               # MemoryPort (Abstraction for L0-L3 & Wiki Knowledge)
│   │       ├── resource_port.py             # ResourceControllerPort (OS Kernel Controller abstraction)
│   │       ├── llm_port.py                  # LLMProviderPort (Inference provider abstraction)
│   │       ├── event_publisher_port.py      # EventPublisherPort (Domain event dispatcher)
│   │       └── jev_decision_port.py         # JevDecisionPort (System-1 typed decisions SPI)
│   ├── services/
│   │   ├── context_optimizer.py             # RRF + Graph BFS + 0/1 Knapsack Token Allocator
│   │   └── yaml_workflow_service.py         # Strict YAML task specification parser & validator
│   └── use_cases/
│       ├── generate_entity_use_case.py      # Single entity generation use case
│       ├── audit_entity_use_case.py         # Canon consistency audit use case
│       ├── orchestrate_swarm_use_case.py    # Multi-agent swarm DAG orchestration use case
│       └── execute_workflow_use_case.py     # Declarative YAML workflow execution use case
│
├── infrastructure/                          # 3. INFRASTRUCTURE LAYER (Secondary Adapters)
│   └── adapters/
│       ├── resource/
│       │   └── job_objects_adapter.py       # Bridges to native C++ libAgentJobEngineC.dylib (JobObjects_RD)
│       ├── memory/
│       │   ├── tencent_memory_adapter.py    # Bridges to TencentDB-Agent-Memory v3 SDK
│       │   └── in_memory_adapter.py         # In-memory L0-L3 & Wiki Graph (for unit tests / local dev)
│       ├── llm/
│       │   ├── openai_compatible_adapter.py # Strict OpenRouter / OpenAI / Ollama adapter
│       │   └── mock_llm_adapter.py          # Deterministic fixture generator for unit testing
│       └── audit/
│           └── open_jev_lore_adapter.py     # Sub-50ms calibrated Jev System-1 decision engine
│
├── presentation/                            # 4. PRESENTATION LAYER (Primary Adapters)
│   ├── cli.py                               # Production YAML Runner & Command-Line Interface
│   └── demo.py                              # End-to-end automated demonstration
│
└── configs/
    └── tasks.yml                            # Sample declarative YAML task workflow specification
```

---

## ⚡ Core Pillars

### 1. Declarative YAML Workflow Engine
Instead of passing dozens of brittle script parameters, tasks are specified in human-readable, version-controlled `.yml` files:
* **Batch Task Pipelines:** Run entity generation, swarm DAGs, Jev canon audits, and ontology classifications in a single execution.
* **World & Settings Isolation:** Declaratively define the target World Bible, runtime LLM provider, memory backend, and export output paths.
* **Strict Schema Validation:** Zero silent fallbacks — syntax errors or missing parameters trigger explicit validation messages.

### 2. OS Kernel Resource Shield ([JobObjects_RD](JobObjects_RD))
Integrates directly with the native C++ `AgentJobEngine` library via 64-bit `ctypes`:
* **Idle Working Set Compression (`TrimWorkingSetToCompressStore`):** While an agent awaits cloud LLM streaming responses, the OS memory manager compresses the agent runtime heap from **~180 MB down to < 15 MB** using macOS Darwin QoS (`PRIO_DARWIN_BG`) and Windows `_EJOB` Page Priority limits.
* **Process Tree Freezing (`FreezeJobTree` / `ThawJobTree`):** Synchronizes generation pipelines. Downstream worker processes are frozen via `SIGSTOP` during canon audits with **0% CPU consumption**, preventing race conditions before being thawed via `SIGCONT`.
* **Zero-Fallbacks Native Enforcement:** Native library loading and kernel calls are strictly enforced. Any kernel-level failure triggers explicit exceptions rather than silent simulated fallbacks.

### 3. Hierarchical Memory ([TencentDB-Agent-Memory](TencentDB-Agent-Memory))
Structured knowledge flow preventing context window degradation:

| Memory Layer | Domain Purpose | Storage & Retrieval |
| :--- | :--- | :--- |
| **L3 Core** | **World Bible:** Immutable cosmic rules, physics, theology, and aesthetic tone. | Injected into all system prompts. |
| **L2 Scenario** | **Historical & Regional Dossiers:** Era overviews, kingdom histories. | Scoped by Era / Continent. |
| **L1 Atomic** | **Verified Canon Facts:** Discrete verified assertions (e.g., dates, deaths, artifacts). | Vector embeddings + BM25 + Reciprocal Rank Fusion (RRF). |
| **Wiki + Link Graph** | **Entity Network:** Bidirectional connections between characters, factions, and places. | Backlinks, Outbound links, graph traversal. |
| **L0 Conversation** | **Audit Trail:** Raw generation prompts and assistant drafts. | Session-scoped conversation logs. |

### 4. Jev System-1 Decision Engine (Sub-50ms Non-Autoregressive Lore Decisions)
Instead of relying on heavy, slow autoregressive LLM calls for validation (5–15 seconds per check), Lore AI Builder integrates **Jev / Open-Jev System-1 typed decisions** running in sub-50ms forward passes:
* **`JevNoulDecision` (Axiom Compliance):** Non-autoregressive Boolean verdict with calibrated probability $P(\text{comply}) \in [0.0, 1.0]$. Tested in parallel against all World Bible immutable laws.
* **`JevScoreDecision` (Lore Distortion Risk):** Ordinal assessment across calibrated severity levels (`none`, `minor`, `severe`, `canon_breaking`) with an expected risk score $[0.00 .. 3.00]$.
* **`LoreOntologyRelationChoice` (Categorical Ontological Relations):** Multi-class decision predicting semantic relationship types (`allied_with`, `ruler_of`, `enemy_of`, `vassal_of`, `worships`, `located_in`) to populate the Wiki graph.
* **`LoreTemporalChoice` (Allen's Interval Algebra):** Categorical temporal relation classification (`before`, `meets`, `during`, `overlaps`, `equals`, `after`) across historical epochs.
* **"Read Once, Ask Many" (Jev v3 Architecture):** The World Bible state is rendered once and answers multiple axiom compliance questions in a single parallel pass without token re-encoding.

### 5. Zero-False-Positives Canon Defense
A robust semantic filtering engine prevents erroneous rejections of valid canonical lore:
* **Metaphorical & Attributive Immunity:** Distinguishes poetic figures of speech (*"undying loyalty"*, *"immortal legacy"*, *"infinite patience"*) from actual claims of physical or divine immortality.
* **Beneficiary Cost Distinction:** Recognizes sentences describing magic performed *"without cost to the villagers"*, ensuring characters who made personal sacrifices are approved.
* **Antagonist Interaction:** Allows mortal heroes who *"fought against the undying dreadlords"* without falsely attributing immortality to the hero.
* **Grammatical Negation Detection:** Validates characters explicitly stating they *"were not immortal and accepted their mortal fate"*.
* **Kinship Disambiguation in Timelines:** Prevents facts like *"Kaelen's father died in year 100"* from triggering false temporal paradoxes against Kaelen's subsequent deeds.
* **Short-Name Fuzzy Guards:** Prevents distinct short names (*"Alden"* vs *"Aldon"*, *"Voss"* vs *"Ross"*) from being falsely merged by Jaro-Winkler similarity.

### 6. Complete Worldbuilding Algorithmic Suite
* **DAG Task Decomposition & Kahn's Topological Sort:** Breaks high-level worldbuilding prompts into dependency DAGs and organizes multi-agent generation waves.
* **Allen's Interval Temporal Algebra:** Strictly detects causal timeline paradoxes (e.g. an entity born after a kingdom fell cannot be its founder).
* **Jaro-Winkler Entity Resolution:** Deduplicates character and location names across multi-agent swarms with configurable similarity thresholds.
* **Reciprocal Rank Fusion (RRF) & 0/1 Knapsack Context Packing:** Combines BM25 and vector search results, dynamically packing facts within strict token budgets.
* **Triplet Extraction & Graph Distillation:** Extracts OpenIE subject-predicate-object triplets, maps them into canonical ontology edges via Jev Choice, and writes them into the Wiki graph.

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

Run the full unit test suite (100% pass across all 30 tests):
```bash
python3 -m pytest tests/unit/ -v
```

Tests validate:
* **Declarative YAML Workflow Suite (`test_yaml_workflow.py`):** YAML workflow parsing, strict task type and parameter validation, end-to-end execution, and JSON report export.
* **Zero-False-Positives Canon Defense Suite (`test_false_positives.py`):** Validates immunity for metaphorical figures of speech (*"undying loyalty"*, *"immortal legacy"*), beneficiary magic costs, battling immortal foes, explicit negations, relative death disambiguation, and short-name fuzzy guards.
* **Jev System-1 Lore Engine Suite (`test_jev_lore.py`):** Calibrated Noul axiom evaluations, Score distortion risks, Choice ontological relation classification, temporal interval analysis, and swarm knowledge graph enrichment.
* **Worldbuilding Algorithms Suite (`test_algorithms.py`):** Allen's interval algebra, Jaro-Winkler entity resolution, DAG topological sorting, RRF + Knapsack token packing, triplet extraction, and end-to-end swarm orchestration.
* **Core Pipeline & Kernel Shield Suite (`test_lore_pipeline.py`):** Domain aggregate lifecycle, native C++ `JobObjects_RD` memory trimming and process freezing, and strict canon defense rejection.

---

## 🎮 Running the System

### 1. Declarative YAML Task Execution (Recommended)
Tasks are defined declaratively in `.yml` files (`configs/tasks.yml`) rather than passing dozens of CLI flags:

```bash
python3 -m lore_builder.presentation.cli configs/tasks.yml
```
*(or explicitly: `python3 -m lore_builder.presentation.cli run configs/tasks.yml`)*

#### Example `configs/tasks.yml` schema:
```yaml
version: "1.0"

# Target World Bible Definition (L3 Core)
world:
  name: "Aethelgard"
  cosmology: "A fractured plane orbiting a dying stellar core, bound by the Ley Lines."
  immutable_laws:
    - "Magic demands an equal sacrifice of vitality (No free energy)"
    - "Mortals cannot achieve true divinity without burning their mortal shell"
    - "The Void Rifts cannot be sealed, only diverted"

# Runtime Execution Settings
settings:
  use_mock_llm: true          # Set to false to use OpenRouter (nvidia/nemotron-3-ultra-550b)
  use_tencent_memory: false   # Set to true for live TencentDB Agent Memory cluster
  output_file: "output/lore_pipeline_results.json"

# Declarative Task Sequence
tasks:
  - type: generate
    name: "The Iron Archon"
    entity_type: character
    prompt: "A mechanical golem general powered by blood sacrifice"
    era: "First Age"
    year: 120

  - type: swarm
    prompt: "Create the northern necromancer clan, their ancient feud with the sun paladins, and the war that changed their lands"

  - type: audit
    name: "Malakor the Undying"
    narrative: "An immortal tyrant who cast infinite magic without sacrifice."

  - type: classify
    source: "High Commander Kaelen"
    target: "The Silver Wardens"
    context: "Commander Kaelen commands the Silver Wardens into battle against the Void."

  - type: temporal
    interval_a: "The Primordial Dawn"
    interval_b: "The Age of Iron"
    context: "The Primordial Dawn occurred centuries prior to the Age of Iron."

  - type: score
    narrative: "An ordinary blacksmith crafting bronze swords in the marketplace."

  - type: graph
    name: "The Iron Archon"
```

---

### 2. Run the End-to-End Architectural Demo
```bash
python3 -m lore_builder.presentation.demo
```
This demonstrates:
1. Initializing the L3 World Bible (*Aethelgard*).
2. Generating a canonical character (*Kaelen Voss*) under native OS resource control (`JobObjects_RD`).
3. Automatically intercepting and rejecting an invalid entity (*Malakor the Undying*, which attempts to bypass mortality rules).
4. Running sub-50ms **Jev System-1 Typed Decisions** (Noul axiom compliance, distortion score, ontology classification, Allen interval relation).
5. Querying the resulting Wiki Link Graph.

### 3. Live Generation via OpenRouter (`nvidia/nemotron-3-ultra-550b-a55b:free`)
```bash
python3 test_openrouter_nemotron.py
```

### 4. Interactive Command-Line Subcommands (Optional)

#### View Active World Bible (L3):
```bash
python3 -m lore_builder.presentation.cli show-world
```

#### Generate a New Lore Entity:
```bash
python3 -m lore_builder.presentation.cli generate \
  --name "The Iron Archon" \
  --type character \
  --prompt "A mechanical golem general powered by blood sacrifice" \
  --era "First Age" \
  --year 100
```

#### Run Full Multi-Agent Swarm DAG Pipeline:
```bash
python3 -m lore_builder.presentation.cli swarm \
  --prompt "Create the northern necromancer clan, their ancient feud with the sun paladins, and the war that changed their lands"
```

#### Inspect Entity Wiki Link Graph:
```bash
python3 -m lore_builder.presentation.cli graph --name "The Iron Archon"
```

#### Jev System-1 Lore Subcommands:

##### Run Instant Canon Audit on Entity Narrative:
```bash
python3 -m lore_builder.presentation.cli jev-audit \
  --name "Malakor the Undying" \
  --narrative "An immortal tyrant who cast infinite magic without sacrifice"
```

##### Classify Ontological Relationship:
```bash
python3 -m lore_builder.presentation.cli jev-classify \
  --source "High Commander Kaelen" \
  --target "The Silver Wardens" \
  --context "Commander Kaelen commands the Silver Wardens"
```

##### Evaluate Lore Distortion Risk Score:
```bash
python3 -m lore_builder.presentation.cli jev-score \
  --narrative "An ordinary blacksmith crafting bronze swords in the market"
```

##### Classify Historical Temporal Relation (Allen's Algebra):
```bash
python3 -m lore_builder.presentation.cli jev-temporal \
  --a "The Dawn Era" \
  --b "The Cataclysm" \
  --context "The Dawn Era occurred centuries prior to the Cataclysm"
```

---

## 📦 Submodules

* **[JobObjects_RD](JobObjects_RD)** (`branch: f/macos`) — High-Density AI Agent OS Resource Controller leveraging Darwin Kernel QoS and Windows `_EJOB` primitives.
* **[TencentDB-Agent-Memory](TencentDB-Agent-Memory)** (`v2.0.2`) — Hierarchical memory infrastructure providing L0–L3 isolation, Vector/BM25 retrieval, and Wiki Knowledge graphs.

---

## 📜 License

Licensed under the MIT License.
