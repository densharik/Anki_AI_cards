"""Конфигурация промптов, типов заметок и параметров обработки."""

from typing import Dict

from .schemas import FieldMode, NoteTypeConfig, NoteTypeFieldConfig

# Белый список тегов
ALLOWED_TAGS = [
    "A2","B1","B2","C1","C2",
    "noun","verb","adj","adv","prep","conj","intj",
    "business","everyday","academic","technical","emotional","phrasal","idiom","slang","collocation",
    "formal","informal","neutral","rude"
]

STRICT_SYSTEM_PROMPT = (
    "Return ONLY valid JSON, no text outside JSON. No markdown. No comments.\n"
    "Schema:\n"
    "{\n"
    "  \"definition\": \"string (5–10 words, short English definition)\",\n"
    "  \"definition_ru\": \"string (5–10 words, natural Russian equivalent)\",\n"
    "  \"ipa\": \"string (IPA transcription, no slashes/brackets)\",\n"
    "  \"lemma\": \"string (dictionary base form, lowercase)\",\n"
    "  \"collocations\": \"string (≤5 items, '<i>english</i> — русский', joined with <br>)\",\n"
    "  \"synonyms\": \"string (≤3 items, 'eng — short explanation (русский)', joined with <br>)\",\n"
    "  \"antonyms\": \"string (≤3 items, same format as synonyms)\",\n"
    "  \"related_forms\": \"string (2–4 lines, 'pos: форма = перевод', joined with <br>. "
    "If irregular verb: 'verb: base — past — past participle = перевод'. "
    "If regular verb: include base + past + past participle with -ed. "
    "Nouns only singular. No duplicate POS.)\",\n"
    "  \"examples\": \"string (2 short dialogs, each with two lines A:/B:, joined with <br>)\",\n"
    "  \"hint\": \"string (short Russian explanation of the word’s meaning in the given sentence/context)\",\n"
    "  \"tags\": [\"string\", \"string\", ...]\n"
    "}\n\n"
    "Rules:\n"
    "- Keys exactly as in schema. All fields MUST be present.\n"
    "- All strings UTF-8, no escaped unicode. No HTML except <i> in collocations and <br> where specified.\n"
    "- definition: neutral register, no headword repetition, no examples/brackets.\n"
    "- definition_ru: one concise natural equivalent, no slashes/alternatives.\n"
    "- ipa: BrE by default; if context clearly American, use AmE. Primary stress required. No / / or [ ].\n"
    "- lemma: lowercase base form (verbs: base; nouns: singular; adjectives/adverbs: base). Keep inherent hyphens.\n"
    "- collocations: 3–5 attested patterns (adj+noun, noun+of, verb+object, fixed phrase). "
    "Format '<i>english</i> — русский', joined with <br>.\n"
    "- synonyms: up to 3, SAME POS and sense as headword. "
    "Format 'eng — short explanation (русский)', joined with <br>.\n"
    "- antonyms: up to 3 true opposites for SAME POS and sense. "
    "Same format as synonyms.\n"
    "- related_forms: 2–4 derivational/morphological relatives, no duplicates of headword. "
    "One verb line with principal parts when applicable. Join with <br>.\n"
    "- examples: exactly 2 dialogs × 2 lines (A:/B:). Each EN line ≤14 words and ends with ' — RU'. Join all lines with <br>. No names or profanity.\n"
    "- hint: 1–2 Russian sentences, explain the exact sense used in `sentence`.\n"
    "- tags: 3–4 items total. Exactly ONE CEFR level (A2/B1/B2/C1/C2). "
    "Other tags ONLY from: "
    f"{', '.join(ALLOWED_TAGS)}. "
    "Use 'everyday' ONLY for core daily vocabulary; use 'academic'/'technical' ONLY when clearly applicable. No duplicates.\n"
)

FIELD_PROMPTS = {
  "definition": (
    "Output: short English definition (5–10 words). "
    "Target sense = the one used in `sentence`; if unclear, use the most common literal sense. "
    "Same POS as the headword. No examples, no synonyms, no idioms, no brackets. "
    "Avoid circularity (do not repeat the headword). Keep register neutral/formal."
  ),

  "definition_ru": (
    "Output: one concise Russian equivalent (5–10 words). "
    "Natural, not telegraphic. No multiple options, no slashes, no brackets. "
    "Match the chosen English sense from `definition`. No transliteration."
  ),

  "ipa": (
    "Output: IPA transcription for the headword. "
    "BrE by default; if the sentence/context is clearly American, use AmE. "
    "No slashes or brackets. Single token if possible; keep hyphens/apostrophes only if in the word. "
    "Mark primary stress. If uncertain, return empty string."
  ),

  "lemma": (
    "Output: dictionary base form in lowercase. "
    "Verbs → base (go), nouns → singular (precinct), adjectives/adverbs → base form. "
    "Strip plural/conjugational endings; keep hyphens if inherent. No POS labels, just the lemma."
  ),

  "collocations": (
    "Output: 3–5 idiomatic, frequent collocations that native speakers actually use. "
    "Prefer patterns: adjective+noun, noun+of, verb+object, fixed expressions. "
    "Do NOT invent niche phrases. No duplicates. "
    "Format each as '<i>english</i> — русский', join with <br>. "
    "Keep same sense as in `sentence`. Lowercase unless proper nouns."
  ),

  "synonyms": (
    "Output: up to 3 synonyms of the SAME POS and sense. "
    "Prioritize common, learner-friendly words. Avoid multiword paraphrases unless standard (e.g., 'drug addict'). "
    "No rare archaisms. No register shift unless intended (mark it in Russian note). "
    "Format: 'eng — short explanation (русский)', join with <br>."
  ),

  "antonyms": (
    "Output: up to 3 true antonyms for the SAME POS and sense. "
    "If no real antonym exists, return empty string. No negated forms with prefixes as fake antonyms unless conventional (e.g., 'legal' vs 'illegal'). "
    "Format: 'eng — short explanation (русский)', join with <br>."
  ),

  "related_forms": (
    "Output: 2–4 derivational/morphological relatives, no duplicates of the headword. "
    "Cover different POS where possible (noun/verb/adj/adv). "
    "If the headword is a verb: "
    " - irregular → one line: 'verb: base — past — past participle = перевод'. "
    " - regular → one line: 'verb: base — past — past participle = перевод' with -ed. "
    "Nouns only singular; adjectives → adverb (-ly) where applicable. "
    "Each line strictly 'pos: форма = перевод'; join with <br>."
  ),

  "examples": (
    "Output: two short mini-dialogs (spoken style). "
    "Each dialog has exactly two lines: 'A: … — …(RU)' and 'B: … — …(RU)'. "
    "Use the target word naturally in context and sense from `sentence`. "
    "Keep each line ≤12–14 words EN. Join all lines with <br>. No profanity, no names."
  ),

  "hint": (
    "Output: 1–2 Russian sentences. "
    "Explain the exact meaning used in `sentence`, disambiguate if multiple senses exist, and note register (slang/formal/technical) if relevant. "
    "No lists, no alternative meanings. Be specific and brief."
  ),

  "tags": (
    "Output: 3–4 tags. Exactly one CEFR level (A2/B1/B2/C1/C2). "
    "Heuristics: function words, core daily actions/objects → A2/B1; common concrete nouns/verbs/adj → B1/B2; abstract/formal/academic/technical → C1/C2; slang/taboo → ≥B2. "
         "Add 2–3 topical/style tags ONLY from ALLOWED_TAGS. "
    "Use 'everyday' ONLY for core daily vocabulary; use 'academic'/'technical' ONLY when clearly applicable. "
    "No duplicates."
  )
}

ANTI_HALLUCINATION_RULES = (
  "If unsure about any field, return an empty string for that field.\n"
  "Keep POS alignment across definition/synonyms/antonyms/collocations.\n"
  "Prefer common, attested phrases; do not coin collocations.\n"
  "For CEFR: if uncertain between two levels, choose the HIGHER level (avoid underestimation).\n"
)


# Системный промпт для OpenAI
SYSTEM_PROMPT = (
    STRICT_SYSTEM_PROMPT
    + "\n\nField guides:\n"
    + "\n".join(f"- {k}: {v}" for k, v in FIELD_PROMPTS.items())
    + "\n\nAnti-hallucination:\n"
    + ANTI_HALLUCINATION_RULES
)



# Конфигурации типов заметок
NOTE_TYPE_CONFIGS: Dict[str, NoteTypeConfig] = {
    "ForkLapisForEnglsih": NoteTypeConfig(
        name="ForkLapisForEnglsih",
        llm_prompt=SYSTEM_PROMPT,
        fields={
            "Expression": NoteTypeFieldConfig(mode=FieldMode.INPUT),
            "Sentence": NoteTypeFieldConfig(mode=FieldMode.INPUT),
            "MainDefinition": NoteTypeFieldConfig(
                mode=FieldMode.GENERATE, 
                llm_key="definition"
            ),
            "MainDefinitionRU": NoteTypeFieldConfig(
                mode=FieldMode.GENERATE, 
                llm_key="definition_ru"
            ),
            "ExpressionAudio": NoteTypeFieldConfig(mode=FieldMode.GENERATE),
            "SentenceAudio": NoteTypeFieldConfig(mode=FieldMode.SKIP),
            "Picture": NoteTypeFieldConfig(mode=FieldMode.SKIP),
            "IPA": NoteTypeFieldConfig(
                mode=FieldMode.GENERATE, 
                llm_key="ipa"
            ),
            "FreqSort": NoteTypeFieldConfig(mode=FieldMode.GENERATE),
            "Collocations": NoteTypeFieldConfig(
                mode=FieldMode.GENERATE, 
                llm_key="collocations"
            ),
            "Synonyms": NoteTypeFieldConfig(
                mode=FieldMode.GENERATE, 
                llm_key="synonyms"
            ),
            "Antonyms": NoteTypeFieldConfig(
                mode=FieldMode.GENERATE, 
                llm_key="antonyms"
            ),
            "RelatedForms": NoteTypeFieldConfig(
                mode=FieldMode.GENERATE, 
                llm_key="related_forms"
            ),
            "E.g.": NoteTypeFieldConfig(
                mode=FieldMode.GENERATE, 
                llm_key="examples"
            ),
            "MiscInfo": NoteTypeFieldConfig(mode=FieldMode.SKIP),
            "DefinitionPicture": NoteTypeFieldConfig(mode=FieldMode.SKIP),
            "SelectionText": NoteTypeFieldConfig(mode=FieldMode.SKIP),
            "Hint": NoteTypeFieldConfig(
                mode=FieldMode.GENERATE, 
                llm_key="hint"
            ),
            "IsWordAndSentenceCard": NoteTypeFieldConfig(mode=FieldMode.SKIP),
            "IsClickCard": NoteTypeFieldConfig(mode=FieldMode.SKIP),
            "IsSentenceCard": NoteTypeFieldConfig(mode=FieldMode.SKIP)
        },
        input_fields=["Expression", "Sentence"],
        generate_fields=[
            "MainDefinition", "MainDefinitionRU", "ExpressionAudio", 
            "IPA", "FreqSort", "Collocations", "Synonyms", "Antonyms", 
            "RelatedForms", "E.g.", "Hint"
        ]
    )
}

# Параметры обработки
DEFAULT_CONCURRENCY_LIMITS = {
    "openai_text": 10,
    "openai_tts": 5,
    "anki_batch": 50
}

# Параметры retry
RETRY_CONFIG = {
    "max_retries": 3,
    "base_delay": 1.0,
    "max_delay": 60.0,
    "exponential_base": 2.0
}
