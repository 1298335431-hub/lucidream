import pytest

from app.schemas.dream import DreamSymbols, DreamSessionResponse
from test_dream_flow import make_client


@pytest.mark.parametrize("forms,expected", [
    (["透明的水母", "一只透明的水母", "透明水母（我）"], {"appearance": "other", "form": "透明的水母"}),
    (["水母", "螃蟹"], None),
    (["我"], None),
    (["男性形象"], {"appearance": "male", "form": ""}),
    (["女性形象"], {"appearance": "female", "form": ""}),
])
def test_prefill_only_one_clear_normalized_form(forms, expected):
    session = DreamSessionResponse(id="test", dream_text="梦境", status="reviewing_symbols", symbols=DreamSymbols(dreamer=forms), revision=1, created_at="now", updated_at="now", model_mode="mock")
    assert session.dreamer_suggestion == expected


def test_legacy_self_is_separate_but_future_self_and_possessives_are_preserved():
    symbols = DreamSymbols(characters=["透明水母（我）", "未来的我", "我的母亲", "发光小鱼"])
    assert symbols.dreamer == ["透明水母"]
    assert symbols.characters == ["未来的我", "我的母亲", "发光小鱼"]
    assert DreamSymbols.model_validate(symbols.model_dump()) == symbols


@pytest.mark.parametrize("appearance,form", [("male", ""), ("female", ""), ("other", "透明水母"), ("unspecified", "")])
def test_explicit_self_requires_confirmation_and_round_trips(tmp_path, appearance, form):
    client = make_client(tmp_path)
    created = client.post("/api/v1/dreams/extract", json={"dream_text": "我梦见自己变成了一只透明的水母，看到我的母亲，我很开心。"}).json()
    assert created["symbols"]["dreamer"] == ["透明的水母"]
    assert created["dreamer_suggestion"] == {"appearance": "other", "form": "透明的水母"}
    payload = {"symbols": created["symbols"], "character_appearance": appearance, "character_form": form}
    endpoint = f"/api/v1/dreams/{created['id']}/symbols"
    assert client.put(endpoint, json=payload).status_code == 200
    restored = client.get(f"/api/v1/dreams/{created['id']}").json()
    assert restored["character_appearance"] == appearance
    assert restored["character_form"] == form
    assert restored["symbols"]["dreamer"] == [form or {"male": "男性形象", "female": "女性形象", "unspecified": "没有明确形象"}[appearance]]
    assert "母亲" in restored["symbols"]["characters"]


def test_unspecified_original_needs_manual_selection(tmp_path):
    client = make_client(tmp_path)
    created = client.post("/api/v1/dreams/extract", json={"dream_text": "森林中有小鸟，我很开心。"}).json()
    assert created["symbols"]["dreamer"] == []
    endpoint = f"/api/v1/dreams/{created['id']}/symbols"
    assert client.put(endpoint, json={"symbols": created["symbols"]}).status_code == 422
    assert client.put(endpoint, json={"symbols": created["symbols"], "character_appearance": "unspecified"}).status_code == 200


def test_other_role_transformation_is_not_the_dreamer(tmp_path):
    client = make_client(tmp_path)
    created = client.post("/api/v1/dreams/extract", json={"dream_text": "我的母亲变成了水母，她说：“我变成了螃蟹。”我很开心。"}).json()
    assert created["symbols"]["dreamer"] == []
