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
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from agent.hidden_gems import GameFacts

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "openai/gpt-oss-120b"
# About 20 to 25 seconds once the name and closing line are spoken.
MIN_BODY_WORDS = 40
MAX_BODY_WORDS = 62
MAX_WRITE_ATTEMPTS = 3
# With low reasoning effort the writer produced broken French ("Tu assemblages
# modules"); it gets medium effort and the allowance to go with it. The
# checker's task is narrower and stays on low.
WRITER_MAX_TOKENS = 6000
WRITER_REASONING = "medium"
CHECKER_MAX_TOKENS = 3000
CHECKER_REASONING = "low"

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
    # Store plumbing is not a reason to play a game.
    "steam", "succès", "cloud", "manette", "partage familial", "cartes à échanger",
)


class ScriptRejected(RuntimeError):
    """The model's text failed a check; the game is skipped, never published."""


@dataclass(frozen=True)
class GemScript:
    body: str
    on_screen_text: str
    caption: str


def _post_groq(payload: dict, api_key: str) -> dict:
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
    with urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def groq_chat(
    messages: list[dict],
    *,
    max_tokens: int,
    reasoning: str = "low",
    api_key: str | None = None,
    post=_post_groq,
) -> str:
    api_key = api_key if api_key is not None else os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Missing GROQ_API_KEY")
    payload = {
        "model": GROQ_MODEL,
        "messages": messages,
        "temperature": 0.4,
        # gpt-oss reasons before it answers and the reasoning counts against
        # this limit; when it used the whole allowance the reply came back
        # empty and Groq refused it as invalid JSON. A wide allowance leaves
        # room for the answer itself.
        "max_tokens": max_tokens,
        "reasoning_effort": reasoning,
        "response_format": {"type": "json_object"},
    }
    try:
        try:
            data = post(payload, api_key)
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            if exc.code != 400 or "reasoning_effort" not in detail:
                raise _groq_error(exc.code, detail) from exc
            # The model does not take the option: ask again without it.
            payload.pop("reasoning_effort")
            data = post(payload, api_key)
    except HTTPError as exc:
        raise _groq_error(exc.code, exc.read().decode("utf-8", errors="replace")[:300]) from exc
    return str(data["choices"][0]["message"]["content"] or "")


def _groq_error(code: int, detail: str) -> Exception:
    if code == 400:
        # Groq answers 400 when the model's reply was not valid JSON; that is
        # a failed draft to retry, not a broken run.
        return ScriptRejected(f"the model reply was refused by the API: {detail}")
    return RuntimeError(f"Groq request failed with HTTP {code}: {detail}")


def _facts_block(facts: GameFacts) -> str:
    return json.dumps(
        {
            "name": facts.name,
            "official_description": facts.description,
            "official_presentation": facts.about,
            "genres": facts.genres,
            "play_modes": facts.modes,
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
- Parle de l'histoire, de l'ambiance et de ce que le joueur fait concrètement.
- Ne parle jamais de fonctionnalités de boutique : succès, sauvegarde en ligne,
  manette, partage familial.
- Français irréprochable : accords, articles et prépositions corrects.
- Phrases simples : sujet, verbe conjugué, complément. Relis chaque verbe.
- Traduis tous les termes anglais des FAITS en français courant. Les noms
  propres du jeu (lieux, factions, personnages) peuvent rester tels quels.
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
lieu, une mécanique, un chiffre ou une qualité absents des FAITS. N'utilise
aucune connaissance extérieure.

Sont appuyées, et ne doivent PAS être signalées :
- une reformulation fidèle ou un résumé d'un passage des FAITS ;
- la traduction française d'un terme anglais des FAITS ("the Void" -> "le Vide",
  "boss hunting" -> "chasse aux boss") ;
- un nom propre repris des FAITS.

Vérifie aussi la langue : toute faute de grammaire, d'accord, d'orthographe ou
de préposition, et tout mot anglais qui n'est pas un nom propre, est une erreur.

Réponds avec : {{"valid": true ou false, "unsupported": ["..."], "language_errors": ["..."]}}
"valid" doit être false s'il y a au moins une affirmation non appuyée ou une erreur de langue."""
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
        # Whole words only: "steam" must not reject "steampunk".
        pattern = re.escape(term.strip())
        if term.strip()[0].isalnum():
            pattern = rf"(?<![a-zà-ÿ0-9]){pattern}"
        if term.strip()[-1].isalnum():
            pattern = rf"{pattern}(?![a-zà-ÿ0-9])"
        if re.search(pattern, lowered):
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
            draft = _parse_json(chat(
                build_writer_messages(facts, feedback),
                max_tokens=WRITER_MAX_TOKENS, reasoning=WRITER_REASONING,
            ))
            body = validate_body(draft.get("body", ""), facts)
            verdict = _parse_json(chat(
                build_checker_messages(facts, body),
                max_tokens=CHECKER_MAX_TOKENS, reasoning=CHECKER_REASONING,
            ))
            language_errors = [str(item) for item in verdict.get("language_errors") or []]
            if verdict.get("valid") is not True or language_errors:
                problems = [str(item) for item in verdict.get("unsupported") or []] + language_errors
                raise ScriptRejected(
                    f"fact-check failed: {'; '.join(problems) or 'no reason given'}"
                )
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
