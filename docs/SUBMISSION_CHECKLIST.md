# Capstone submission checklist

## Four required deliverables

- [x] **Public GitHub repository** published at `https://github.com/gireeshpatgar17/ZentroMart-Support-Assistant`; verify the URL opens without signing in.
- [ ] **Demo video**, maximum 2 minutes. Record your own screen using `DEMO_RECORDING_SCRIPT.md`; target 1:40-1:50.
- [x] **Evaluation report PDF**, 3 pages, with actual local evaluator results and explicit metric limitations.
- [x] **Working project**, including the folder-based Gnani STT -> agent -> Gnani TTS workflow and example JSON/WAV output. The course dataset and own input recording remain local; follow README dataset setup.

## Measured results represented in the report

- BM25 section hit@5: 85.1% across 47 answerable questions; MRR: 0.764.
- Hit@5 by language: English 76.7% (n=30), Hindi 100% (n=7), Hinglish 100% (n=10).
- Prompt-only versus RAG answer comparison: 49 scored decision cases (three conversation-flow questions excluded). Deterministic RAG decision check 49/49; prompt-only 4/49. Required-fact checks exclude non-applicable rows: RAG 46/46; prompt-only 6/46. RAG gold-evidence source hit 49/52.
- Conversation evaluator: 23/23 scenarios and 96/96 turns pass literal checks; 96/96 expected mock tool calls match.
- These are heuristic literal/source/tool checks, not human semantic answer grading. The conversation harness uses mocked tickets.

## Privacy and package rules

- Do not commit `.env`, keys, the course dataset, input voice recordings, `.venv`, generated ticket logs, or raw evaluation CSVs.
- Course dataset redistribution terms were not confirmed. The README explains how to add a separately obtained archive to a local checkout.
- Keep the output ZIP separate for the course portal. Check the organizer's current Unstop page for the exact upload slot and deadline.

