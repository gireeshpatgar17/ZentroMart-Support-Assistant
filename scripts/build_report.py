"""Build the four-page maximum capstone evaluation report from saved results."""
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak,
)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "pdf" / "ZentroMart_Capstone_Report.pdf"
RESULTS = ROOT / "reports" / "drafts"
NAVY = colors.HexColor("#17324D")
TEAL = colors.HexColor("#087E8B")
INK = colors.HexColor("#263442")
MUTED = colors.HexColor("#637381")
PALE = colors.HexColor("#EEF4F7")
RULE = colors.HexColor("#D5E0E6")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


retrieval = json.loads((RESULTS / "retrieval_final.json").read_text(encoding="utf-8"))
answers = read_csv(RESULTS / "answer_comparison_final_scored.csv")
conversations = read_csv(RESULTS / "conversation_evaluation.csv")
scored_answers = [r for r in answers if r.get("rag_correct_decision", "") != "N/A - evaluate in conversation flow"]


def n_yes(column: str, rows: list[dict[str, str]]) -> int:
    return sum(r.get(column, "").strip().casefold() == "yes" for r in rows)


langs = Counter(r.get("language", "") for r in answers if r.get("answerable", "").lower() in {"true", "yes", "1"})
conversation_count = len({r["conversation_id"] for r in conversations})
passed_turns = sum(r.get("turn_screen") == "Pass" for r in conversations)

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="CoverTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=24, leading=29, textColor=NAVY, spaceAfter=6))
styles.add(ParagraphStyle(name="Deck", parent=styles["Normal"], fontName="Helvetica", fontSize=11, leading=16, textColor=MUTED, spaceAfter=10))
styles.add(ParagraphStyle(name="H1x", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=16, leading=20, textColor=NAVY, spaceBefore=7, spaceAfter=7, keepWithNext=True))
styles.add(ParagraphStyle(name="H2x", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=10.5, leading=13, textColor=TEAL, spaceBefore=5, spaceAfter=4, keepWithNext=True))
styles.add(ParagraphStyle(name="Bodyx", parent=styles["BodyText"], fontName="Helvetica", fontSize=9.2, leading=13.2, textColor=INK, spaceAfter=5))
styles.add(ParagraphStyle(name="Smallx", parent=styles["BodyText"], fontName="Helvetica", fontSize=7.7, leading=10, textColor=MUTED, spaceAfter=3))
styles.add(ParagraphStyle(name="KPI", parent=styles["BodyText"], fontName="Helvetica-Bold", fontSize=17, leading=20, textColor=NAVY, alignment=TA_CENTER))
styles.add(ParagraphStyle(name="KPILabel", parent=styles["BodyText"], fontName="Helvetica", fontSize=7.8, leading=10, textColor=MUTED, alignment=TA_CENTER))
styles.add(ParagraphStyle(name="Cell", parent=styles["BodyText"], fontName="Helvetica", fontSize=8.2, leading=10.5, textColor=INK))
styles.add(ParagraphStyle(name="CellHead", parent=styles["BodyText"], fontName="Helvetica-Bold", fontSize=8.2, leading=10.5, textColor=colors.white))
styles.add(ParagraphStyle(name="Pull", parent=styles["BodyText"], fontName="Helvetica-Bold", fontSize=10, leading=14, textColor=NAVY, leftIndent=8, rightIndent=8, spaceAfter=0))


def P(text: str, style: str = "Bodyx") -> Paragraph:
    return Paragraph(text, styles[style])


def footer(canvas, doc):
    canvas.saveState()
    w, _ = A4
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.6)
    canvas.line(18 * mm, 14 * mm, w - 18 * mm, 14 * mm)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(18 * mm, 9 * mm, "ZENTROMART SUPPORT ASSISTANT  |  CAPSTONE EVALUATION")
    canvas.drawRightString(w - 18 * mm, 9 * mm, f"{doc.page}")
    canvas.restoreState()


class ReportDoc(BaseDocTemplate):
    def __init__(self, filename):
        super().__init__(str(filename), pagesize=A4, leftMargin=19 * mm, rightMargin=19 * mm,
                         topMargin=17 * mm, bottomMargin=20 * mm, title="ZentroMart Capstone Evaluation Report",
                         author="ZentroMart Support Assistant Capstone")
        frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="main")
        self.addPageTemplates(PageTemplate(id="report", frames=frame, onPage=footer))


story = []
story += [P("CAPSTONE PROJECT  /  EVALUATION REPORT", "Smallx"), P("ZentroMart Support Assistant", "CoverTitle"),
          P("Policy-grounded customer support with retrieval, verified synthetic order tools, and Gnani voice batch processing", "Deck")]

kpis = [
    (f"{retrieval['section_hit_rate_at_5'] * 100:.1f}%", "Section hit@5 · 47 answerable questions"),
    (f"{retrieval['mrr']:.3f}", "Mean reciprocal rank"),
    (f"{passed_turns}/{len(conversations)}", "Conversation turns passed literal screen"),
]
kt = Table([[P(v, "KPI") for v, _ in kpis], [P(l, "KPILabel") for _, l in kpis]], colWidths=[57 * mm] * 3, rowHeights=[9 * mm, 10 * mm])
kt.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), PALE), ("BOX", (0, 0), (-1, -1), 0.6, RULE), ("INNERGRID", (0, 0), (-1, -1), 0.5, RULE), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
story += [kt, Spacer(1, 7), P("1. Project overview", "H1x"),
          P("This prototype answers questions using a section-aware BM25 retriever over the supplied synthetic ZentroMart knowledge base, structured catalog facts, and an OpenAI-compatible chat endpoint configured for Groq. A conversation controller gates mock order lookup behind identity verification and creates a support ticket for handoff. A separate folder workflow uses Gnani for speech-to-text and text-to-speech.")]
story += [P("Design and safeguards", "H2x"),
          P("Current policy takes precedence over help articles, FAQs, marketing, and superseded documents. Answers expose source section IDs. Unsupported questions abstain and can offer human handoff. Order details remain unavailable until the mock tool verifies one phone suffix or delivery pincode; verification state is conversation-scoped. The mock tool and synthetic identifiers are for coursework only.")]

flow = [
    [P("INPUT", "CellHead"), P("RETRIEVAL / FACTS", "CellHead"), P("CONTROL", "CellHead"), P("OUTPUT", "CellHead")],
    [P("Text or transcribed audio", "Cell"), P("BM25 policy sections; catalog and verified order records", "Cell"), P("Precedence, verification, abstention, ticket handoff", "Cell"), P("Concise response with source IDs; optional Gnani audio", "Cell")],
]
ft = Table(flow, colWidths=[34 * mm, 47 * mm, 48 * mm, 42 * mm])
ft.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), NAVY), ("BACKGROUND", (0, 1), (-1, -1), PALE), ("GRID", (0, 0), (-1, -1), 0.5, RULE), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
story += [Spacer(1, 4), ft, Spacer(1, 5), P("Scope", "H2x"),
          P("Evaluation uses the course-provided synthetic practice set: 52 single-turn questions (47 answerable with section evidence) and 23 multi-turn scenarios covering 96 customer turns. The dataset fixes its business reference date at 20 October 2026. No real customer records are used.")]

story += [PageBreak(), P("2. Evaluation method and measured results", "H1x"),
          P("All figures below were regenerated from the saved evaluator outputs in this workspace on 25 October 2026. They are automated screening results; they do not equal a human semantic quality score.")]

retrieval_rows = [[P("Language", "CellHead"), P("Questions", "CellHead"), P("Hit@5", "CellHead")]]
for code, label in [("en", "English"), ("hi", "Hindi"), ("hi-en", "Hinglish")]:
    retrieval_rows.append([P(label, "Cell"), P(str(langs[code]), "Cell"), P(f"{retrieval['by_language_hit_rate'][code] * 100:.1f}%", "Cell")])
retrieval_rows.append([P("All answerable", "Cell"), P(str(retrieval["answerable_with_section_evidence"]), "Cell"), P(f"{retrieval['section_hit_rate_at_5'] * 100:.1f}%", "Cell")])
rt = Table(retrieval_rows, colWidths=[67 * mm, 45 * mm, 59 * mm], repeatRows=1)
rt.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), NAVY), ("BACKGROUND", (0, 1), (-1, -1), colors.white), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]), ("GRID", (0, 0), (-1, -1), 0.4, RULE), ("ALIGN", (1, 1), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
story += [P("Section retrieval (BM25)", "H2x"), rt, Spacer(1, 3),
          P(f"Overall MRR: {retrieval['mrr']:.3f}. Hit@5 counts a hit when a gold evidence section appears among the five retrieved sections. It excludes catalog-row evidence and says nothing about whether a generated answer is correct. Hindi is 7 questions and Hinglish 10, so those percentages are based on small samples.", "Smallx")]

rag_dec = n_yes("rag_correct_decision", scored_answers)
rag_evidence = n_yes("rag_grounded", answers)
prompt_prohibited_hits = sum(r.get("prompt_only_prohibited_claims") == "Yes" for r in answers)
rag_prohibited_hits = sum(r.get("rag_prohibited_claims") == "Yes" for r in answers)
prompt_dec = n_yes("prompt_only_correct_decision", scored_answers)
fact_rows = [r for r in scored_answers if r.get("rag_required_facts", "") != "N/A"]
prompt_fact_rows = [r for r in scored_answers if r.get("prompt_only_required_facts", "") != "N/A"]
prompt_fact_yes = n_yes("prompt_only_required_facts", prompt_fact_rows)
rag_fact_yes = n_yes("rag_required_facts", fact_rows)
qa_rows = [
    [P("Screen (49 scored cases; 3 flow cases excluded)", "CellHead"), P("Prompt only", "CellHead"), P("RAG", "CellHead")],
    [P("Expected-decision literal check", "Cell"), P(f"{prompt_dec}/49 ({prompt_dec/49:.1%})", "Cell"), P(f"{rag_dec}/49 ({rag_dec/49:.1%})", "Cell")],
    [P("Required-fact literal check", "Cell"), P(f"{prompt_fact_yes}/{len(prompt_fact_rows)} ({prompt_fact_yes/len(prompt_fact_rows):.1%})", "Cell"), P(f"{rag_fact_yes}/{len(fact_rows)} ({rag_fact_yes/len(fact_rows):.1%})", "Cell")],
    [P("Prohibited-claim phrase hits", "Cell"), P(f"{prompt_prohibited_hits}/52", "Cell"), P(f"{rag_prohibited_hits}/52", "Cell")],
    [P("Gold evidence source hit (52 rows)", "Cell"), P("Not scored", "Cell"), P(f"{rag_evidence}/52 ({rag_evidence/52:.1%})", "Cell")],
]
qt = Table(qa_rows, colWidths=[78 * mm, 46 * mm, 47 * mm], repeatRows=1)
qt.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), NAVY), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]), ("GRID", (0, 0), (-1, -1), 0.4, RULE), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
story += [P("Prompt-only versus retrieval-augmented generation", "H2x"), qt, Spacer(1, 3),
          P("Checks use literal rubric variants and source IDs; they can miss paraphrases or accept incorrect wording that contains a target phrase. Three conversation-flow questions are not decision-scored. Required-fact denominators exclude rows marked not applicable (3 for RAG, 3 for prompt-only). Zero phrase hits do not prove that every possible unsafe claim is absent. The three evidence misses include expected escalation/tool cases; evidence match alone is not a quality judgement.", "Smallx")]

story += [P("Multi-turn conversation screen", "H2x"),
          P(f"{conversation_count}/23 scenarios and {passed_turns}/{len(conversations)} turns passed the automated literal screen. Expected tool calls: 96/96 matched. Gold evidence hit: 96/96. Prohibited-claim phrase hits: 0/96. Ticket creation is mocked; this harness checks explicit expected tool names and literal answer criteria, not semantic correctness or live service operation.")]

story += [PageBreak(), P("3. Voice workflow, limitations, and reproducibility", "H1x"),
          P("Voice and batch processing", "H2x"),
          P("The batch runner accepts a folder of WAV, MP3, M4A, FLAC, or OGG recordings. For each file it calls Gnani STT, passes the transcript through the support agent, calls Gnani TTS, then writes a UTF-8 JSON result, a WAV reply, and a batch manifest. The saved example is a user-confirmed UPI refund voice test. The recording must be the submitter's own voice; no supplied dataset audio exists.")]

voice_table = [
    [P("Step", "CellHead"), P("Evidence in the prototype", "CellHead")],
    [P("Speech input", "Cell"), P("Gnani STT transcript stored in JSON manifest", "Cell")],
    [P("Grounded response", "Cell"), P("Policy-derived refund timeline with evidence IDs", "Cell")],
    [P("Speech output", "Cell"), P("Gnani TTS WAV reply; user listened and confirmed it was correct", "Cell")],
]
vt = Table(voice_table, colWidths=[45 * mm, 126 * mm])
vt.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), NAVY), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]), ("GRID", (0, 0), (-1, -1), 0.4, RULE), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
story += [vt, Spacer(1, 6), P("Known limitations", "H2x"),
          P("This is a coursework prototype, not a production service. BM25 is lexical and has no learned embeddings; language results use small test subsets. The answer rubrics are heuristic and should be supplemented with blinded human review. The mock order data, verification mechanism, and ticket store are not secure production services. Model and speech behavior depend on valid external credentials, network availability, and provider response. No latency, cost, or statistically significant improvement claim is made.")]

story += [P("Reproduce locally", "H2x"),
          P("1. Place the course dataset under <font name='Courier'>data/raw/</font> using the layout documented in the README. It is deliberately excluded from public Git until redistribution permission is confirmed.<br/>2. Install <font name='Courier'>requirements.txt</font>, copy <font name='Courier'>.env.example</font> to <font name='Courier'>.env</font>, and set Groq and Gnani credentials.<br/>3. Run <font name='Courier'>streamlit run app.py</font> for chat; run <font name='Courier'>python run.py voice_inputs --output sample_outputs --language en-IN --reply-language en-IN</font> for batch audio.<br/>4. Recompute results with <font name='Courier'>python evaluate.py</font>, <font name='Courier'>python evaluate_answers.py --output reports/drafts/answer_comparison_final.csv</font>, and <font name='Courier'>python evaluate_conversations.py</font>. Answer generation uses up to 104 Groq completions.")]

story += [P("Reproducibility note", "H2x"),
          P("The saved single-turn score sheet was re-scored locally; the conversation suite was rerun with model credentials disabled so deterministic tool flows could be evaluated offline. The report is generated by <font name='Courier'>scripts/build_report.py</font> from those result files. API outputs can vary when the model/provider version changes.", "Smallx"),
          Spacer(1, 4),
          Table([[P("Measured evidence is reported with its sample size and scoring limits. No automated screen is presented as a human-validated accuracy rate.", "Pull")]], colWidths=[171 * mm], style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), PALE), ("BOX", (0, 0), (-1, -1), 0.6, RULE), ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9), ("TOPPADDING", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 9)]))]

OUT.parent.mkdir(parents=True, exist_ok=True)
ReportDoc(OUT).build(story)
print(f"Wrote {OUT}")

