import json

from models import Reel
from utils.json_payload import to_json_text


def test_to_json_text_serializes_models_as_plain_json():
    text = to_json_text({"reels": [Reel(id="1", title="Judul", views=10)]})

    payload = json.loads(text)
    assert payload["reels"][0]["reel_id"] == "1"
    assert payload["reels"][0]["title"] == "Judul"
    assert payload["reels"][0]["views"] == 10
