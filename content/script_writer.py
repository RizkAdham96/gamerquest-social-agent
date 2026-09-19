from app.models import Topic, ReelScript


def _first_sentence(value: str) -> str:
    text = " ".join((value or "").split()).strip()
    if not text:
        return ""
    for marker in (". ", "! ", "? "):
        if marker in text:
            return text.split(marker, 1)[0].rstrip(".!?") + "."
    return text if text.endswith((".", "!", "?")) else text + "."


def build_reel_script(topic: Topic) -> ReelScript:
    tagset = {t.lower() for t in topic.tags}
    free = "free-game" in tagset or "gratuit" in topic.title.lower()
    deal = "deal" in tagset
    detail = _first_sentence(topic.summary)

    if free:
        hook = f"Jeu gratuit : {topic.title}."
        context = detail or "L'offre est disponible pour une durée limitée."
        impact = "Ajoute-le à ta bibliothèque avant la fin de l'offre."
        cta = "Tu vas le récupérer ?"
    elif deal:
        hook = f"Bon plan : {topic.title}."
        context = detail or "La réduction est disponible actuellement."
        impact = "Vérifie le prix sur la boutique avant la fin de l'offre."
        cta = "Tu le prends à ce prix ?"
    else:
        hook = topic.title if topic.title.endswith((".", "!", "?")) else topic.title + "."
        context = detail or "Voici l'information essentielle pour les joueurs."
        impact = "Retrouve les détails complets sur GamerQuestFR."
        cta = "Tu en penses quoi ?"

    beats = [hook, context, impact]
    voiceover = " ".join(beats + [cta])
    return ReelScript(language="fr", hook=hook, beats=beats, cta=cta, voiceover=voiceover[:420])
