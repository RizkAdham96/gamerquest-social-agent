from app.models import Topic


def build_caption(topic: Topic) -> str:
    free = "free-game" in {t.lower() for t in topic.tags} or "gratuit" in topic.title.lower()
    if free:
        return f"🎮 {topic.title}\n\nGarde l'œil sur GamerQuestFR pour les prochains jeux gratuits. Tu le récupères ? #gaming #jeuxvideo"
    return f"🎮 {topic.title}\n\nL'essentiel gaming sur GamerQuestFR. Tu en penses quoi ? #gaming #jeuxvideo"
