"""French voice-over for a GTA 6 news Reel, written by AI from one article.

Same safeguards as the hidden-gem script: the model writes only the body, a
deterministic check runs first, then a second call fact-checks every claim
against the article text. The closing line and the caption (title, outlet,
link) are filled in by code.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import datetime, timezone

from agent.gta6_news import NewsFacts
from content.gem_script import (
    CHECKER_MAX_TOKENS,
    CHECKER_REASONING,
    MAX_WRITE_ATTEMPTS,
    WRITER_MAX_TOKENS,
    WRITER_REASONING,
    GemScript,
    ScriptRejected,
    _parse_json,
    groq_chat,
)

GTA6_BODY_WORDS = (75, 115)
GTA6_FOLLOW_LINE = "Abonne-toi pour ne rien rater de l'actu GTA 6."
GTA6_HASHTAGS = (
    "#GTA6 #GTAVI #GrandTheftAutoVI #RockstarGames #jeuxvideo #gaming #gamerquest"
)

# News may carry dates, platforms and prices, so those are allowed here. What
# stays out: links, tags, verdicts nobody has checked, and claims of access.
FORBIDDEN_TERMS = (
    "http", "www.", "#", "@",
    "j'y ai joué", "j'ai joué", "j'ai testé", "on a testé", "on y a joué",
    "chef-d'œuvre", "chef d'œuvre", "jeu de l'année", "goty",
    "lien en bio", "en exclusivité",
)
LEAK_WORDS = ("rumeur", "leak", "fuite", "insider", "selon des sources", "non confirm")


def _facts_block(facts: NewsFacts) -> str:
    return json.dumps(
        {"titre": facts.title, "média": facts.source, "article": facts.text},
        ensure_ascii=False, indent=1,
    )


def reports_rumour(facts: NewsFacts) -> bool:
    lowered = f"{facts.title} {facts.text}".lower()
    return any(word in lowered for word in LEAK_WORDS)


def build_writer_messages(facts: NewsFacts, feedback: str = "") -> list[dict]:
    min_words, max_words = GTA6_BODY_WORDS
    rumour_rule = (
        "- L'article parle de rumeur, de fuite ou d'informations non confirmées : "
        "dis-le clairement dès la première ou la deuxième phrase "
        "(\"c'est pas encore confirmé\", \"selon une rumeur\")."
        if reports_rumour(facts) else
        "- Présente seulement comme officiel ce que l'article présente comme officiel."
    )
    system = (
        "Tu écris le texte lu en voix off dans un Reel Instagram pour GamerQuest FR, "
        "qui donne chaque jour l'actu de GTA 6. Tu réponds uniquement en JSON."
    )
    user = f"""Écris le texte du Reel à partir de l'article ci-dessous, en français.

FAITS (seule source autorisée) :
{_facts_block(facts)}

RÈGLES :
- Entre {min_words} et {max_words} mots.
- Français oral, tutoiement, phrases courtes, comme un créateur qui annonce
  une news à un ami ("t'as vu", "c'est pas", "y a", "du coup", "franchement").
  Aucune parenthèse, aucune liste.
- STRUCTURE, dans cet ordre :
  1. Une accroche d'une phrase qui donne LA nouvelle sur GTA 6, sans "Salut"
     ni "Aujourd'hui on parle de".
  2. Les détails concrets de l'article : qui, quoi, quand, avec les chiffres
     et noms exacts des FAITS.
  3. Ce que ça change pour les joueurs, seulement si l'article le dit.
  4. Une phrase courte de réaction ou une question au spectateur
     ("Et toi, t'en penses quoi ?"), sans donner d'avis sur la qualité du jeu.
{rumour_rule}
- Utilise uniquement ce que disent les FAITS : aucune date, aucun chiffre,
  aucun personnage, aucune plateforme ou fonctionnalité absente de l'article.
- N'affirme jamais avoir joué au jeu ou l'avoir testé.
- Pas de lien, pas d'emoji, pas de hashtag. Écris "GTA 6" et pas "GTA VI".
- Les nombres s'écrivent en chiffres quand l'article les donne en chiffres.
- Français irréprochable : accords, articles et prépositions corrects.
{("CORRECTION DEMANDÉE : " + feedback) if feedback else ""}
Réponds avec : {{"body": "..."}}"""
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def build_checker_messages(facts: NewsFacts, body: str) -> list[dict]:
    system = "Tu es un vérificateur de faits strict. Tu réponds uniquement en JSON."
    user = f"""Vérifie que chaque affirmation du TEXTE est appuyée par les FAITS.

FAITS :
{_facts_block(facts)}

TEXTE :
{body}

Une affirmation est non appuyée si elle ajoute une date, un chiffre, un prix,
une plateforme, un personnage, une fonctionnalité ou un événement absents des
FAITS, ou si elle présente comme officiel ce que les FAITS présentent comme une
rumeur ou une fuite. N'utilise aucune connaissance extérieure, même si tu
penses connaître la réponse.

Sont appuyées, et ne doivent PAS être signalées :
- une reformulation fidèle ou un résumé d'un passage des FAITS ;
- "GTA 6" pour "GTA VI" ou "Grand Theft Auto VI" ;
- une question au spectateur ou une réaction qui n'affirme aucun fait.

Vérifie aussi la langue : toute faute de grammaire, d'accord, d'orthographe ou
de préposition est une erreur. Le registre oral est voulu : "t'as", "c'est
pas", "y a", l'absence de "ne" ne sont PAS des erreurs.

Réponds avec : {{"valid": true ou false, "unsupported": ["..."], "language_errors": ["..."]}}
"valid" doit être false s'il y a au moins une affirmation non appuyée ou une erreur de langue."""
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def validate_body(body: str) -> str:
    min_words, max_words = GTA6_BODY_WORDS
    body = " ".join(str(body or "").split())
    words = body.split()
    if not min_words <= len(words) <= max_words:
        raise ScriptRejected(f"text has {len(words)} words; expected {min_words}-{max_words}")
    if not body.endswith((".", "!", "?")):
        raise ScriptRejected("text does not end with a complete sentence")
    lowered = body.lower()
    for term in FORBIDDEN_TERMS:
        if term in lowered:
            raise ScriptRejected(f"text contains a forbidden term: {term}")
    if re.search(r"[\U0001F000-\U0001FAFF☀-➿]", body):
        raise ScriptRejected("text contains an emoji")
    if "gta" not in lowered and "grand theft auto" not in lowered:
        raise ScriptRejected("text never names GTA 6")
    return body


def build_caption(facts: NewsFacts, today: datetime | None = None) -> str:
    today = today or datetime.now(timezone.utc)
    return (
        f"🚨 {facts.title}\n\n"
        f"Source : {facts.source} ({facts.published:%d/%m/%Y})\n"
        f"{facts.url}\n\n"
        "Abonne-toi pour suivre toute l'actu GTA 6 ! 🎮\n\n"
        f"{GTA6_HASHTAGS}"
    )


def on_screen_text(body: str) -> str:
    return f"{body} {GTA6_FOLLOW_LINE}"


def write_gta6_script(facts: NewsFacts, chat: Callable[..., str] = groq_chat) -> GemScript:
    """Write, validate and fact-check; raise ScriptRejected if it cannot pass."""
    feedback = ""
    last_error: ScriptRejected | None = None
    for _attempt in range(MAX_WRITE_ATTEMPTS):
        try:
            draft = _parse_json(chat(
                build_writer_messages(facts, feedback),
                max_tokens=WRITER_MAX_TOKENS, reasoning=WRITER_REASONING,
            ))
            body = validate_body(draft.get("body", ""))
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
            print(f"Script rejected for '{facts.title}': {exc}")
            continue
        return GemScript(body=body, on_screen_text=on_screen_text(body), caption=build_caption(facts))
    raise last_error or ScriptRejected("no script was produced")
