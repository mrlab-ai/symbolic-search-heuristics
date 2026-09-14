"""Load Lab's separate static properties before identity-aware callbacks."""

import json
from pathlib import Path


def initialize_static(_content, props):
    # Experiment.parse() starts from dynamic properties; Fetcher merges the
    # static properties only later. Identity-aware parsers need them earlier.
    static = json.loads(Path("static-properties").read_bytes())
    props.setdefault("unexplained_errors", [])
    for field, value in static.items():
        if field in props and props[field] != value:
            raise ValueError(f"static and parsed properties disagree: {field}")
        props[field] = value
