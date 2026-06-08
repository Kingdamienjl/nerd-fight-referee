# Offline Discord Battle Bot for Anime and Game Characters

## Executive recommendation

Build this as a **citation-first local battle engine**, not as a freeform chatbot that “knows” fictional powers. The durable version is: a curated character-feat database, a retrieval layer that fetches only the relevant evidence for the requested matchup, and a judge model that must emit a strict verdict object. For a Docker-first Discord bot, the strongest starting stack is a slash-command bot, a worker queue, PostgreSQL with pgvector for hybrid retrieval, and a local model server. If your host can handle a larger local model, **Qwen3.6-35B-A3B** is the best current fit from the options reviewed because its official materials emphasize reasoning and tool use, and the model is documented for production serving with vLLM. If you need a lighter box, **DeepSeek-R1-0528-Qwen3-8B** or **DeepSeek-R1-Distill-Qwen-14B** are the best budget reasoning tiers. citeturn37view6turn37view11turn39view1turn38view0

For the model runner, use **Ollama** if you want the least-friction path: it has an official Docker image, supports structured outputs, and exposes a separate thinking field for thinking-capable models. Move to **vLLM** when concurrency and throughput matter, since vLLM ships an official Docker image with an OpenAI-compatible server, and Qwen’s own model guidance recommends dedicated serving engines like vLLM for production or high-throughput workloads. citeturn19view10turn41search0turn41search2turn19view11turn24search6

If you later want a hosted “research mode” or a cloud fallback, keep your verdict contract provider-agnostic. **LM Studio** can reuse existing OpenAI clients by changing the base URL to its local server, and OpenAI’s **Responses API** supports the same general pattern on the hosted side: structured outputs, tool use, file search, and web search. That lets you keep one adjudication schema while swapping backends. citeturn40search0turn40search2turn40search3turn19view8turn19view9turn29search1turn29search8turn29search15

A practical architecture looks like this:

```text
Discord slash command
   -> bot service
   -> queue job
   -> worker
   -> retrieve character forms + feat cards from Postgres/pgvector
   -> call local judge model
   -> return verdict JSON
   -> render Discord embed + source thread
```

The key product decision is to **start with a curated roster and explicit forms**, not “type any character and I’ll figure it out.” There is no universal official API for cross-franchise combat stats; the real IP in this project is your normalization layer and ruleset, not the chat wrapper. citeturn34view0turn33view0turn36search0turn33view2

## Source of truth and stat schema

Your data layer needs a **confidence hierarchy**. Official or near-official structured sources are great when they exist, but they do not solve the whole problem. **AniList** gives you GraphQL access to anime and manga entries, characters, staff, and airing data; it is good for names, aliases, media links, and images, not for cross-franchise battle stats. **PokéAPI** is much stronger for franchises like Pokémon because it exposes structured gameplay data through open GET endpoints, requires no authentication, and explicitly asks developers to cache results. **Jikan** is useful as a convenience layer around MyAnimeList, but its own docs say it is **unofficial** and scrapes MAL to fill gaps, so it should not be your primary source of truth for a serious adjudication engine. **Comic Vine** is usable if you expand beyond anime and games, but its API is explicitly non-commercial and rate-limited, so it is better for prototypes than for a public monetized bot. citeturn34view0turn31search1turn31search15turn33view0turn36search0turn36search1turn33view2

For anime and many game franchises, the fight-relevant data will still come from **community-maintained wikis and your own manual feat cards**. MediaWiki itself exposes both an Action API and a REST API, and Fandom documents Fandom-specific endpoints as well. But Fandom also notes that the Portable Infobox API is **not officially announced**, which is a giant hint that infobox scraping will be brittle if you make it your live hot path. That means the right pattern is **ETL into your own schema**: pull pages out-of-band, parse them, normalize them, and store the cleaned result locally instead of scraping live during a `/fight` command. If you ingest or quote Fandom content, preserve attribution and license metadata because Fandom pages note that community content is available under **CC BY-SA unless otherwise noted**. citeturn19view4turn19view5turn7search16turn35view0

The schema should be **form-centric**, not character-centric. “Naruto” is not one row. “Naruto, mainline canon, war arc, Six Paths Sage Mode” is a row. “Sonic” is not one row. “Game canon Super Sonic” and “Composite Sonic” are different rows with different admissibility. At minimum, every playable form should store `character_id`, `continuity`, `form`, `era`, `attack_potency`, `durability`, `speed`, `range`, `stamina`, `battle_iq`, `abilities`, `resistances`, `win_conditions`, `anti_feats`, `source_excerpt`, `source_doc_id`, and `confidence`.

The best internal unit is not one giant profile string but a set of **feat cards**. Each feat card should answer: *what happened, under what canon/form, how direct is the feat, was scaling involved, what counters it, and what is the source excerpt?* That lets the judge retrieve only the cards needed for a matchup instead of dumping full dossiers into the prompt. It also makes it possible to show users a transparent “why this verdict happened” trail.

Use **confidence tiers** in the database itself. A good default is: gameplay- or guidebook-grade structured stats at the top; official metadata next; community feat analysis after that; and pure LLM inference from prose at the bottom. That gives you a clean way to decide when the bot should answer **tie** or **insufficient evidence** instead of forcing fake certainty.

## Local model choice and battle reasoning

For the local judge, the best current family for this job is **Qwen**. Official Qwen materials show that **Qwen3-8B** supports tool use and reasoning, can switch between thinking and non-thinking modes, and can even be controlled turn-by-turn with `/think` and `/no_think`. The newer **Qwen3.6-35B-A3B** is explicitly documented for tool use with vLLM and a `reasoning-parser`, and LM Studio lists it as a reasoning-capable, tool-capable model with a 20 GB minimum system-memory footprint for its packaged local build. In practice, that makes Qwen the best “one model to rule the referee” choice if your box is strong enough. citeturn37view0turn37view1turn37view6turn37view11turn38view3

If you need a smaller local model, **DeepSeek-R1** distills are the best budget lane. DeepSeek’s official release announced the R1 line and the open distilled variants; LM Studio’s packaged **DeepSeek-R1-Distill-Qwen-14B** is documented as an 8 GB minimum-memory local model tuned for reasoning; and LM Studio’s write-up of **DeepSeek-R1-0528-Qwen3-8B** says it supports both tool use and reasoning, with the small local version runnable in roughly the 4–6 GB range depending on packaging. That makes the 8B/14B DeepSeek lane the best place to start if your goal is “good enough reasoning on consumer hardware” rather than maximum quality. citeturn11search2turn38view0turn39view0turn39view1

**Mistral Small 3.1** is the best alternate pick if your priority is clean JSON and function-calling behavior. Mistral describes it as able to run on a single RTX 4090 or a Mac with 32 GB RAM, and its model card highlights low-latency function calling, native JSON outputting, and strong system-prompt adherence. That makes it a very good **controller/judge** if you decide to use a slightly stronger or more specialized model as a separate retrieval or analysis worker later. citeturn37view3turn37view4turn25search6

I would **not** make Llama your first pick for this specific project unless you already have a strong reason to standardize on it. The main issue is not raw capability; it is developer ergonomics and licensing. **Qwen** and **Mistral Small 3.1** both ship under Apache 2.0 in the materials reviewed, while **Llama 3.3** uses the Llama 3.3 Community License. For a bot you may eventually redistribute, fine-tune, or commercialize, the Apache-licensed lanes are simply cleaner. citeturn26search6turn26search12turn26search1turn27search1turn27search2

The bigger design point is that the local model should **not** decide the match on raw vibes. It should consume normalized evidence and emit a strict verdict object. If you run on Ollama, use its structured outputs and thinking separation. If you add a hosted fallback, OpenAI’s structured outputs and Responses API tools map to the same pattern. A good response contract looks like this:

```json
{
  "verdict": "win | loss | tie | insufficient_evidence",
  "winner": "form_id or null",
  "confidence": 0.0,
  "decisive_factors": ["speed gap", "regen countered", "range advantage"],
  "key_interactions": [
    {
      "attacker_ability": "",
      "defender_resistance": "",
      "result": ""
    }
  ],
  "evidence": [
    {
      "claim": "",
      "source_doc_id": "",
      "confidence": "high | medium | low"
    }
  ],
  "narrative_summary": ""
}
```

Make the **narrative summary** the presentation layer. Make the **verdict object** the product. citeturn41search0turn41search2turn19view9turn19view8

## Discord workflow and command surface

Use **slash commands**, not old prefix commands, as the primary interface. Discord’s own migration guidance points developers toward application commands, and Discord’s message-content policies make slash commands the clean path for bots that may grow past hobby scale. Discord also explicitly publishes message-content alternatives and notes that verified apps operating at scale will run into privileged-intent review if they depend on reading arbitrary server message content. For this project, slash commands and message components are enough; you do not need message-content intent for the core experience. citeturn20view10turn28search2turn28search3turn28search7

The interaction flow matters because fight simulation is not instant. Discord requires an initial interaction response within **3 seconds**, and the interaction token stays valid for **15 minutes** for follow-up messages. Message content is capped at **2,000 characters**, while embeds can hold richer content up to **10 embeds** and **6,000 characters**. That means your bot should immediately defer, spin the fight as a queued job, and then post the result as a compact embed plus either a thread, pagination buttons, or an attached JSON/text artifact for full evidence. citeturn19view7turn19view6

The useful command surface is small. `/fight` should resolve two exact forms plus a ruleset. `/character` should show a file-card view of a selected form and its source citations. `/ruleset` should let users flip things like in-character vs. bloodlusted, standard equipment vs. no equipment, neutral field vs. selected arena, and speed equalized vs. normal. `/sources` should dump the admissible evidence used in the most recent fight. `/compare_forms` is worth adding early because version ambiguity is where most fandom fights go full filler arc.

Use autocomplete aggressively so the user selects from canonical form IDs instead of typing freeform chaos. Discord’s interaction model supports autocomplete suggestions, and `discord.py` already gives you an async-ready wrapper with sane rate-limit handling. That matters because the real user experience win here is not “the AI is smart”; it is “the bot doesn’t let users accidentally compare Ultra Instinct Goku to Kid Goku and call it the same character.” citeturn18search3turn18search7

For the async job layer, **RQ** is a good fit because it is intentionally simple: it is a Redis-backed queue for ordinary Python functions, and job results are stored in Redis for later inspection. That is enough for a bot that needs to defer, queue local inference, and poll or callback when the verdict is ready. You do not need a more elaborate orchestration stack on day one. citeturn16search6turn16search9turn16search19

## Dockerized deployment design

A Docker-first setup is the right call. The clean Compose layout is: `bot`, `worker`, `postgres`, `redis`, and **one** local model service, either `ollama` or `vllm`. If you want a thin HTTP layer because you may later add a web dashboard, insert an `api` service between the bot and the queue. If not, the bot can enqueue directly into Redis and the worker can talk straight to the model server and database.

For the model container, pick based on your phase. **Ollama** has an official Docker image, documents GPU access, and now supports structured outputs and thinking-capable models. It also documents Vulkan-based access paths that matter for some non-NVIDIA environments. **vLLM** has official Docker images for both CUDA and ROCm and exposes an OpenAI-compatible server out of the box. Docker Compose itself documents GPU reservations, and NVIDIA’s container documentation covers the prerequisites for exposing NVIDIA devices cleanly into containers. citeturn19view10turn20view8turn41search0turn41search2turn19view11turn19view12turn20view9

Store secrets like the Discord bot token outside the image. Docker’s own docs recommend **Compose secrets** rather than relying on environment variables for sensitive values, because environment variables are easier to leak accidentally and Docker explicitly warns against baking secrets into `ENV` or `ARG` instructions in a Dockerfile. For this project, that means the Discord token, any optional cloud API key, and any upstream connector credential should enter through secrets or a secret manager, not hardcoded env in the image itself. citeturn19view13turn17search21

For retrieval, **PostgreSQL plus pgvector** is a sweet spot because you need both exact and fuzzy matching. PostgreSQL’s native full-text search gives you reliable lexical retrieval for exact names, forms, techniques, continuity tags, and quoted move names. pgvector’s own examples explicitly describe **hybrid search** with Postgres full-text search so you can blend keyword precision with semantic similarity. That is exactly what a battle bot needs when a user asks for something like “Archie Sonic vs. UI Goku, standard equipment, no composite, neutral ground” and you need both exact form matching and semantically relevant feat retrieval. citeturn14search1turn14search9turn21search0

LM Studio is still worth keeping around even if your production stack runs on Ollama or vLLM. Its docs say it can run entirely offline, expose a local server, and reuse OpenAI-compatible clients by changing the base URL. That makes it excellent for **local prompt tuning, schema testing, and quick model bake-offs** on your workstation, even if your headless deployment later standardizes on a different serving stack. citeturn40search0turn40search2turn40search3

## Decisions that lock the build

The remaining choices are not about “can this be built.” They are about **what kind** of bot you want to ship.

The first lock is **scope**. Do you want a broad, messy “any anime or game character” bot, or a tight launch roster with a few canons done correctly? The second is **canon policy**. Are composite characters allowed, or is the default strictly one continuity and one form? The third is **battle policy**. Are fights in-character by default, or bloodlusted? Is prep time ever allowed? Are standard equipment and summons included? The fourth is **evidence policy**. Which sources are admissible, and do fan-wiki claims need corroboration before they can decide a verdict?

The fifth is **hosting reality**. If your host is closer to “consumer GPU, one or two simultaneous fights,” start with Ollama plus a smaller reasoning model. If you expect more simultaneous requests, Qwen3.6 behind vLLM is the more scalable endgame. The sixth is **offline purity**. Is the product fully offline after ingest, or will you allow an opt-in research mode that can refresh sources or use hosted tools? The seventh is **audience**. Is this a private server bot, a public bot, or something you may commercialize later? That answer directly affects model-license choices and upstream API choices, because sources like AniList and Comic Vine have meaningful terms and limits. citeturn31search1turn33view2turn19view11turn19view10turn37view11

These are the follow-up questions that will actually complete the design:

- **Launch roster:** What franchises are in scope for beta, and which one is the reference-quality first dataset?
- **Canon rules:** Mainline only, or will composite/alternate continuities exist as explicit selectable forms?
- **Verdict rules:** In-character or bloodlusted by default? Standard equipment? Prep time? Speed equalization?
- **Evidence rules:** What source tiers are admissible, and what has to be corroborated before it becomes “decisive” evidence?
- **Host hardware:** What machine is actually running this so the model tier can be locked now instead of hand-waved later?
- **Public scale:** Private guild only, or something that may grow beyond 100 servers and should avoid privileged intents from day one?
- **Transparency:** Should users see source cards and confidence scores, or only the final referee summary?
- **Offline policy:** Fully offline after import, or optional online refresh/research mode for missing characters?

If you answer those eight, the rest of the build stops being brainstorming and becomes implementation.