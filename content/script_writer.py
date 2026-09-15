from app.models import Topic, ReelScript


def build_reel_script(topic: Topic) -> ReelScript:
    free = "free-game" in {t.lower() for t in topic.tags} or "gratuit" in topic.title.lower()
    if free:
        hook = f"Ne paie surtout pas pour ça : {topic.title}."
        beats = [
            hook,
            "L'offre est officielle et disponible pour une durée limitée.",
            "Ajoute-le à ta bibliothèque avant la fin de l'offre.",
        ]
        cta = "Tu le récupères ?"
    else:
        hook = f"À retenir aujourd'hui : {topic.title}."
        beats = [
            hook,
            "Voilà ce qui change pour les joueurs.",
            "GamerQuestFR te résume l'essentiel sans perdre ton temps.",
        ]
        cta = "Tu en penses quoi ?"
    voiceover = " ".join(beats + [cta])
    return ReelScript(language="fr", hook=hook, beats=beats, cta=cta, voiceover=voiceover[:420])
