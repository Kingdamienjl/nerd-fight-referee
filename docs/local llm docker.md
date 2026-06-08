# Dockerized Local LLM Discord Arbiter for Anime and Game Character Battles

## Executive summary

For your hardware profile—Ryzen 7 8700F, 32 GB RAM, RTX 4070 SUPER 12 GB, and ample disk—the strongest practical design is a **Docker Compose stack built around Ollama, LiteLLM, Redis, Postgres, and a slash-command Discord bot in discord.py**. On a 12 GB GPU, the safe public-serving tier is **quantized 8B-class models**. A **Qwen3 8B Q4_K_M-class build** is the best default because Qwen3 explicitly supports switching between thinking and non-thinking modes and is designed for reasoning, tool use, and structured output workflows. **DeepSeek-R1 8B** is the best alternative when you want a heavier referee mode, but it tends to be slower and more verbose. **14B Q4_K_M** models can run, but they leave much less VRAM headroom and are a bad default for a public queue on a single 4070 SUPER. **32B Q4_K_M is out** for this machine in GPU-resident serving because Ollama’s DeepSeek-R1 32B Q4_K_M tag is 20 GB. citeturn35view0turn35view2turn37view0turn38view2turn38view3turn39search0

For Discord, the clean public design is **slash commands, not `!fight` prefix commands**. Discord.py’s commands extension requires the **Message Content intent** for prefix commands, and Discord documents Message Content as a **privileged intent**. Since you want to avoid privileged intents from day one and scale beyond 100 servers, the production command surface should be `/fight`, `/refresh`, `/sources`, and `/confidence`, with optional dev-only prefix aliases in a test guild. Every command should **defer immediately** because Discord requires an initial interaction response within **3 seconds**, and interaction tokens remain usable for **15 minutes** for follow-ups and edits. citeturn1view5turn1view6turn24search1turn13view0

The evidence model should be **strictly source-aware**: use official publisher/developer materials and official game/anime databases where available for decisive facts; use AniList for franchise, title, and character metadata; and allow **VS Battles Wiki only as an admissible fan-wiki source whose claims cannot decide the verdict unless corroborated**. That fits both your desired policy and the nature of the sources: AniList exposes a public GraphQL API, while VS Battles pages explicitly describe character versions, tiers, powers, and calculations, but VS Battles is still a community-edited Fandom wiki. Also, because **Fandom’s Terms of Use prohibit scraping/indexing content and using content to develop AI systems without prior consent**, the safest “refresh/research” workflow is **operator-run curation**, not autonomous bulk scraping of VS Battles pages. citeturn18view0turn18view1turn31search0turn31search6turn32view0turn32view1turn32view2turn21search1

Operationally, a single personal PC can absolutely host a bot that is **present in 100+ servers** if demand is bursty, but it should be treated as a **queued single-GPU service**, not a parallel battle farm. LiteLLM is a useful gateway here because it provides an OpenAI-compatible front door, virtual keys, rate limits, model routing, and spent/usage tracking, while Ollama provides the local model runtime and structured outputs. LM Studio is also viable, but its official docs position it more as a **headless host-native daemon** (`llmster` / `lms`) than a Docker-first inference service, so if the top goal is “Dockerized everywhere,” Ollama is the cleaner primary path. citeturn40view2turn30search0turn30search1turn30search3turn27view0turn27view2turn28view0turn28view1turn28view4

## Hardware envelope and model choice

Your hard constraint is the **12 GB VRAM** on the RTX 4070 SUPER. Ollama supports NVIDIA GPUs with **compute capability 5.0+** and modern drivers, so your card is comfortably inside the supported window. The practical consequence is simple: **7B–8B Q4-class models fit comfortably**, **14B Q4-class models are possible but tight**, and **32B Q4-class models exceed your GPU envelope**. For this specific project, that means reliability matters more than squeezing the last bit of model IQ out of a borderline 14B serve. citeturn39search0turn37view0turn38view2turn38view3

| Model option | Quantized size | Approx. VRAM use on your box | Expected latency per fight | Why it fits this project | Tradeoffs |
|---|---:|---:|---:|---|---|
| **Qwen3 8B Q4_K_M-class** | ~5.2 GB | ~7–9 GB | ~15–40 s | Best default referee: strong instruction following, explicit thinking/non-thinking control, good tool/JSON behavior | Slightly less “slow-think” than DeepSeek on edge cases |
| **DeepSeek-R1 8B** | 5.2 GB | ~8–10 GB | ~25–60 s | Strongest reasoning-first local default at this size; good for hard matchup logic | Verbose, slower, more likely to overthink |
| **Qwen3 14B Q4_K_M** | 9.3 GB | ~10.5–11.8 GB | ~40–90 s | Higher-quality “detail mode” if queue is light and context is controlled | Too tight for public default on a 12 GB GPU; lower concurrency headroom |

The on-disk model sizes above are drawn from the Ollama library/tags where available; the VRAM and latency columns are **engineering estimates**, not vendor benchmarks. They assume a warmed model, an 8K–16K effective prompt, GPU-first inference, and a structured 1–2K token referee response. The important operational fact is not the exact seconds; it is that **8B is the reliable public tier** and **14B should be opt-in only**. citeturn37view0turn38view2turn38view3turn35view0turn35view2

My recommendation is to expose **two model modes**:

- **Standard mode** → `qwen3:8b`
- **Reasoning mode** → `deepseek-r1:8b`

Then, if you later discover that queue depth is consistently low, add **high-detail mode** with `qwen3:14b`. Do **not** make 14B the default on day one. That gives you the best mix of schema compliance, speed, and battle logic on the 4070 SUPER. Qwen3’s official materials explicitly emphasize thinking/non-thinking switching, tool capability, and reasoning improvements, while DeepSeek-R1’s official model card emphasizes distilled reasoning behavior and benchmark strength. citeturn35view0turn35view1turn35view2

## Architecture and runtime design

The winning topology is **Discord bot as control plane, Redis as queue, Postgres as source-of-truth and battle store, LiteLLM as API normalization/auth/routing layer, and Ollama as the only GPU-facing runtime**. This keeps the Discord event loop fast, prevents inference from blocking interactions, and gives you an upgrade path later if you add a second GPU box or a cloud overflow worker. LiteLLM’s architecture docs explicitly describe request validation, rate limiting, Redis/in-memory cache use, routing, retries, and asynchronous post-request bookkeeping; Ollama exposes the local HTTP API that actually runs the models. citeturn40view2turn27view1

```mermaid
flowchart LR
    U[Discord User] --> D[discord.py Bot]
    D -->|defer in under 3s| Q[Redis Queue]
    D --> P[(Postgres)]
    Q --> W[Arbiter Worker]
    W --> S[Source Resolver]
    S --> P
    W --> L[LiteLLM Gateway]
    L --> O[Ollama Local LLM]
    W --> P
    P --> D
    D --> R[Discord Follow-up Embed and Buttons]
```

The key non-blocking rule is: **never let the Discord process do heavyweight model calls directly**. Discord requires an initial interaction response inside **3 seconds**, and the interaction token is valid for **15 minutes**. So the bot should validate input, create a `battle_request` row, push a job onto Redis, defer the interaction, and return control immediately. A separate **arbiter worker** then resolves evidence, calls the LLM, computes the confidence score, writes `battle_result`, and triggers the bot to edit the original message or send a follow-up. If you ever expect a queue backlog that might exceed 15 minutes, the bot should return a persistent `job_id` early and deliver the final result as a new message rather than relying forever on the original interaction token. citeturn13view0

A useful relational schema for scaffolding is small and boring:

- `character`
- `character_version`
- `source`
- `claim`
- `claim_source_link`
- `battle_request`
- `battle_result`

Postgres should be the system of record because you want stable IDs, searchable evidence, and reproducible battle reports; Redis should stay ephemeral and queue-oriented. If you later want fuzzy alias resolution, add `pg_trgm` or `pgvector`, but do not start there. Start with normalized aliases and exact/source-backed profiles.

A minimal Compose-friendly service split looks like this:

- `ollama`  
- `litellm`
- `postgres`
- `redis`
- `bot`
- `worker`

Then add monitoring containers later. Docker Compose supports explicit GPU device reservations, and Docker’s docs require the `capabilities` field for GPU reservations. Use that instead of older ad hoc runtime hacks. citeturn26view0turn26view2

```mermaid
flowchart TD
    A[Profile Request]
    A --> B{Character Exists?}
    B -->|Yes| C[Load vetted sources and claims]
    B -->|No| D[Offline Refresh Mode]
    D --> E[AniList or official metadata]
    D --> F[Operator adds VS Battles or fan-wiki claims]
    F --> G[Corroboration review]
    G --> H[Insert vetted claims into Postgres]
    H --> C
    C --> I[LLM Referee JSON]
    I --> J[Confidence engine]
    J --> K[Discord result + source cards]
```

## Discord surface and command design

For a public bot, use **slash commands only**. Discord’s interaction model is the right fit for this bot because it avoids privileged Message Content access and gives you strong UX primitives for buttons, follow-ups, and ephemeral subviews. Discord.py also explicitly supports application commands and interaction models, and its docs distinguish these from prefix commands that need `message_content`. citeturn24search1turn24search10turn23search1turn24search0

I would implement this command surface:

- `/fight character_a character_b mode environment prep:true strongest_form_only:true`
- `/sources battle_id`
- `/confidence battle_id`
- `/refresh character franchise`  
  restricted to trusted roles or bot admins

If you want to preserve the retro `!fight` feel, keep a **dev-only prefix bridge** in a single testing guild, not in the public deployment. That gives you convenience without designing the whole bot around a privileged intent.

The response UX should be **summary first, provenance second**. Discord embeds have documented field and aggregate size limits, so do not try to dump the whole referee report into one monster blob. Use:

1. **Primary verdict embed**  
   winner, loser/tie, confidence, decisive factors, canon version labels
2. **Evidence button or `/sources`**  
   paginated evidence cards
3. **Confidence button or `/confidence`**  
   breakdown of evidence coverage, corroboration, contradiction penalties, and model consistency

Discord documents up to **25 embed fields** and **6000 aggregate embed characters** across embeds on a message, so pagination is not optional here; it is the clean design from day one. Also, Discord rate limits are explicitly not meant to be hardcoded, so your HTTP client should respect returned headers and back off on 429s. citeturn13view1turn13view2

For intents, keep the bot lean:

```python
import discord

intents = discord.Intents.default()
intents.message_content = False
intents.members = False
intents.presences = False
intents.typing = False
```

That aligns with Discord.py’s intent guidance and your no-privileged-intents goal. When you eventually move past a few hundred or thousand guilds, swap `Bot` for `AutoShardedBot` so shard behavior is already part of the codebase. Discord’s Gateway docs say `Get Gateway Bot` returns the recommended shard count and session start limits, and Discord.py exposes `AutoShardedBot` directly. Also remember Discord’s documented **1000 IDENTIFY calls per 24 hours** across shards; noisy restart loops are the kind of boss mechanic that wipes runs for stupid reasons. citeturn34search6turn34search2turn33search1turn13view3

## Evidence policy, canon, and confidence

Your source policy should be explicit enough that the bot can refuse bad battles instead of hallucinating them.

### Canon and battle policy

Use this canonical policy:

- Default to the **strongest canonical form or feat of the requested version of the character**
- Do **not** silently compose across alternate continuities, reboots, non-canon events, gag crossovers, or spinoff-only feats unless the user explicitly requests composite rules
- If the “strongest feat” is a clear outlier or is contradicted by the broader vetted profile, mark it as an outlier and exclude it from decisive reasoning unless corroborated
- If a source profile distinguishes forms, versions, timeskips, or transformations, preserve that split rather than merging them

That policy matches how VS Battles itself structures multi-version pages and transformation keys; their profile format explicitly calls out character versions, keys, transformations, and power-up timelines. citeturn32view0

Use this battle policy:

- Both characters are **aware a battle is coming**
- Both are **prepared and battle-ready**
- **Standard equipment** is allowed
- **Standard summons / battle companions** are allowed if they are canonically standard and controllable for the chosen strongest form
- Neutral battlefield unless the user specifies otherwise
- No outside armies, deus ex machina allies, or one-off prep advantages unless those are ordinary parts of the character’s standard battle profile

That gives you a stable arbitration baseline and matches what you described you want.

### Admissible source tiers

I would operationalize evidentiary admissibility like this:

**Tier A**
Official publisher/developer source pages, official game wikis/encyclopedias/manuals/databooks, directly authoritative in-universe or officially published reference material.

**Tier B**
AniList, MyAnimeList, similar database/index sources used for identity, aliases, media linkage, character metadata, and continuity labels. AniList is especially useful here because it has a public GraphQL API and clean request semantics. AniList also documents rate limits and commercial terms, which matters if the bot later becomes monetized. citeturn18view0turn18view1turn31search0turn31search6

**Tier C**
VS Battles Wiki and other fan wikis. These are admissible as structured claim sources and feat pointers, but **they cannot be decisive alone**. VS Battles explicitly presents itself as a community attempt to index character statistics and discusses the validity and reliability of feats, statements, and calculations; that is useful, but it is not the same thing as primary canon. citeturn32view1turn32view2

### Corroboration rules

Use these hard rules:

- A **decisive claim** is any claim that changes the final verdict on speed, attack potency, durability, hax resistance, battlefield control, or win condition.
- A decisive claim from **Tier C** needs corroboration from:
  - one **Tier A** source, or
  - two independent admissible sources with matching details, one of which must not simply copy the same fan-wiki phrasing
- An uncorroborated Tier C claim may appear in a source card as **unverified** but **must not affect the verdict**
- If both fighters hinge on unresolved, uncorroborated claims, the result becomes **insufficient evidence** rather than a fake confident win

That policy gives the bot permission to be rigorous instead of theatrical.

### Evidence cards

Each source card should store:

- `claim_id`
- `claim_text`
- `stat_axis`  
  attack, speed, durability, hax, resistances, range, summons, loadout
- `source_tier`
- `source_title`
- `source_locator`
- `continuity`
- `form_version`
- `corroborated_by[]`
- `decisive: true|false`
- `status: verified|unverified|outlier|contradicted`

The visible Discord card should show only the essentials: claim, source, why it matters, corroboration state, and whether it materially changed the ruling.

### Confidence scoring algorithm

Make confidence mechanical, not vibes:

```text
evidence_score =
  0.35 * corroboration_score +
  0.25 * source_authority_score +
  0.20 * stat_coverage_score +
  0.10 * contradiction_penalty_score +
  0.10 * continuity_clarity_score

model_consistency_score =
  majority agreement across 3 low-temperature referee passes
  using the same evidence packet

final_confidence =
  round(100 * (
    0.60 * evidence_score +
    0.25 * model_consistency_score +
    0.15 * schema_validity_score
  )) - hard_penalties
```

Use these hard penalties:

- `-25` if any decisive claim is single-source fan-wiki only
- `-15` if speed evidence is materially missing
- `-15` if attack/durability evidence is materially missing
- `-20` if canon version/form mapping is ambiguous
- cap at **49** if the verdict depends on unresolved decisive claims
- return **`insufficient_evidence`** if both sides lack decisive validated evidence

This is the kind of confidence model users can actually inspect and argue with, which is exactly what you want for “source cards + confidence score + referee summary.”

## Prompting and structured output

Ollama supports both **structured outputs via JSON Schema** and **tool calling**, and its API also supports a dedicated `think` field and runtime generation controls. LiteLLM also supports JSON-schema style structured output and can front either Ollama or LM Studio with an OpenAI-compatible client surface. LM Studio likewise documents OpenAI-compatible endpoints and JSON-schema structured output support. That means you do **not** need brittle regex parsing for your referee. citeturn27view0turn27view1turn27view2turn27view3turn10search2turn27view4turn28view1

### System prompt

```text
You are FightRef, an evidence-bound battle arbiter.

Your job is to determine a winner, loser, tie, or insufficient_evidence between two fictional characters.

Rules:
- Use only the supplied evidence packet.
- Treat official publisher/developer or official wiki material as highest authority.
- Treat AniList/MyAnimeList metadata as identity/context, not feat proof.
- Treat fan-wiki claims as admissible only when corroborated.
- Use the strongest canonical form or feat of the requested version only.
- Do not silently composite across alternate continuities.
- Assume both fighters are prepared, battle-ready, and have standard equipment.
- Standard summons or battle companions are allowed if included in the evidence packet.
- Reject outliers unless corroborated or clearly identified as standard for the chosen form.
- Never invent feats, scalings, resistances, or cosmology.
- Do not output chain-of-thought.
- Output valid JSON matching the provided schema only.
```

### User prompt template

```text
Arbitrate a fight.

Character A: {character_a}
Character B: {character_b}

Battle rules:
- strongest canonical form only
- prep enabled
- standard equipment allowed
- standard summons allowed
- neutral battlefield
- no composite continuities unless explicitly marked

Evidence packet:
{normalized_evidence_json}

Return:
- matchup_summary
- decisive_factors
- per-axis comparison
- evidence_cards_used
- verdict
- confidence_breakdown
- missing_or_contested_points
```

### JSON schema

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": [
    "match_id",
    "character_a",
    "character_b",
    "canon_scope",
    "battle_assumptions",
    "axis_comparison",
    "decisive_factors",
    "verdict",
    "confidence",
    "evidence_cards_used",
    "missing_or_contested_points"
  ],
  "properties": {
    "match_id": { "type": "string" },
    "character_a": {
      "type": "object",
      "required": ["name", "version", "form"],
      "properties": {
        "name": { "type": "string" },
        "version": { "type": "string" },
        "form": { "type": "string" }
      },
      "additionalProperties": false
    },
    "character_b": {
      "type": "object",
      "required": ["name", "version", "form"],
      "properties": {
        "name": { "type": "string" },
        "version": { "type": "string" },
        "form": { "type": "string" }
      },
      "additionalProperties": false
    },
    "canon_scope": { "type": "string" },
    "battle_assumptions": {
      "type": "array",
      "items": { "type": "string" }
    },
    "axis_comparison": {
      "type": "object",
      "required": ["attack", "speed", "durability", "hax", "range", "summons_loadout"],
      "properties": {
        "attack": { "type": "string" },
        "speed": { "type": "string" },
        "durability": { "type": "string" },
        "hax": { "type": "string" },
        "range": { "type": "string" },
        "summons_loadout": { "type": "string" }
      },
      "additionalProperties": false
    },
    "decisive_factors": {
      "type": "array",
      "items": { "type": "string" }
    },
    "verdict": {
      "type": "object",
      "required": ["result", "winner", "reasoning_summary"],
      "properties": {
        "result": {
          "type": "string",
          "enum": ["character_a", "character_b", "tie", "insufficient_evidence"]
        },
        "winner": { "type": ["string", "null"] },
        "reasoning_summary": { "type": "string" }
      },
      "additionalProperties": false
    },
    "confidence": {
      "type": "object",
      "required": ["score", "tier", "evidence_score", "consistency_score", "penalties"],
      "properties": {
        "score": { "type": "integer", "minimum": 0, "maximum": 100 },
        "tier": { "type": "string" },
        "evidence_score": { "type": "number" },
        "consistency_score": { "type": "number" },
        "penalties": {
          "type": "array",
          "items": { "type": "string" }
        }
      },
      "additionalProperties": false
    },
    "evidence_cards_used": {
      "type": "array",
      "items": { "type": "string" }
    },
    "missing_or_contested_points": {
      "type": "array",
      "items": { "type": "string" }
    }
  }
}
```

### Sample JSON output

```json
{
  "match_id": "fight_20260608_01",
  "character_a": {
    "name": "Character A",
    "version": "Mainline canon",
    "form": "Strongest canonical form"
  },
  "character_b": {
    "name": "Character B",
    "version": "Mainline canon",
    "form": "Strongest canonical form"
  },
  "canon_scope": "Mainline continuity only; no composite feats used.",
  "battle_assumptions": [
    "Prepared combatants",
    "Standard equipment allowed",
    "Standard summons allowed",
    "Neutral battlefield"
  ],
  "axis_comparison": {
    "attack": "Character A holds a corroborated edge.",
    "speed": "Character B has better raw movement but weaker corroboration.",
    "durability": "Character A scales more consistently.",
    "hax": "Character B has better utility but weaker decisive coverage.",
    "range": "Roughly comparable.",
    "summons_loadout": "Character A standard loadout is better documented."
  },
  "decisive_factors": [
    "Character A has stronger corroborated attack and durability evidence",
    "Character B speed edge is not decisive after evidence weighting"
  ],
  "verdict": {
    "result": "character_a",
    "winner": "Character A",
    "reasoning_summary": "Character A wins by more reliable decisive evidence across AP and durability, with fewer canon ambiguities."
  },
  "confidence": {
    "score": 78,
    "tier": "moderate_high",
    "evidence_score": 0.81,
    "consistency_score": 0.74,
    "penalties": [
      "One fan-wiki speed claim was excluded as uncorroborated"
    ]
  },
  "evidence_cards_used": [
    "src_14",
    "src_22",
    "src_24"
  ],
  "missing_or_contested_points": [
    "Character B strongest speed feat remains contested"
  ]
}
```

## Refresh and ingestion mode

This project needs **two modes**, not one:

- **Arbitration mode**  
  fully offline against your local Postgres evidence store
- **Refresh/research mode**  
  operator-triggered profile building for missing characters

That separation is the difference between a stable referee and a hallucination casino.

### Why refresh mode should be operator-driven

AniList’s API is documented and rate-limited, and its terms explicitly allow low-revenue commercial use without separate permission below the documented threshold. VS Battles, by contrast, sits on Fandom, and Fandom’s Terms of Use prohibit scraping/indexing portions of the content and prohibit copying content for AI-software development without prior written consent. So if you want a public-facing project that survives contact with reality, **do not build an autonomous VS Battles scraper as the backbone of refresh mode**. Use AniList and official sources programmatically where permitted, then use an **operator review step** for VS Battles or other fan-wiki content. citeturn18view0turn18view1turn31search0turn31search6turn21search1

### Recommended refresh workflow

1. **Resolve identity and continuity**
   - fetch AniList metadata
   - create aliases
   - map franchise/series/version labels

2. **Collect authoritative canon sources**
   - official publisher/developer profile pages
   - official wikis/manuals/databooks
   - official move/loadout pages for games

3. **Collect fan-wiki structured claims**
   - enter VS Battles claims manually or via human-reviewed import
   - mark every such claim `source_tier = C`

4. **Corroborate decisive claims**
   - promote only corroborated decisive claims to `verified`
   - demote the rest to `unverified`

5. **Build a normalized strongest-form profile**
   - per axis: attack, speed, durability, hax, range, summons/loadout
   - version and form labels required

6. **Approve profile for arbitration**
   - set `character_version.status = vetted`

### Minimal AniList metadata ingest script

AniList documents GraphQL requests as `POST` to `https://graphql.anilist.co`, with `query` and `variables`, and publishes rate-limit behavior. This is safe to automate inside refresh mode. citeturn18view1turn31search0

```python
# ingest/anilist_lookup.py
import requests
import sys

QUERY = """
query($search: String) {
  Character(search: $search) {
    id
    name {
      full
      native
      alternative
    }
    image {
      large
    }
    media(perPage: 10) {
      nodes {
        id
        title {
          romaji
          english
          native
        }
        type
      }
    }
  }
}
"""

def lookup_character(name: str) -> dict:
    r = requests.post(
        "https://graphql.anilist.co",
        json={"query": QUERY, "variables": {"search": name}},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["data"]["Character"]

if __name__ == "__main__":
    print(lookup_character(sys.argv[1]))
```

### Manual review file for fan-wiki claims

Because of the legal and provenance issues above, use a manual review YAML for VS Battles/fan-wiki inputs instead of raw scraping:

```yaml
character: "Example Character"
version: "Mainline canon"
form: "Strongest canonical form"
claims:
  - axis: attack
    text: "Planet-level feat from profile summary"
    source_title: "VS Battles profile"
    source_locator: "profile URL"
    source_tier: "C"
    decisive: true
    corroborated_by: []
    status: "unverified"

  - axis: speed
    text: "FTL travel/reaction scaling from accepted calc"
    source_title: "VS Battles calc page"
    source_locator: "calc URL"
    source_tier: "C"
    decisive: true
    corroborated_by:
      - "official wiki page URL"
    status: "verified"
```

### Dockerized refresh commands

```bash
# lookup metadata
docker compose run --rm worker python -m ingest.anilist_lookup "Character Name"

# validate/manual import of reviewed claims
docker compose run --rm worker python -m ingest.import_profile ./profiles/character_name.yaml

# rebuild normalized strongest-form profile
docker compose run --rm worker python -m ingest.normalize_profile "Character Name"
```

That division of labor is slower than a reckless web scraper, but it gives you something much more valuable: **traceable verdicts**.

## Deployment, security, and operations

### Supported runtime choices

**Ollama** is the best first choice for a fully Dockerized local stack. Ollama publishes official Docker guidance for CPU and NVIDIA GPU serving, its Windows docs say it runs natively on Windows at `http://localhost:11434`, and its FAQ says Docker GPU acceleration is supported on Linux and on Windows with WSL2. If you want the fewest weird edge cases, either run the whole stack in Docker with WSL2-backed GPU support, or run Ollama natively on Windows and keep the rest containerized. citeturn39search16turn39search4turn39search6

**LiteLLM** belongs in front of Ollama. Its docs cover Docker, config-driven model aliases, model routing to Ollama, master keys, virtual keys, budgets/rate limits, Redis/DB-aware request handling, and an OpenAI-compatible API surface. That gives you one stable client interface regardless of whether the backend is Ollama today or LM Studio tomorrow. citeturn29view2turn40view1turn40view2turn30search0turn30search1

**LM Studio** is usable, but the official docs emphasize **headless `llmster`/`lms`** and OpenAI-compatible local endpoints, not a first-party Docker image. So I would treat LM Studio as a **host-native alternative**, not the primary Dockerized production path. citeturn28view0turn28view1turn28view2turn28view4

### Exact install and run commands

The officially documented Ollama NVIDIA Docker path is:

```bash
docker volume create ollama

docker run -d \
  --gpus=all \
  --restart unless-stopped \
  -v ollama:/root/.ollama \
  -p 11434:11434 \
  --name ollama \
  ollama/ollama
```

Then pull models:

```bash
docker exec -it ollama ollama pull qwen3:8b
docker exec -it ollama ollama pull deepseek-r1:8b
docker exec -it ollama ollama pull qwen3:14b
```

And smoke-test:

```bash
curl http://localhost:11434/api/generate -d '{
  "model": "qwen3:8b",
  "prompt": "Return JSON {\"ok\":true}",
  "stream": false,
  "format": "json"
}'
```

Those commands follow Ollama’s documented Docker and API paths. citeturn39search16turn39search18turn27view1

A minimal LiteLLM Docker run is:

```bash
docker run \
  --restart unless-stopped \
  -v $(pwd)/config/litellm_config.yaml:/app/config.yaml \
  -e LITELLM_MASTER_KEY=sk-change-me \
  -p 4000:4000 \
  docker.litellm.ai/berriai/litellm:main-latest \
  --config /app/config.yaml
```

LiteLLM’s docs also show a Compose-based DB-backed deployment that adds UI, virtual keys, and persisted configuration. citeturn41view0turn40view1

For LM Studio headless on the host, the official commands are:

```bash
curl -fsSL https://lmstudio.ai/install.sh | bash
lms daemon up
lms server start --port 1234 --bind 127.0.0.1
```

And its OpenAI-compatible base URL is:

```text
http://localhost:1234/v1
```

That is the officially documented path; I would not invent an unsupported LM Studio container recipe for production. citeturn28view0turn28view1turn28view2

### Docker Compose example

Docker Compose supports GPU reservations, and Docker’s docs require `capabilities: [gpu]` on the device reservation. Docker Compose secrets are mounted under `/run/secrets/<name>`, which is the right place for your Discord token and DB password. citeturn26view0turn26view1turn26view2

```yaml
services:
  postgres:
    image: postgres:16
    restart: unless-stopped
    environment:
      POSTGRES_DB: battlebot
      POSTGRES_USER: battlebot
      POSTGRES_PASSWORD_FILE: /run/secrets/postgres_password
    secrets:
      - postgres_password
    volumes:
      - pgdata:/var/lib/postgresql/data

  redis:
    image: redis:7
    restart: unless-stopped
    command: ["redis-server", "--appendonly", "yes", "--appendfsync", "everysec"]
    volumes:
      - redisdata:/data

  ollama:
    image: ollama/ollama:latest
    restart: unless-stopped
    ports:
      - "127.0.0.1:11434:11434"
    volumes:
      - ollama:/root/.ollama
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]

  litellm:
    image: docker.litellm.ai/berriai/litellm:main-latest
    restart: unless-stopped
    depends_on:
      - postgres
      - redis
      - ollama
    ports:
      - "127.0.0.1:4000:4000"
    environment:
      LITELLM_MASTER_KEY: ${LITELLM_MASTER_KEY}
      DATABASE_URL: postgresql://battlebot:${POSTGRES_PASSWORD}@postgres:5432/battlebot
    volumes:
      - ./config/litellm_config.yaml:/app/config.yaml:ro
    command: ["--config", "/app/config.yaml"]

  bot:
    build: ./bot
    restart: unless-stopped
    depends_on:
      - redis
      - postgres
      - litellm
    environment:
      DATABASE_URL: postgresql://battlebot:${POSTGRES_PASSWORD}@postgres:5432/battlebot
      REDIS_URL: redis://redis:6379/0
      LITELLM_BASE_URL: http://litellm:4000
      DISCORD_APPLICATION_ID: ${DISCORD_APPLICATION_ID}
      DISCORD_GUILD_SYNC_ID: ${DISCORD_GUILD_SYNC_ID}
    secrets:
      - discord_token

  worker:
    build: ./worker
    restart: unless-stopped
    depends_on:
      - redis
      - postgres
      - litellm
    environment:
      DATABASE_URL: postgresql://battlebot:${POSTGRES_PASSWORD}@postgres:5432/battlebot
      REDIS_URL: redis://redis:6379/0
      LITELLM_BASE_URL: http://litellm:4000
      REFEREE_MODEL: referee-default

secrets:
  discord_token:
    file: ./secrets/discord_token.txt
  postgres_password:
    file: ./secrets/postgres_password.txt

volumes:
  pgdata:
  redisdata:
  ollama:
```

### LiteLLM config example

LiteLLM documents Ollama routing through `ollama_chat/...` model names and supports JSON-schema style response formatting. citeturn29view1turn29view2

```yaml
model_list:
  - model_name: referee-default
    litellm_params:
      model: ollama_chat/qwen3:8b
      api_base: http://ollama:11434

  - model_name: referee-reasoning
    litellm_params:
      model: ollama_chat/deepseek-r1:8b
      api_base: http://ollama:11434

  - model_name: referee-detail
    litellm_params:
      model: ollama_chat/qwen3:14b
      api_base: http://ollama:11434

general_settings:
  master_key: sk-change-me
  database_url: postgresql://battlebot:change-me@postgres:5432/battlebot
```

### Step-by-step zero-to-running walkthrough

1. **Install Docker and NVIDIA GPU runtime**
   - Install Docker Desktop or Docker Engine.
   - Install NVIDIA Container Toolkit if needed.
   - Verify GPU passthrough with a CUDA container.
   - Docker and NVIDIA document GPU-enabled container setup and runtime configuration. citeturn39search1turn39search9turn26view0

2. **Create repo structure**
   ```text
   battlebot/
     bot/
     worker/
     config/
     secrets/
     profiles/
     docker-compose.yml
     .env
   ```

3. **Create secrets**
   ```bash
   printf '%s' 'YOUR_DISCORD_BOT_TOKEN' > secrets/discord_token.txt
   printf '%s' 'CHANGE_ME_DB_PASSWORD' > secrets/postgres_password.txt
   chmod 600 secrets/*.txt
   ```

4. **Create `.env`**
   ```bash
   cat > .env <<'EOF'
   LITELLM_MASTER_KEY=sk-change-me
   POSTGRES_PASSWORD=CHANGE_ME_DB_PASSWORD
   DISCORD_APPLICATION_ID=YOUR_APP_ID
   DISCORD_GUILD_SYNC_ID=YOUR_DEV_GUILD_ID
   EOF
   ```

5. **Write `docker-compose.yml` and `config/litellm_config.yaml`**
   - Use the examples above.

6. **Start infrastructure**
   ```bash
   docker compose up -d postgres redis ollama litellm
   ```

7. **Pull models**
   ```bash
   docker exec -it $(docker compose ps -q ollama) ollama pull qwen3:8b
   docker exec -it $(docker compose ps -q ollama) ollama pull deepseek-r1:8b
   ```

8. **Smoke-test the model and gateway**
   ```bash
   curl http://localhost:11434/api/generate -d '{
     "model":"qwen3:8b",
     "prompt":"Say pong",
     "stream":false
   }'

   curl -X POST http://localhost:4000/chat/completions \
     -H "Authorization: Bearer sk-change-me" \
     -H "Content-Type: application/json" \
     -d '{
       "model":"referee-default",
       "messages":[{"role":"user","content":"Say pong"}]
     }'
   ```

9. **Build and start bot and worker**
   ```bash
   docker compose up -d --build bot worker
   ```

10. **Sync slash commands in a dev guild**
    - Start with guild-only command sync in a test server.
    - Once stable, sync global commands.

11. **Invite bot with minimal scopes**
    - `bot`
    - `applications.commands`

12. **Run first fight**
    - `/fight character_a:... character_b:... mode:standard`

### Backups, monitoring, and CI/CD

For backups, do **nightly Postgres dumps** and volume snapshots. PostgreSQL documents `pg_dump` as producing consistent exports even if the DB is being used concurrently. For Redis, enable persistence with **AOF**; Redis documents AOF with `fsync every second` as the default durability/performance balance. That is enough for this project’s queue and cooldown state. citeturn20search0turn20search1turn20search4

For monitoring, add **Prometheus** and **cAdvisor**. Prometheus documents container installation, and cAdvisor exposes Prometheus metrics for container resource usage. At minimum, monitor:

- queue depth
- inference duration
- model load duration
- battle failure rate
- Discord API 429 count
- worker restarts
- Postgres latency
- container CPU/RAM disk growth citeturn19search2turn19search10turn20search5turn20search17

For CI/CD, keep it simple:

- **CI on every PR**
  - Ruff / black / mypy / pytest
  - JSON schema tests
  - prompt snapshot tests
  - `docker compose config` validation
- **CD on tag**
  - build bot and worker images
  - push to registry
  - deploy with `docker compose pull && docker compose up -d`
  - run DB migrations first

Pin image tags for LiteLLM and Postgres. Do not auto-bump your inference stack blind; model/runtime drift is how you get stealth nerfs in the middle of ranked season.

### Launch checklist for public rollout

- [ ] Slash commands only in production
- [ ] `message_content` disabled
- [ ] Redis queue in place
- [ ] Discord responses deferred immediately
- [ ] Result delivery safe if queue exceeds 15 minutes
- [ ] `qwen3:8b` set as default model
- [ ] `deepseek-r1:8b` available as opt-in reasoning mode
- [ ] 14B models disabled by default
- [ ] Evidence cards implemented
- [ ] Confidence algorithm visible to users
- [ ] Fan-wiki decisive claims blocked unless corroborated
- [ ] Manual/operator review path for VS Battles ingestion
- [ ] Ollama and LiteLLM bound to localhost or internal Docker network only
- [ ] Discord token and DB password loaded from Docker secrets
- [ ] Postgres backup job scheduled
- [ ] Prometheus/cAdvisor or equivalent metrics enabled
- [ ] Dev-guild command sync tested before global sync
- [ ] AutoShardedBot or shard-ready code path prepared
- [ ] Per-user and per-guild queue limits enforced
- [ ] Abuse controls for `/refresh` restricted to admins

### Open questions and limitations

The biggest incomplete area is **official-game-wiki coverage across “any anime or game character”**. Some franchises have excellent official databases; some do not. That means your long-term quality ceiling depends less on the LLM and more on the **profile ingestion pipeline** and how disciplined you are about source vetting.

The other practical limit is throughput. A single RTX 4070 SUPER can support a public bot with a queue, but it is not a true multi-tenant inference cluster. If the bot becomes popular enough that fights are piling up across many servers at once, the next upgrade is **another worker host or a second GPU**, not increasingly cursed prompt alchemy.

The cleanest initial build, using the evidence above, is:

**Ollama + LiteLLM + Postgres + Redis + discord.py slash commands + operator-reviewed refresh mode + Qwen3 8B default referee.** citeturn39search16turn40view2turn35view0turn13view0turn24search1turn21search1