"""SB rewrite prompt, promoted verbatim from the two-pass prototype.

Provenance: REWRITE_SYSTEM + build_rewrite_prompt are byte-identical to
the strong rewrite prompt in twopass_strong_run.py (fixed demo -- no
candle/lighthouse). Do NOT edit the prompt text here without changing
PROMPT_VERSION: cached_fight_results rows carry the prompt version, and
a changed prompt must never match rows written by an older prompt.

PROMPT_VERSION construction (same as the Wave 1 worker):
    md5(REWRITE_SYSTEM + "\n" + <source of build_rewrite_prompt>)
where <source> is the exact function source as returned by
ast.get_source_segment.
"""

import json

REWRITE_SYSTEM = (
    "You are a strict rewriting editor. You MUST change the draft. "
    "A rewrite that copies the draft is a failure. Follow every numbered "
    "rule below. If any rule conflicts with keeping a sentence unchanged, "
    "the rule wins: rewrite the sentence. Change the wording and the "
    "sentence structure. Do not change the facts."
)


def build_rewrite_prompt(draft_rs, analyst_breakdown):
    winner = draft_rs.get("predicted_winner") or ""
    difficulty = draft_rs.get("difficulty") or ""
    confidence = draft_rs.get("confidence") or ""
    user = f"""Rewrite the DRAFT narration below into the required format.

Pinned outcome (do not change): winner = {winner}; difficulty = {difficulty}.

MUST rules, in order. Every rule is a requirement, not a suggestion. A rewrite that violates any rule is a failure.

1. ANTI-COPY. Do NOT copy any phase unchanged. Every rewritten phase MUST differ from the draft in wording AND sentence structure. If your rewritten output is identical to the draft, you have failed. Copying is not rewriting.

2. ANTI-DELETION. Do NOT delete sentences or facts. You may split a sentence into two or more sentences, and you may reword sentences, but every fact in the draft must appear in the rewrite. Dropping a sentence because it is hard to rewrite is a failure. The only new sentences allowed are the analogy last sentences required by rule 3 and the splits required by rule 5.

3. MUST-WRITE ANALOGY. You MUST write a NEW last sentence for each phase, and that last sentence MUST be exactly one analogy. If the draft phase already ends with an analogy, keep it or improve it. Never delete it. If the draft phase does not end with an analogy, write one. A phase whose last sentence is not an analogy is a failure. A phase with no analogy at all is a failure.

4. ANALOGY METHOD. Exactly ONE analogy per phase, as the LAST SENTENCE only. No analogy may appear anywhere but the last sentence of its phase. The analogy must use the same domain on both sides. Anchor on the smaller side's best feat, then scale the bigger side against it ("her best is X, his warm-up is Y"). The analogy MUST contain the size ratio: the listener must feel the gap without numbers. Where the draft or breakdown supports it, draw the analogy from the fighters' own worlds.

5. SPLIT DEMAND. Split EVERY sentence that holds two fight facts into one-fact sentences. Break every construction that joins two facts with "but", "and", or "while" into separate sentences. A phase containing an unsplit two-fact sentence is a failure. One fight fact per sentence, no exceptions.

6. PHASE ORDER. Each phase must answer, in this order: (1) what happened, (2) who can hurt whom, (3) what decides it, (4) the analogy as the last sentence. A phase missing any part is unfinished.

7. Keep every grounding fact from the draft. Drop nothing that decides the fight. Add no new feats, abilities, or outcomes. Use only facts present in the draft and the analyst breakdown. Never invent feats, abilities, or outcomes. Never change the winner or the difficulty.

8. Remove every banned word: counterplay, leverage, thresholds, deployment, tempo. Remove every bare tier label (a power or speed scale label stated without plain-words meaning in the same sentence): either drop the label or state what it means in plain words in the same sentence.

9. Use verbs, not nouns: describe what each fighter can or cannot do, not abstract nouns for their options. If a sentence cannot be said in one breath, split it.

10. Rewrite the quick verdict into two or three sentences stating the decisive interaction, following rules 2, 5, 7, 8, and 9. The quick verdict contains no analogy.

DEMONSTRATION (invented fighters only -- do NOT copy its fighters, feats, or wording; it shows the operations only):
DRAFT PHASE: "Fighter B opens with her fastest strikes, but Fighter A blocks every one without moving. Fighter B cannot hurt Fighter A, and Fighter A can end Fighter B with one clean hit."
REWRITTEN PHASE: "Fighter B opens with her fastest strikes. Fighter A blocks every one without moving. Fighter B cannot hurt Fighter A. Fighter A can end Fighter B with one clean hit. The decider is simple. Fighter B must never get touched. She cannot stay untouched forever. Her best is [a small thing from her world]; his warm-up is [a big thing from his world]."
Note what changed: the two-fact sentences were split (rules 5), nothing was deleted (rule 2), the wording changed (rule 1), and a ratio-carrying analogy was written as the new last sentence (rules 3 and 4). Do the same operations to the real draft below.

Return ONLY a JSON object with exactly these keys: quick_verdict, phase_1, phase_2, phase_3, difficulty, confidence, predicted_winner. Set predicted_winner to the pinned winner and difficulty to the pinned difficulty. Copy confidence from the draft.

DRAFT:
{json.dumps(draft_rs, indent=1)}

ANALYST BREAKDOWN:
{analyst_breakdown}"""
    return ([{"role": "system", "content": REWRITE_SYSTEM},
             {"role": "user", "content": user}], winner, difficulty, confidence)


# md5(REWRITE_SYSTEM + "\n" + source of build_rewrite_prompt). See the
# module docstring. Do not change this constant without changing the prompt.
PROMPT_VERSION = "9a1f7a3048e1e0dfb9c2a0715c9a8c8e"
