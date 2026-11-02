"""EvaluatorAgent: evidence-grounded rubric scoring. Deterministic core here;
LLM spot-check layer plugs into score_with_llm()."""
import yaml

RUBRIC_PATH = "rubric/rubric.yaml"

def _load_rubric():
    with open(RUBRIC_PATH) as f:
        return yaml.safe_load(f)

def score(fetch: dict, transcript: dict, ocr: dict, verify_result: dict,
          llm_spotcheck_fn=None) -> dict:
    """Score a reel 0-100 against rubric.yaml. llm_spotcheck_fn(caption, transcript_sample)
    may return {'transcript_match_pct': 0-100, 'hallucinations': [...]} to refine scoring."""
    rubric = _load_rubric()
    t = rubric["thresholds"]
    scores = {}

    # caption_completeness
    cap = fetch.get("caption") or ""
    if not cap:
        scores["caption_completeness"] = 0
    elif "#" in cap and len(cap) > 10:
        scores["caption_completeness"] = 20
    else:
        scores["caption_completeness"] = 10

    # transcript_accuracy (base) + optional LLM refinement
    conf = transcript.get("avg_confidence")
    if not transcript.get("text"):
        scores["transcript_accuracy"] = 0
    elif conf is not None and conf < 0.2:
        scores["transcript_accuracy"] = 25
    elif conf is not None and conf < 0.4:
        scores["transcript_accuracy"] = 15
    else:
        scores["transcript_accuracy"] = 5

    # onscreen_text_coverage
    lines = ocr.get("lines") or []
    dur = ocr.get("duration_s") or 0
    density = len(lines) / max(dur / 10, 1)  # lines per 10s
    scores["onscreen_text_coverage"] = 25 if density >= 2 else (15 if density >= 0.5 else (5 if lines else 0))

    # metadata_accuracy
    scores["metadata_accuracy"] = 10 if fetch.get("shortcode") and fetch.get("url") else 0

    # formatting
    scores["formatting"] = 10 if verify_result.get("status") == "pass" else 5

    # no_hallucination: fail-cap if verify failed on caption
    scores["no_hallucination"] = 0 if "V3_caption_match" in verify_result.get("failed_checks", []) else 10

    weights = {c["criterion"]: c["weight"] for c in rubric["rubric"]}
    max_scores = {}
    for c in rubric["rubric"]:
        max_scores[c["criterion"]] = max(c["scoring"].keys())
    total = sum(scores[c] * weights[c] / max_scores[c] for c in scores)
    total = round(total, 1)

    justification = f"verify={verify_result.get('status')}; " +         "; ".join(f"{k}={v}" for k, v in scores.items())
    verdict = "publish" if total >= t["publish"] else ("retry" if total >= t["retry"] else "fail")
    return {"total": total, "criteria": scores, "justification": justification, "verdict": verdict}
