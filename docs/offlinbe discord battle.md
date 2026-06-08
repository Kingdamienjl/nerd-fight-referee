# Offline Discord Battle Referee Blueprint

## Recommended direction

Build this as an **offline-first, evidence-gated Discord slash-command bot** with a **deterministic policy engine** in front of a **local OpenAI-compatible model server**. The winning pattern is not “ask a model who wins”; it is “resolve both characters, fetch only whitelisted database/wiki evidence, normalize the evidence into structured claims, apply your canon and battle policies deterministically, then let a local model write the referee summary from the filtered claim packet.” That architecture lines up with Discord’s current direction toward application commands, avoids message-content intent from day one, and cleanly supports long-running battle jobs by deferring the interaction and editing the response later. Discord explicitly positions application commands as the primary interaction model because message content is privileged at scale, and interaction tokens must be acknowledged within 3 seconds while followups remain valid for 15 minutes. Docker Compose is built for this kind of multi-service stack, and Ollama already exposes structured outputs for schema-constrained local inference. citeturn36view0turn36view1turn37view1turn37view2

My concrete recommendation is to start with **Python + Docker Compose + Postgres/pgvector + Redis Streams + Ollama**. Use **slash commands only**, not prefix commands, and treat the LLM as a **referee writer plus claim comparator**, not as the source of truth. For local models, the practical starting tiers are: **Qwen3 8B** if the machine is modest; **Qwen3 14B** or **DeepSeek-R1 14B** if you have a stronger GPU; and **DeepSeek-R1 32B** only if you have genuinely large VRAM headroom. Qwen3 officially supports hybrid thinking/non-thinking modes, while DeepSeek-R1 is positioned as an open reasoning family. In Ollama’s current Q4_K_M builds, Qwen3 8B is about **5.2 GB**, Qwen3 14B about **9.3 GB**, DeepSeek-R1 14B about **9.0 GB**, and DeepSeek-R1 32B about **20 GB**; Qwen3 Embedding is also available locally at about **4.7 GB**. I cannot honestly lock your exact model tier beyond that, because your actual PC specs are not present in this chat context. citeturn40search0turn40search11turn28view0turn30view0turn26view1turn32view0turn26view2

## Rules that should govern verdicts

Your **canon policy** should be stricter than “strongest feat wins.” A good default is: use the **strongest canon form or key** the character can normally access by their own means, but only allow a **strongest feat** to decide a match if it is **not an obvious outlier**, **not purely a game-mechanics artifact**, and **not supported only by an uncited fan-wiki assertion**. That is close to the underlying logic battle communities already use: VS Battles defines canon as genuine verse material, defaults to the strongest listed canon version, treats outliers as potentially unusable if irreconcilable, and explicitly warns that game mechanics are not automatically indicative of true ability. In other words, “strongest form” is a sound default; “single highest thing ever shown once” is not, unless it survives consistency checks. citeturn19view0turn33search0turn33search2turn33search1

Your **battle policy** should intentionally diverge from standard versus-thread defaults. VS Battles’ standard assumptions use **no prep time**, **standard equipment**, a minimal amount of opponent knowledge, and allow things listed as part of the character’s own powers such as familiars or summons. That is useful as a reference point precisely because you want a different default: not random-state teleport combat, but **prepared ready-state combat**. The clean version of that rule is: both fighters know a battle is imminent, both begin mentally ready, both may enter their strongest canon form, both get **standard equipment**, and both get **standard summons or familiars** if those are normally available as part of their own kit. They do **not** get outside support from non-participants, one-off crossover amps, or opponent-specific counter-prep unless that kind of targeted preparation is itself a standard part of their canon combat behavior. citeturn19view3turn19view4turn19view5turn17view2turn17view3

Your **evidence policy** is the part that makes the bot trustworthy. Keep verdict generation restricted to **admissible databases and admissible wikis only**, and make a hard rule that **a single uncited fan-wiki claim can never be decisive on its own**. That rule is justified by the sources themselves: Bulbapedia says it makes **no guarantee of validity or accuracy**, Super Mario Wiki likewise says the wiki makes **no guarantee of validity**, and both Bulbapedia and Zelda Wiki maintain explicit citation/reference guidance because citations matter for factual reliability. So the policy should read like this: database facts can establish identity, continuities, aliases, and release chronology; wiki claims can establish battle evidence only when they are either corroborated by a second admissible source, backed by inline references on the same page, or otherwise consistent with the surrounding canonical evidence. If that corroboration is missing, the bot should downgrade confidence or return **inconclusive**, not guess. citeturn12search12turn20search0turn21search7turn21search5turn13search12

One more policy matters because this bot will eventually become a citation machine: **license-aware caching**. Wikidata’s structured data is available under **CC0**, which is friendly for storage and reuse; Bulbapedia’s original content is **CC BY-NC-SA**; Fandom text is generally **CC BY-SA**; and Zelda Wiki content is under **GFDL 1.3**. So architect the system to store raw fetches internally for reproducibility, but publicly display only short excerpts, source cards, and links unless you have confirmed that your reuse is compatible with the source’s license and your deployment model. citeturn38view1turn12search0turn12search3turn13search8turn13search9

## Source and evidence architecture

For a broad “any anime or game character” bot, use **databases for identity** and **wikis for feats**, not the other way around. A solid base layer is: **AniList** for anime/manga metadata and characters, **IGDB** for game/franchise identity, and **Wikidata** for cross-source identifiers and alias resolution. AniList’s GraphQL API exposes anime, manga, character, staff, and airing data; IGDB provides a formal API with OAuth-based authentication; and Wikidata now has a versioned REST API tailored to items and statements. This gives you a neutral entity-resolution backbone before you touch verse-specific lore pages. citeturn38view0turn37view7turn38view1

Most of the wiki layer can be standardized through **MediaWiki adapters**. MediaWiki’s Action API provides the `api.php` endpoint pattern, and the revisions module can fetch the latest revision by page, a revision range, or a specific revision ID. That matters because reproducibility is everything in battle verdicts: when the bot cites a page, it should save the **page title, source domain, revision or retrieval timestamp, extracted quote, and normalized claim**. For independent or Fandom-hosted wikis that still speak MediaWiki cleanly, your ingest path can remain largely uniform. For the long tail of weird wikis, you add custom HTML adapters, but the normalized output should remain the same. citeturn37view4turn37view5

The internal data model should revolve around **Claim**, not “document chunk.” A `Claim` should carry at least: `character_id`, `form_key`, `claim_type`, `claim_value`, `quote_or_snippet`, `source_domain`, `source_title`, `source_revision`, `corroboration_count`, `evidence_weight`, and `policy_flags` such as `outlier_risk`, `game_mechanics_risk`, and `uncited_fanwiki`. That lets you compute a real confidence score instead of a vibes score. My suggestion is to score confidence from five dimensions: **source quality**, **corroboration**, **matchup coverage**, **contradiction penalty**, and **model agreement**. The LLM should never invent that score; it should receive the computed sub-scores and summarize them. That is exactly the kind of workflow schema-constrained local outputs are good at. citeturn37view2turn37view3turn39search1

A minimal result contract worth scaffolding now looks like this:

```json
{
  "winner": "character_a | character_b | tie | inconclusive",
  "confidence": 0.0,
  "mode": "offline | refresh",
  "policy_applied": {
    "canon": "strongest_consistent_canon_form",
    "prep": "prepared_ready_state",
    "equipment": "standard",
    "summons": true,
    "outside_help": false
  },
  "profiles": [
    {
      "name": "string",
      "resolved_source_ids": ["string"],
      "selected_form": "string",
      "claim_summary": {
        "attack_potency": "string",
        "speed": "string",
        "durability": "string",
        "abilities": ["string"],
        "resistances": ["string"],
        "range": "string",
        "equipment": ["string"],
        "summons": ["string"]
      }
    }
  ],
  "evidence_cards": [
    {
      "claim": "string",
      "supports": "character_a | character_b | both | neither",
      "source": "string",
      "revision": "string",
      "corroborated": true,
      "impact": "high | medium | low"
    }
  ],
  "referee_summary": "string"
}
```

## Runtime stack and model recommendations

The clean stack is a **gateway service**, a **battle worker**, an **ingest/refresh worker**, **Postgres with pgvector**, **Redis Streams**, and a **local model server**. pgvector keeps vectors in Postgres and supports nearest-neighbor search while preserving the normal strengths of Postgres such as joins and transactional integrity; Redis Streams gives you an append-only log plus consumer-group semantics that are a good fit for deferred interaction jobs and refresh pipelines. Put the whole thing behind Docker Compose so the bot, queue, database, and model server come up together as one stack. citeturn37view8turn37view9turn37view1

For the local inference layer, start with **Ollama**. It has an official Docker path, runs models locally, exposes the API on **11434**, and supports structured outputs via JSON schema. Keep your application talking to it through an **OpenAI-compatible provider interface** so you can swap backends later without rewriting the battle engine. If you outgrow Ollama, the two sane upgrade paths are **vLLM** for higher-throughput GPU serving and **llama.cpp** for lightweight GGUF serving on constrained hardware; both expose OpenAI-compatible server interfaces, and vLLM also supports structured outputs in its OpenAI-compatible server. citeturn37view0turn37view2turn37view3turn39search1turn39search3

For model choice, I would not ship a single-model architecture. The best production pattern is a **small extractor + referee** split. Use **Qwen3 Embedding** for retrieval, then either **Qwen3 14B** or **DeepSeek-R1 14B** as the referee model. If the machine is smaller, start with **Qwen3 8B** as both extractor and referee and accept that close battles will need more conservative confidence thresholds. Qwen3’s hybrid thinking is handy because you can keep normal retrieval/extraction fast and switch into deeper reasoning only for close or contradictory matchups. DeepSeek-R1 is attractive when the decisive factor is longer logical comparison rather than tool use or concise formatting. citeturn26view2turn30view0turn26view1turn28view0turn40search0turn40search11

A practical hardware envelope, based on the currently published Q4 model sizes, is this: **under 16 GB VRAM, build for 8B first**; **16–24 GB VRAM, target 14B**; **24 GB+ VRAM, test 32B if latency is acceptable**. Those are deployment heuristics, not hard vendor guarantees, because the published sizes are the weight files and real serving also needs KV cache, runtime overhead, and room for the rest of the stack. If your personal PC ends up being the smaller tier, do not let that derail the project. This bot will live or die by evidence quality and policy enforcement far more than by squeezing in an extra 18 billion parameters. citeturn28view0turn30view0turn32view0turn26view2

## Discord UX and transparency

Use **application commands only**. Discord explicitly recommends moving toward interaction options rather than message-content-based usage, and application commands are the main app entry points now. You can receive interactions either through the **gateway** or via an **outgoing webhook**; those two paths are mutually exclusive. For a personal-PC deployment, the **gateway path** is simpler because it avoids having to expose a public Interactions Endpoint URL. The bot should immediately defer the command, enqueue the battle job, and then edit the original response when the worker finishes. citeturn36view0turn22view2turn36view1

The response UX should be split into three layers: a **verdict card**, a **comparison card**, and **source cards**. Discord embeds support rich structured fields, but each embed is capped and fields max out at 25, so paginate source cards instead of trying to jam every snippet into one payload. Use buttons or select menus for “Sources,” “Why this verdict,” and “Refresh evidence,” because Discord’s component system is built for exactly this kind of interaction. You have more than enough command budget to support this cleanly, since apps can register up to 100 global slash commands and options can use autocomplete. citeturn36view5turn36view6turn36view7

A good default response should show: **winner**, **confidence**, **selected canon form for each side**, **top decisive factors**, and **the three highest-impact evidence cards**. Then a secondary component action can show the fuller evidence trail. This preserves readability while still giving users the receipts. If the evidence is thin, say so explicitly with a visible label such as **Low confidence** or **Inconclusive due to insufficient corroborated evidence**. In this niche, honest uncertainty is a feature, not a bug. citeturn36view5turn36view6

## Development and Docker deployment walkthrough

Scaffold the repo as a **single monorepo** with one language and clear package boundaries. Python is the easiest fit here because your scrape/parse/RAG stack will be easier to maintain if the gateway, worker, and ingest services all share the same models and claim schemas.

```text
battle-bot/
  apps/
    discord_gateway/
    battle_worker/
    ingest_worker/
    admin_api/
  packages/
    entities/
    sources/
    claims/
    verdict_engine/
    llm_provider/
    discord_views/
  infra/
    docker/
    compose/
    postgres/
  tests/
    fixtures/
    golden_battles/
```

Build order matters. Do it in this order so the scaffolding agent does not waste mana on the wrong boss phase:

- **Phase A**: define the schemas first: `Entity`, `Profile`, `Claim`, `EvidenceCard`, `BattleRequest`, `BattleResult`.
- **Phase B**: implement the source registry and adapters for **AniList**, **IGDB**, **Wikidata**, and **MediaWiki**.
- **Phase C**: implement the policy engine: canon selection, outlier rejection, game-mechanics filtering, prepared-battle defaults, standard equipment, and summons.
- **Phase D**: add Postgres/pgvector persistence and Redis Streams job handling.
- **Phase E**: add the local LLM provider and schema-constrained referee output.
- **Phase F**: add Discord slash commands, deferred replies, embeds, and component-driven source cards. citeturn38view0turn37view7turn38view1turn37view4turn37view5turn37view8turn37view9turn36view0turn36view1

The runtime flow should look like this:

```text
Discord slash command
  -> gateway service
  -> defer reply within 3s
  -> enqueue job in Redis Streams
  -> worker resolves entities
  -> worker fetches/caches whitelisted sources
  -> worker normalizes claims
  -> policy engine filters evidence
  -> local model writes structured referee result
  -> gateway edits original Discord response
```

Your first Docker Compose file should include **gateway**, **worker**, **ingest**, **postgres**, **redis**, and **ollama**. Docker Compose is specifically meant for defining and running multi-container apps from one YAML file, and Ollama documents a containerized local deployment path directly. If this personal PC is Windows-based and you want GPU containers, Docker Desktop’s GPU support is available only on **Windows with the WSL2 backend**, so plan around that from day one rather than discovering it after you wire the stack. citeturn37view1turn37view0turn37view10

A minimal Compose sketch is enough for scaffolding:

```yaml
services:
  gateway:
    build: ./apps/discord_gateway
    env_file: .env
    depends_on: [redis, postgres, ollama]

  worker:
    build: ./apps/battle_worker
    env_file: .env
    depends_on: [redis, postgres, ollama]

  ingest:
    build: ./apps/ingest_worker
    env_file: .env
    depends_on: [redis, postgres]

  postgres:
    image: pgvector/pgvector:pg17
    environment:
      POSTGRES_DB: battlebot
      POSTGRES_USER: battlebot
      POSTGRES_PASSWORD: battlebot
    volumes:
      - pgdata:/var/lib/postgresql/data

  redis:
    image: redis:7

  ollama:
    image: ollama/ollama
    ports:
      - "11434:11434"
    volumes:
      - ollama:/root/.ollama

volumes:
  pgdata:
  ollama:
```

From there, pre-load a tiny golden test set before you ever open the bot to the public. Pick about twenty famous cross-verse matchups where the conclusion should be obvious, another twenty where the right answer should be **inconclusive**, and at least ten cases designed to trigger your rule filters for **outliers**, **game mechanics**, and **unsupported fan-wiki claims**. If the bot cannot consistently refuse bad evidence, it is not production-ready no matter how pretty the Discord embeds look. citeturn33search1turn33search2turn12search12turn20search0

## Open questions and limitations

The main unresolved variable is **your actual host hardware**. I do not have your GPU model, VRAM, RAM, CPU, or operating system in this chat context, so I cannot truthfully lock the final referee model tier more tightly than the published size envelopes above.

There is also a **source-license and commercialization** question. IGDB documents different terms for non-commercial and commercial use, and your wiki sources do not all share the same license. If you plan to monetize the bot, sell premium access, or redistribute more than short excerpts, review each source’s terms before you finalize the ingest/cache strategy. citeturn37view7turn12search0turn12search3turn13search9turn38view1

The other practical limit is **interaction timing**. Discord gives you 3 seconds for the initial acknowledgement and about 15 minutes for followups using the interaction token. That is fine for normal cached battles and moderate refresh jobs, but a very heavy live refresh across multiple long-tail wikis can still overrun the window. The bot should therefore prefer cached evidence, cap refresh scope, and persist full results in your own database so they can be reopened or replayed if needed. citeturn36view1

If you follow the architecture above, the project stays honest to your rules: **broad character coverage, strongest consistent canon form, prepared battle defaults, standard equipment and summons, database/wiki-only evidence, and transparency through source cards plus confidence scores**. That is the version of this bot that can actually survive contact with power-scalers instead of getting one-shot by its own hallucinations.