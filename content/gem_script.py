"""French on-screen script for a hidden-gem Reel, written by AI from store facts.

The model only writes the description of the game. Its name, the closing line
and the caption's price and review figures are filled in by code from Steam
data, so the facts viewers act on never pass through the model.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.request import Request, urlopen

from agent.hidden_gems import GameFacts

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "openai/gpt-oss-120b"
# About 20 to 25 seconds once the name and closing line are spoken.
MIN_BODY_WORDS = 40
MAX_BODY_WORDS = 62
MAX_WRITE_ATTEMPTS = 2

FOLLOW_LINE = "Abonne-toi pour découvrir une pépite cachée chaque jour."

# The body describes gameplay only. Anything about money, dates, platforms or
# reception comes from Steam data in the caption, never from the model.
FORBIDDEN_TERMS = (
    "€", "$", "euro", "prix", "gratuit", "promo", "réduction", "solde",
    "ps5", "ps4", "playstation", "xbox", "switch", "nintendo", "game pass",
    "sortie", "sorti ", "bientôt", "mise à jour", "dlc",
    "meilleur", "chef-d'œuvre", "chef d'œuvre", "incontournable", "culte",
    "millions", "record", "récompense", "prix du", "goty",
    "http", "www.", "#", "@",
)


class ScriptRejected(RuntimeError):
    """The model's text failed a check; the game is skipped, never published."""


@dataclass(frozen=True)
class GemScript:
    body: str
    on_screen_text: str
    caption: str


def groq_chat(messages: list[dict], *, max_tokens: int, api_key: str | None = None) -> str:
    api_key = api_key if api_key is not None else os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Missing GROQ_API_KEY")
    payload = {
        "model": GROQ_MODEL,
        "messages": messages,
        "temperature": 0.4,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    request = Request(
        GROQ_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "gamerquest-social-agent",
        },
        method="POST",
    )
    with urlopen(request, timeout=90) as response:
        data = json.loads(response.read().decode("utf-8"))
    return str(data["choices"][0]["message"]["content"] or "")


def _facts_block(facts: GameFacts) -> str:
    return json.dumps(
        {
            "name": facts.name,
            "official_description": facts.description,
            "genres": facts.genres,
            "steam_features": facts.features,
        },
        ensure_ascii=False,
        indent=1,
    )


def build_writer_messages(facts: GameFacts, feedback: str = "") -> list[dict]:
    system = (
        "Tu écris le texte lu en voix off dans un Reel Instagram pour GamerQuest FR, "
        "qui présente chaque jour un jeu méconnu. Tu réponds uniquement en JSON."
    )
    user = f"""Écris la description du jeu ci-dessous, en français, pour un Reel.

FAITS (seule source autorisée) :
{_facts_block(facts)}

RÈGLES :
- Entre {MIN_BODY_WORDS} et {MAX_BODY_WORDS} mots, en 4 ou 5 phrases courtes.
- Le texte sera lu à voix haute : écris comme on parle, sans parenthèses ni abréviations.
- Tutoie le spectateur, au présent ("Dans ce jeu, tu...").
- Commence directement par ce qu'on fait dans le jeu, de façon accrocheuse.
- Utilise uniquement ce que disent les FAITS. N'ajoute aucun mode, personnage,
  lieu, chiffre ou mécanique qui n'y figure pas.
- Ne cite pas le nom du jeu : il est ajouté après ton texte.
- Aucun prix, aucune date, aucune plateforme, aucun avis ni superlatif
  ("meilleur", "culte", "incontournable").
- Aucun chiffre, aucun emoji, aucun hashtag, aucun mot en anglais sauf un nom propre.
{("CORRECTION DEMANDÉE : " + feedback) if feedback else ""}
Réponds avec : {{"body": "..."}}"""
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def build_checker_messages(facts: GameFacts, body: str) -> list[dict]:
    system = "Tu es un vérificateur de faits strict. Tu réponds uniquement en JSON."
    user = f"""Vérifie que chaque affirmation du TEXTE est appuyée par les FAITS.

FAITS :
{_facts_block(facts)}

TEXTE :
{body}

Une affirmation est non appuyée si elle ajoute un mode de jeu, un personnage, un
lieu, une mécanique, un chiffre ou une qualité absents des FAITS. Une simple
reformulation fidèle est appuyée. N'utilise aucune connaissance extérieure.

Réponds avec : {{"valid": true ou false, "unsupported": ["..."]}}"""
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _parse_json(text: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", str(text or "").strip())
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1:
        raise ScriptRejected("the model did not return JSON")
    try:
        data = json.loads(cleaned[start:end + 1])
    except json.JSONDecodeError as exc:
        raise ScriptRejected(f"the model returned invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ScriptRejected("the model did not return a JSON object")
    return data


def validate_body(body: str, facts: GameFacts) -> str:
    """Deterministic checks; returns the cleaned body or raises ScriptRejected."""
    body = " ".join(str(body or "").split())
    words = body.split()
    if not MIN_BODY_WORDS <= len(words) <= MAX_BODY_WORDS:
        raise ScriptRejected(
            f"description has {len(words)} words; expected {MIN_BODY_WORDS}-{MAX_BODY_WORDS}"
        )
    if not body.endswith((".", "!", "?")):
        raise ScriptRejected("description does not end with a complete sentence")
    lowered = body.lower()
    for term in FORBIDDEN_TERMS:
        if term in lowered:
            raise ScriptRejected(f"description contains a forbidden term: {term.strip()}")
    if re.search(r"\d", body):
        raise ScriptRejected("description contains a number")
    if re.search(r"[\U0001F000-\U0001FAFF☀-➿]", body):
        raise ScriptRejected("description contains an emoji")
    if facts.name.lower() in lowered:
        raise ScriptRejected("description repeats the game's name")
    return body


def build_caption(facts: GameFacts, today: datetime | None = None) -> str:
    """Every figure here is copied from Steam and dated."""
    today = today or datetime.now(timezone.utc)
    return (
        "Abonne-toi pour découvrir une pépite cachée chaque jour ! 🎮\n\n"
        f"Jeu : {facts.name}\n"
        "Plateforme : PC (Steam)\n"
        f"Prix : {facts.price} (prix Steam au {today:%d/%m/%Y})\n"
        f"Avis Steam : {facts.review_percent} % positifs\n\n"
        "#gaming #jeuxvideo #jeuxindé #pépite #steam #gamerquest"
    )


def on_screen_text(facts: GameFacts, body: str) -> str:
    return f"{body} Le jeu s'appelle {facts.name}. {FOLLOW_LINE}"


def write_gem_script(
    facts: GameFacts,
    chat: Callable[..., str] = groq_chat,
) -> GemScript:
    """Write, validate and fact-check; raise ScriptRejected if it cannot pass."""
    feedback = ""
    last_error: ScriptRejected | None = None
    for _attempt in range(MAX_WRITE_ATTEMPTS):
        try:
            draft = _parse_json(chat(build_writer_messages(facts, feedback), max_tokens=1400))
            body = validate_body(draft.get("body", ""), facts)
            verdict = _parse_json(chat(build_checker_messages(facts, body), max_tokens=900))
            if verdict.get("valid") is not True:
                unsupported = "; ".join(str(item) for item in verdict.get("unsupported") or [])
                raise ScriptRejected(f"fact-check failed: {unsupported or 'no reason given'}")
        except ScriptRejected as exc:
            last_error = exc
            feedback = str(exc)
            print(f"Script rejected for {facts.name}: {exc}")
            continue
        return GemScript(
            body=body,
            on_screen_text=on_screen_text(facts, body),
            caption=build_caption(facts),
        )
    raise last_error or ScriptRejected("no script was produced")
