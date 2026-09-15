import argparse
import json
from pathlib import Path
from agent.discover import load_topics_from_json
from agent.select import select_best_topic
from content.script_writer import build_reel_script
from content.caption_writer import build_caption


def main():
    parser = argparse.ArgumentParser(description="GamerQuest Social Agent Sprint 1")
    parser.add_argument("topics", type=Path, help="JSON file containing candidate topics")
    args = parser.parse_args()
    selected = select_best_topic(load_topics_from_json(args.topics), recent_slugs=set())
    script = build_reel_script(selected.topic)
    print(json.dumps({
        "topic": selected.topic.title,
        "score": selected.score.total,
        "script": script.voiceover,
        "caption": build_caption(selected.topic),
    }, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
