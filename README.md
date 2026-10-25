# ZentroMart Support Assistant

Course capstone prototype for *From Tokens to Transformers*. It demonstrates policy-grounded support chat, verified lookups against synthetic orders, ticket handoff, and batch voice processing with Gnani STT/TTS and Groq chat completions.

> Coursework prototype only. ZentroMart and the supplied customer/order records are synthetic. Do not use this code or mock identity checks for real customer data. Do not commit API keys, customer recordings, or the course dataset.

## Features

- Section-aware BM25 retrieval with current-policy precedence and source IDs.
- Structured catalog facts, refund date calculations using the dataset's fixed 20 October 2026 reference date, and multilingual English/Hindi/Hinglish responses.
- Multi-turn order lookup with phone-suffix or delivery-pincode verification, one retry, and a mock ticket handoff.
- Streamlit chat interface.
- Folder-based voice workflow: Gnani STT -> support answer -> Gnani TTS; saves JSON per input, WAV reply audio, and a batch manifest.
- Retrieval, prompt-only/RAG, and multi-turn evaluation scripts.

## Requirements

- Python 3.11 or newer (the implementation was run with Python 3.13 in this workspace).
- A Groq API key for model-generated chat and a Gnani API key for voice batch processing.
- The course dataset archive downloaded separately from the course. It is not stored in this public repository because redistribution terms were not confirmed.

## Setup

### Windows PowerShell

```powershell
git clone https://github.com/gireeshpatgar17/ZentroMart-Support-Assistant.git
cd ZentroMart-Support-Assistant
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Copy the course-provided dataset ZIP onto your machine, then prepare the runtime folder:

```powershell
python scripts/prepare_dataset.py "C:\path\to\Capstone_Project_Dataset_FTTT_2026.zip"
```

The script safely extracts the dataset into `data/raw/`, refuses to overwrite a non-empty destination, and validates the expected folder layout. `data/raw/` is ignored by Git. To validate the dataset:

```powershell
python data/raw/validate_dataset.py
```

Create `.env` from the placeholder file and add your own credentials:

```powershell
Copy-Item .env.example .env
```

Set `GROQ_API_KEY` and `GNANI_API_KEY` in `.env`. `.env` is ignored by Git; never paste keys into chat, source files, screenshots, or the repository. The configured default model is `openai/gpt-oss-20b` on Groq's OpenAI-compatible endpoint.

## Run the chat app

```powershell
streamlit run app.py
```

Use synthetic examples only. The order verification tool is a coursework simulation, not authentication.

## Run batch audio processing

Put one or more recordings in `voice_inputs/`. Supported extensions: `.wav`, `.mp3`, `.m4a`, `.flac`, `.ogg`.

```powershell
python run.py .\voice_inputs --output .\sample_outputs --language en-IN --reply-language en-IN
```

For each audio file the command writes `<name>.json`, `<name>_reply.wav`, and a `batch_manifest.json`. The JSON contains the source section IDs used by the agent. Gnani is used for both speech directions; there is no alternate speech-provider fallback. The course archive does not contain audio, so create your own short test recording.

## Evaluation

The supplied practice data has 52 single-turn questions and 23 multi-turn scenarios (96 turns). The reproducible results in `output/pdf/ZentroMart_Capstone_Report.pdf` were measured from evaluator outputs and are screening results, not human semantic grading.

```powershell
python evaluate.py --output .\reports\drafts\retrieval_final.json
python evaluate_answers.py --output .\reports\drafts\answer_comparison_final.csv
python score_answer_comparison.py --input .\reports\drafts\answer_comparison_final.csv --output .\reports\drafts\answer_comparison_final_scored.csv
python evaluate_conversations.py --offline
```

`evaluate_answers.py` can make up to 104 model completions. It compares prompt-only and RAG answers using literal rubric variants and source IDs. `evaluate_conversations.py --offline` avoids model calls and checks deterministic tool flows plus literal answer criteria; ticket creation is mocked. Read the report for sample sizes, denominators, and limitations.

To regenerate the report from saved evaluator outputs, install `reportlab` and run:

```powershell
pip install -r requirements-report.txt
python scripts/build_report.py
```

## Repository map

```text
app.py                          Streamlit chat interface
run.py                          Gnani batch audio workflow
src/                            Retrieval, answers, conversation safety, evaluation
scripts/prepare_dataset.py      Local-only dataset setup helper
scripts/build_report.py         Rebuilds the measured PDF report
evaluate.py                     Retrieval-only metric
evaluate_answers.py             Prompt-only versus RAG answer generation
score_answer_comparison.py      Literal scoring without API calls
evaluate_conversations.py       Multi-turn scenario and tool-call checks
docs/                           Case notes, checklist, and demo recording script
output/pdf/                     Four-page maximum measured-results report
sample_outputs/                 Example JSON manifest and generated voice reply
data/raw/                       Course data on the local machine only; Git-ignored
```

The short demo recording plan and narration are in [`docs/DEMO_RECORDING_SCRIPT.md`](docs/DEMO_RECORDING_SCRIPT.md).

