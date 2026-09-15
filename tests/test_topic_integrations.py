from app.models import Topic


def test_topic_accepts_publisher_steam_app_and_official_channels():
    topic = Topic(
        title="Example Game update",
        url="https://gamerquestfr.com/example",
        source="GamerQuestFR",
        publisher="Example Studio",
        steam_app_id=12345,
        official_channel_ids=["UC-official"],
    )
    assert topic.publisher == "Example Studio"
    assert topic.steam_app_id == 12345
    assert topic.official_channel_ids == ["UC-official"]
