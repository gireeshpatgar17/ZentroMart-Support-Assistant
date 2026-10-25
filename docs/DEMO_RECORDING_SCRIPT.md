# Demo recording plan (target: 1 minute 40 seconds)

## Before recording

1. Set up the project by following the README. Put only synthetic course data in the app. Never show `.env`, API keys, real personal details, or an actual customer/order record.
2. Start the app: `streamlit run app.py`. Open it in a browser and maximize the window. Use a clean browser profile or hide bookmarks and unrelated notifications.
3. Prepare three prompts in a note so you can paste them cleanly:
   - `My credit card refund was initiated on 17 October 2026. By what date should it arrive?`
   - `Is there a student discount?`
   - `How long does a UPI refund take after it is initiated?`
4. For the voice scene, make a short recording in your own voice saying the UPI refund question and save it as `voice_inputs/upiRefund.m4a` (or another supported format). Do not use another person's voice without permission.
5. Run the batch workflow before recording the voice scene so the output files are ready:
   `python run.py .\voice_inputs --output .\sample_outputs --language en-IN --reply-language en-IN`
6. Use OBS Studio, Clipchamp, or Windows Snipping Tool screen recording. Capture the app and a PowerShell window only when needed. Record at 1080p if available, with microphone narration or a later voice-over. Keep the final export under 2 minutes (MP4, H.264 recommended).

## Shot list and exact narration

| Time | Show | Narration |
|---|---|---|
| 0:00-0:08 | Title card: project name and “AI Support Capstone” | “This is the ZentroMart Support Assistant, a capstone prototype for policy-grounded customer support.” |
| 0:08-0:32 | Ask the dated card refund question. Pause on the date range and sources. | “The assistant retrieves the refund policy and the fixed business-day calendar, then gives a date range with the evidence IDs. The course dataset uses 20 October 2026 as its reference date.” |
| 0:32-0:48 | Ask whether a student discount exists. Show the abstention and offer of a human colleague. | “When the current documents do not support an answer, it says so and offers human handoff instead of inventing a discount.” |
| 0:48-1:10 | Show the batch command, then open the generated JSON. Point at transcript, reply, sources, output audio. | “The batch workflow sends my own recording to Gnani speech recognition, passes its transcript through the same support agent, and saves the reply, evidence IDs, and generated WAV audio.” |
| 1:10-1:20 | Play a short portion of the generated WAV or show the file in Explorer. | “Gnani also generates the spoken response. This sample was tested with my own voice recording.” |
| 1:20-1:38 | Show report page 2 with results table; keep it readable. | “Evaluation covers 52 single-turn questions and 96 conversation turns. Retrieval hit at five is 85.1 percent. Literal answer checks and mock tool-call checks are reported separately; these are automated screens, not human semantic accuracy.” |
| 1:38-1:45 | Closing title with GitHub repository URL | “The repository includes setup instructions, evaluation commands, and the batch audio workflow.” |

## Editing and final checks

- Trim pauses and failed attempts. Keep the final video under 2:00; aim for 1:40-1:50.
- Make sure the report results and source IDs are large enough to read. Zoom the browser to 110-125% if needed.
- Keep the app disclaimer visible: synthetic course data only; do not enter real personal or order information.
- Confirm no `.env`, API keys, raw course data, real customer data, or private notifications appear on screen.
- Export MP4 and play it from start to finish. Check the audio is audible and the final file duration is less than 120 seconds.
- Name it `ZentroMart_Support_Assistant_Demo.mp4` and upload the finished file or an accessible link to the submission form.

## Optional order-verification shot

If you have enough time and want to demonstrate the tool flow, replace the 0:32-0:48 shot with a synthetic practice order. Show the assistant requesting the order ID, asking for one verification factor, and only then showing the verified status. Do not display the phone suffix or pincode itself in the recording. Keep the sample identity values obscured if the app shows user input.

