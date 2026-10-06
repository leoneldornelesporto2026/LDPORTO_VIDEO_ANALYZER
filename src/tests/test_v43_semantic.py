from copy import deepcopy
import json

import pytest

from ldporto.config import DEFAULTS
from ldporto import semantic


def review_candidate(mid="M1", text="A gravacao foi feita no estudio."):
    return {"moment_id": mid, "start": 0, "end": 60, "text": text,
            "evidence_segment_ids": ["S1" if mid == "M1" else "S2"],
            "categories": ["educational"], "editorial": {}, "standalone_class": "good"}


def review_row(mid, quote_ref):
    return {"moment_id": mid, "quote_ref": quote_ref, "editorial_score": .7,
            "why": "O trecho explica a gravacao no estudio.", "hook_text": "O segredo da gravacao",
            "title_idea": "Uma historia de gravacao", "context_note": "O trecho possui contexto.",
            "evidence_segment_ids": ["S1" if mid == "M1" else "S2"]}


def envelope(rows):
    return {"locale": "pt-BR", "overview": "O programa discute historias sobre gravacao.",
            "top_moments": rows, "content_angles": [], "notes": []}


def test_quote_ref_resolves_only_to_its_grounded_candidate():
    candidates = [review_candidate()]
    catalog = semantic.prepare_quote_catalog(candidates)
    quote = next(iter(catalog))
    assert semantic.validate_global_review(envelope([review_row("M1", quote)]), candidates)
    with pytest.raises(ValueError, match="quote_ref"):
        semantic.validate_global_review(envelope([review_row("M1", "QUOTE_ABSENT")]), candidates)


def test_invalid_global_item_preserves_valid_items_after_bounded_targeted_repair(monkeypatch):
    candidates = [review_candidate(), review_candidate("M2", "Uma segunda explicacao sobre a gravacao.")]
    quote = next(reference for reference, row in semantic.prepare_quote_catalog(candidates).items() if row["moment_id"] == "M1")
    calls = []

    def chat(url, model, messages, schema, cfg):
        calls.append(json.loads(messages[-1]["content"]))
        return envelope([review_row("M1", quote), review_row("M2", "QUOTE_BAD")]), {"total_duration_ns": 1000}

    monkeypatch.setattr(semantic, "ollama_chat", chat)
    result, meta = semantic.call_global_review(deepcopy(DEFAULTS["semantic_analysis"]), [], candidates)
    assert result["top_moments"][0]["moment_id"] == "M1"
    assert result["top_moments"][0]["literal_excerpt"] == candidates[0]["text"]
    assert result["status"] == "partial"
    assert len(calls) == 2
    assert all(row["moment_id"] == "M2" for row in calls[1]["moments"])
    assert meta["invalid_item_count"] == 1


def test_valid_global_quote_ref_does_not_require_expensive_repair(monkeypatch):
    candidate = review_candidate()
    quote = next(iter(semantic.prepare_quote_catalog([candidate])))
    calls = []
    monkeypatch.setattr(semantic, "ollama_chat", lambda *args: (calls.append(True) or envelope([review_row("M1", quote)]), {}))
    result, meta = semantic.call_global_review(deepcopy(DEFAULTS["semantic_analysis"]), [], [candidate])
    assert len(calls) == 1 and result["status"] == "ok"
    assert not meta["repair_attempted"]


def test_compact_range_schema_expands_only_existing_ordered_segment_refs():
    from test_v42_editorial import model_fixture
    group = [{"segment_id": "S", "start": 0, "end": 10, "text": "Uma explicacao sobre gravacao.", "speaker": "A"}]
    model = model_fixture()
    for key in ("topics", "moments"):
        for item in model[key]:
            item.pop("segment_ids")
            item.update(start_segment_id="S", end_segment_id="S")
    assert semantic.ground_model_output(model, group, 0)["moments"][0]["evidence_segment_ids"] == ["S"]
    model["topics"][0]["end_segment_id"] = "ABSENT"
    with pytest.raises(Exception):
        semantic.ground_model_output(model, group, 0)


def test_semantic_cache_reuses_facts_and_invalidates_only_relevant_contracts(tmp_path, monkeypatch):
    from test_v42_editorial import semantic_context, model_fixture
    ctx, transcript = semantic_context(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(semantic, "call_ollama", lambda *args: (calls.append(True) or model_fixture(), {}))
    semantic.SemanticEngine().run(ctx, transcript)
    ctx.config["camera_director"]["profile"] = "conservative"
    assert semantic.SemanticEngine().run(ctx, transcript)["data"]["semantic_metrics"]["semantic_cache_hit_ratio"] == 1
    assert len(calls) == 1
    monkeypatch.setattr(semantic, "SCHEMA_VERSION", "changed")
    semantic.SemanticEngine().run(ctx, transcript)
    assert len(calls) == 2
    monkeypatch.setattr(semantic, "PROMPT_VERSION", "changed")
    semantic.SemanticEngine().run(ctx, transcript)
    assert len(calls) == 3


def test_empty_ollama_content_records_thinking_budget_without_retry(monkeypatch):
    from ldporto import ollama_local
    calls = []
    def response(*args, **kwargs):
        calls.append(kwargs["payload"])
        return {"message": {"thinking": "Internal synthetic reasoning"}, "done_reason": "length", "eval_count": 100}
    monkeypatch.setattr(ollama_local, "_request_json", response)
    with pytest.raises(ollama_local.OllamaContentError) as error:
        ollama_local.chat("http://127.0.0.1:11434", "qwen3:14b", [{"role": "user", "content": "Synthetic"}], {}, DEFAULTS["semantic_analysis"])
    assert error.value.metadata["failure_category"] == "empty_thinking_only"
    assert error.value.metadata["done_reason"] == "length"
    assert "thinking" not in error.value.metadata or not isinstance(error.value.metadata.get("thinking"), str)
    assert calls[0]["think"] is False and len(calls) == 1


def test_local_targeted_repair_preserves_valid_moment_metadata(monkeypatch):
    from test_v42_editorial import model_fixture
    group = [{"segment_id": "S", "start": 0, "end": 10, "text": "A gravacao foi feita no estudio.", "speaker": "A"}]
    invalid = model_fixture()
    original_moment = deepcopy(invalid["moments"][0])
    invalid["topics"][0]["segment_ids"] = ["BAD"]
    repaired = model_fixture()
    repaired["moments"][0]["reason"] = "Uma mudanca indevida no momento valido."
    calls = []
    monkeypatch.setattr(semantic, "ollama_chat", lambda *args: (calls.append(json.loads(args[2][-1]["content"])) or repaired, {}))
    result, meta = semantic.repair_ollama_output(DEFAULTS["semantic_analysis"], group, invalid, "Invalid topic refs")
    assert result["moments"][0] == original_moment
    assert calls[0]["invalid_output"]["moments"] == []
    assert meta["preserved_item_count"] == 1
    assert semantic.ground_model_output(result, group, 0)


def test_global_review_cache_reuses_checksums_without_new_inference(tmp_path, monkeypatch):
    candidate = review_candidate()
    quote = next(iter(semantic.prepare_quote_catalog([candidate])))
    calls = []
    monkeypatch.setattr(semantic, "ollama_chat", lambda *args: (calls.append(True) or envelope([review_row('M1', quote)]), {}))
    cfg = deepcopy(DEFAULTS['semantic_analysis'])
    cfg['_global_cache_dir'] = str(tmp_path)
    semantic.call_global_review(cfg, [], [candidate])
    result, meta = semantic.call_global_review(cfg, [], [candidate])
    assert len(calls) == 1 and meta['cache_hit']
    assert result['top_moments'][0]['quote_ref'] == quote