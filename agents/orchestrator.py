"""ADK orchestrator. The deterministic pipeline runs as tools; ADK agents
handle judgment calls (scout anomaly handling, evaluator spot-checks)."""
from google.adk.agents import LlmAgent, SequentialAgent, ParallelAgent
from google.adk.tools import FunctionTool
from . import scout, fetch, transcript, ocr, writer, verifier, evaluator

scout_agent = LlmAgent(
    name="ProfileScoutAgent",
    model="gemini-2.5-flash",
    instruction=(
        "Discover every reel for the given Instagram username using discover_reels. "
        "If count is 0, report that the profile may be private or cookies expired - "
        "never invent URLs. Return the full JSON list."
    ),
    tools=[FunctionTool(scout.discover_reels)],
)

extractors = ParallelAgent(
    name="ReelExtractors",
    sub_agents=[
        LlmAgent(name="FetchAgent", model="gemini-2.5-flash",
                 instruction="Fetch metadata and video for one reel.",
                 tools=[FunctionTool(fetch.fetch_reel)]),
        LlmAgent(name="TranscriptAgent", model="gemini-2.5-flash",
                 instruction="Transcribe spoken audio with whisper.",
                 tools=[FunctionTool(transcript.transcribe)]),
        LlmAgent(name="OCRAgent", model="gemini-2.5-flash",
                 instruction="Extract deduplicated on-screen text via OCR.",
                 tools=[FunctionTool(ocr.extract_text)]),
    ],
)

post = SequentialAgent(
    name="PostProcess",
    sub_agents=[
        LlmAgent(name="MDWriterAgent", model="gemini-2.5-flash",
                 instruction="Render the markdown file from all artifacts.",
                 tools=[FunctionTool(writer.write_md)]),
        LlmAgent(name="VerifierAgent", model="gemini-2.5-flash",
                 instruction="Run fidelity checks V1-V7. If status=retry, retry once "
                             "with fps=1.0 for OCR, then mark final status.",
                 tools=[FunctionTool(verifier.verify_reel)]),
        LlmAgent(name="EvaluatorAgent", model="gemini-2.5-flash",
                 instruction="Score against rubric.yaml. Every score must cite evidence; "
                             "flag any MD content with no traceable source as hallucination "
                             "(caps score at 59).",
                 tools=[FunctionTool(evaluator.score)]),
    ],
)

root_agent = SequentialAgent(
    name="ReelExtractionOrchestrator",
    sub_agents=[scout_agent, extractors, post],
)
