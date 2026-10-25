# Case brief and dataset requirements

## User goal

Complete the remaining individual capstone for IIT Guwahati's *From Tokens to Transformers: A Course on GenAI x LLM Mastery*. The course asks for a practical GenAI project and final report; the submission page asks for a PDF report and relevant source-code or live-demo links. The available date in the pasted course information is 25 October 2026, 11:59 PM IST.

## Case brief, translated into project requirements

Build a ZentroMart support agent that can answer chat/email/ticket questions using company knowledge and structured order/catalog data. The dataset README divides work into four steps:

1. Retrieve and answer from the knowledge base, with section IDs and practice-question evaluation.
2. Use structured data and the supplied offline tools for product, delivery, and verified order details.
3. Maintain multi-turn state; create tickets and hand off where required.
4. Add the required voice path: transcribe recorded customer audio using Gnani STT and return speech using Gnani TTS. The brief requires Gnani as the only speech provider and a batch command that accepts an audio folder and saves text, audio and retrieved sources. No audio samples are supplied; a personal test recording is required.

The ZIP README and schema are the detailed implementation authority for the dataset. Its requirements include:

- Keep `[SECTION-ID]`, document status and `effective_from` metadata in retrieval chunks.
- Resolve conflicts using `KB-00.1`: current policy > agent guide > help article > FAQ > marketing. Superseded policies are not current authority. Human support logs are language examples, not policy truth.
- Use dataset fixed date 20 October 2026 for delay/deadline computations; business days are Monday-Saturday excluding `holidays.csv`. Return windows are calendar days.
- Answer in the customer's language. Support English, Hindi and Hinglish; identify native-language support limitations honestly.
- Use `practice/questions.csv` (52 rows, including ASR-style variants) and `practice/conversations.csv` (96 turns across 23 conversations) as gold evaluation data. Respect alternative facts in `must_include` and forbidden claims in `must_not_include`.
- For order lookup, ask once for a phone suffix or pincode, never reveal expected secrets, allow one retry, and hold verified state only in the current chat. The mock tools are not production authentication.
- For escalation, create a ticket first and only confirm it if the tool returns `created=True`; do not promise unapproved outcomes or times.

## Dataset contents

The course archive contains 21 knowledge documents; CSVs for 70 products, 300 customers, 1,000 orders, 1,783 order lines, 36 pincodes, 4 holidays and 244 support logs; 52 practice questions; 23 conversations (96 customer turns); and an offline mock order/ticket package. It contains no real customer records and no audio files.

## Scope decision

Build the text/RAG, structured-tool and evaluation path, then complete Gnani voice once API access and a personal recording are available. Voice is a scored core requirement (20/100 marks), not an optional extension. The final submission also requires a public repo, run command, report up to four pages, demo up to two minutes and submission ZIP; exclude the dataset copy, API keys, virtual environments and real customer data from that ZIP. Hardcoded answers and hand-edited test outputs are disallowed.

