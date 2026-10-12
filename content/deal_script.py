"""French script for a "bon plan" Reel.

The model writes only the description of the game, exactly as for a
hidden-gem Reel. The sentences that carry the name, the prices and the
discount are assembled here from store data.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from agent.deals import DealFacts
from content.gem_script import GemScript, groq_chat, write_gem_script

# Shorter than a hidden-gem description: the price sentences take their share
# of the Reel's 55 seconds.
DEAL_BODY_WORDS = (70, 100)
DEAL_FOLLOW_LINE = "Abonne-toi pour ne rater aucun bon plan."


def spoken_price(cents: int) -> str:
    """A price the voice reads without guessing: "14 euros 99"."""
    euros, rest = divmod(int(cents), 100)
    if euros == 0:
        return f"{rest} centimes"
    unit = "euro" if euros == 1 else "euros"
    return f"{euros} {unit} {rest:02d}" if rest else f"{euros} {unit}"


def written_price(cents: int) -> str:
    euros, rest = divmod(int(cents), 100)
    return f"{euros},{rest:02d} €"


def on_screen_text(facts: DealFacts, body: str) -> str:
    return (
        f"Bon plan : {facts.name} est à moins {facts.discount_percent} pour cent sur Steam. "
        f"{body} "
        f"En ce moment, {facts.name} passe de {spoken_price(facts.original_cents)} "
        f"à {spoken_price(facts.sale_cents)} sur Steam. "
        f"{DEAL_FOLLOW_LINE}"
    )


def build_caption(facts: DealFacts, today: datetime | None = None) -> str:
    today = today or datetime.now(timezone.utc)
    lines = [
        f"🔥 Bon plan : {facts.name} à -{facts.discount_percent} % sur Steam",
        "",
        f"Prix : {written_price(facts.sale_cents)} au lieu de {written_price(facts.original_cents)}",
    ]
    if facts.ends_at and facts.ends_at > today:
        lines.append(f"Offre annoncée jusqu'au {facts.ends_at:%d/%m/%Y}")
    lines += [
        f"Avis Steam : {facts.review_percent} % positifs",
        f"Prix relevé sur Steam le {today:%d/%m/%Y}, l'offre peut changer.",
        "",
        "Abonne-toi pour ne rater aucun bon plan ! 🎮",
        "",
        "#bonplan #promo #steam #gaming #jeuxvideo #gamerquest",
    ]
    return "\n".join(lines)


def write_deal_script(facts: DealFacts, chat: Callable[..., str] = groq_chat) -> GemScript:
    described = write_gem_script(facts, chat, words=DEAL_BODY_WORDS)
    return GemScript(
        body=described.body,
        on_screen_text=on_screen_text(facts, described.body),
        caption=build_caption(facts),
    )
