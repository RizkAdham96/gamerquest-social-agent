"""French on-screen script for a hidden-gem Reel, written by AI from store facts.

The model only writes the description of the game. Its name, the closing line
and the caption's price and review figures are filled in by code from Steam
data, so the facts viewers act on never pass through the model.
"""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from agent.hidden_gems import GameFacts

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "openai/gpt-oss-120b"
# The reference Reels run 35-42 seconds at about four words a second, with
# the game's name held back to the end.
MIN_BODY_WORDS = 95
MAX_BODY_WORDS = 135
MAX_WRITE_ATTEMPTS = 3
# With low reasoning effort the writer produced broken French ("Tu assemblages
# modules"); it gets medium effort and the allowance to go with it. The
# checker's task is narrower and stays on low.
WRITER_MAX_TOKENS = 6000
WRITER_REASONING = "medium"
CHECKER_MAX_TOKENS = 3000
CHECKER_REASONING = "low"
MAX_RATE_LIMIT_RETRIES = 3

FOLLOW_LINE = "Je te présente un nouveau jeu chaque jour, alors abonne-toi pour ne rien manquer."

# The body describes gameplay only. Anything about money, dates, platforms or
# reception comes from Steam data in the caption, never from the model.
FORBIDDEN_TERMS = (
    "€", "$", "euro", "prix", "gratuit", "promo", "réduction", "solde",
    "ps5", "ps4", "playstation", "xbox", "switch", "nintendo", "game pass",
    "sortie", "sorti ", "bientôt", "mise à jour", "dlc",
    "meilleur", "chef-d'œuvre", "chef d'œuvre", "incontournable", "culte",
    "millions", "record", "récompense", "prix du", "goty",
    "http", "www.", "#", "@",
    # Verdicts on how the game plays, which nobody here has checked.
    "tient en haleine", "du début à la fin", "addictif", "immersion", "captivant",
    "impossible de lâcher", "des heures",
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
    sleep=time.sleep,
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
    for attempt in range(1, MAX_RATE_LIMIT_RETRIES + 2):
        try:
            data = post(payload, api_key)
            break
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            if exc.code == 400 and "reasoning_effort" in detail and "reasoning_effort" in payload:
                # The model does not take the option: ask again without it.
                payload.pop("reasoning_effort")
                continue
            if exc.code == 429 and attempt <= MAX_RATE_LIMIT_RETRIES and "per day" not in detail:
                # The free tier allows 8000 tokens a minute; a writer call
                # followed by a check can cross it. The window clears quickly.
                sleep(rate_limit_wait(detail))
                continue
            raise _groq_error(exc.code, detail) from exc
    return str(data["choices"][0]["message"]["content"] or "")


def rate_limit_wait(detail: str) -> float:
    match = re.search(r"try again in ([0-9.]+)s", detail)
    seconds = float(match.group(1)) if match else 20.0
    return min(seconds + 2.0, 65.0)


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
- Entre {MIN_BODY_WORDS} et {MAX_BODY_WORDS} mots.
- Le texte est dit à voix haute par un créateur qui parle à un ami : français
  oral, tutoiement, phrases courtes. Les tournures parlées sont voulues
  ("t'es", "c'est pas", "y a", "du coup", "sauf que", "franchement").
  Aucune parenthèse, aucune abréviation, aucune liste.
- STRUCTURE, dans cet ordre :
  1. Une accroche de une ou deux phrases qui pose l'enjeu ou le retournement
     du jeu du point de vue du joueur. Pas de "Dans ce jeu, tu...".
  2. Ce que le joueur fait concrètement, avec les détails précis des FAITS.
  3. Ce qui rend le jeu différent ou tendu ("Sauf que...", "Et le pire...").
  4. Une seule phrase courte d'enthousiasme sur l'IDÉE du jeu (par exemple
     "Franchement, l'idée est maligne."), sans jamais dire que tu y as joué
     ni que tu l'as testé, et sans juger sa qualité, sa durée ou son effet
     sur le joueur ("terrifiant", "te tient en haleine", "du début à la fin").
- Chaque phrase doit donner une information ou faire monter la tension :
  aucune phrase creuse, aucune répétition.
- Ne parle jamais de fonctionnalités de boutique : succès, sauvegarde en ligne,
  manette, partage familial.
- Français irréprochable : accords, articles et prépositions corrects.
- Phrases simples : sujet, verbe conjugué, complément. Relis chaque verbe.
- Traduis tous les termes anglais des FAITS en français courant. Les noms
  propres du jeu (lieux, factions, personnages) peuvent rester tels quels.
- Méfie-toi des faux amis : "ramming" se dit "éperonner" (pas "ramer"),
  "boarding" se dit "aborder". Si tu n'es pas certain de la traduction d'un
  terme, décris l'action avec d'autres mots plutôt que de la traduire.
- Utilise uniquement ce que disent les FAITS. N'ajoute aucun mode, personnage,
  lieu, chiffre ou mécanique qui n'y figure pas.
- Ne cite pas le nom du jeu : il est ajouté après ton texte.
- Aucun prix, aucune date, aucune plateforme, aucun superlatif
  ("meilleur", "culte", "incontournable"), aucun avis de joueurs ou de presse.
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
Le registre oral est voulu : "t'es", "c'est pas", "y a", l'absence de "ne" et
les mots comme "franchement" ou "du coup" ne sont PAS des erreurs.
Une phrase d'enthousiasme sur le concept est permise tant qu'elle n'affirme
aucun fait ; en revanche, dire qu'on a joué au jeu ou qu'on l'a testé est une
affirmation non appuyée.

Vérifie enfin chaque traduction : pour chaque verbe d'action et chaque terme de
jeu du TEXTE, retrouve le mot anglais des FAITS et confirme que le sens est le
même. Un faux ami ou un contresens est une erreur de langue. Exemples d'erreurs :
"ramming" rendu par "ramer" (il faut "éperonner"), "boarding" rendu par
"embarquer" (il faut "aborder"), "crafting" rendu par "crafter".

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
        # Whole words only, plural included: "steam" must not reject
        # "steampunk", while "euro" must still catch "euros".
        pattern = re.escape(term.strip())
        if term.strip()[0].isalnum():
            pattern = rf"(?<![a-zà-ÿ0-9]){pattern}"
        if term.strip()[-1].isalnum():
            pattern = rf"{pattern}(?:s|x)?(?![a-zà-ÿ0-9])"
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
    return f"{body} {FOLLOW_LINE} Ce jeu, c'est {facts.name}, et il est dispo sur PC, sur Steam."


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
