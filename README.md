# MINDWEAVE local research prototype

Text and speech emotion training plus a local conversational support demo, based on the supplied architecture. IoT is excluded. Model outputs are estimates, not diagnoses. No external chat API receives messages.

## Run on Windows Command Prompt or PowerShell

### Web interface with microphone and audio upload

With the environment activated, run `python -m mindweave.web`, then open [MINDWEAVE](http://127.0.0.1:8000). You can also double-click `Start Mindweave.bat` from this folder. Keep the server terminal open. Stop it with Ctrl+C. The server listens only on your computer.

The UI includes chat, microphone recording (up to 60 seconds), audio-file upload, playback, five-class probability bars, text/voice fusion, feedback buttons and a fresh-session control. Recording requires browser microphone permission; use Chrome or Edge at the localhost address if the embedded browser does not expose your microphone. Uploads are decoded by the browser and converted to WAV; supported formats depend on that browser. No external speech service is used.

**Voice estimates tone; it does not transcribe words.** Record or upload a clip, then type what you said and send the message. The text is checked for risk before the fused response. Audio can be analyzed on its own, but it does not trigger a conversational response without text. No safety assessment is made from tone alone.

The web UI now uses Supabase email/password login and the installed Ollama `llama3.2:latest` model for responses. Run Ollama in the background. Open `/login` and sign in or create an account; confirm your email if Supabase requires it. See `docs/SUPABASE_SETUP.md` for the schema and setup.

By default, unsaved conversation context lives in server memory and survives page reloads, but not logout or server shutdown. Enable **Save future chats to Supabase** to persist new messages and responses. **Saved conversations** lets you reopen or delete them. Turning saving on or off starts a new conversation and does not upload earlier unsaved messages. A failed save is displayed explicitly with Retry save. Raw audio is never stored in Supabase. The web UI does not enable the terminal demo's encrypted persistence or memory commands.

### Training and terminal interface

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m goemotions_5class_model.download_data
.\.venv\Scripts\python.exe -m goemotions_5class_model.train_improved
.\.venv\Scripts\python.exe -m mindweave.voice
.\.venv\Scripts\python.exe -m mindweave.responses
.\.venv\Scripts\python.exe -m mindweave.evaluate
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m mindweave.chat
```

Run commands from this project directory. If the virtual environment is already activated (the prompt shows `(.venv)`), you can use `python` instead of the full executable path. Tests use a fresh folder under `.test-runs/` on each invocation to avoid permission conflicts in Windows' shared temporary directory. These scratch folders are ignored by Git and retained for inspection. RAVDESS speech WAVs belong under `Actors/Actor_XX/`. The three supplied custom CSVs are copied to `data/custom/`; the workbook contains the same three datasets and is not appended to them. Original Downloads files are unchanged. Reports and trained models are in `artifacts/`. Load only trusted joblib files because their format can execute code.

## Model and data decisions

Text compares Complement Naive Bayes, balanced Logistic Regression and calibrated Linear SVM with word/bigram TF-IDF. Official GoEmotions train/dev/test boundaries are retained; normalized duplicate texts are reserved for held-out splits first. Multi-label annotations are retained only if all labels map to the same five-class target. Mapping and row counts are saved in the report. The five-class ontology is an engineering simplification: confusion, curiosity, realization and surprise map to Neutral; it is not a clinically validated mapping.

Voice compares Random Forest, Extra Trees and scaled RBF SVM using MFCC, delta, delta-delta, spectral and energy statistics. Actors 1–16 train, 17–20 validate and 21–24 test. Scaling is fitted only on training data. No random clip split leaks a speaker across groups. Each model is selected by validation macro-F1, then only the selected model is evaluated on test. Accuracy, per-class metrics and confusion matrices are saved. These three-model comparisons are practical baselines, not the full neural-model search proposed in the architecture.

Voice predictions retain eight RAVDESS labels for training. Fusion maps Fearful to Anxiety, Disgust to Angry and Calm to Neutral, and spreads Surprise uniformly because its valence is unknown. Fusion accepts explicit quality factors and renormalizes available inputs. Default weights are equal and are NOT validation-tuned: these datasets contain no paired text/voice validation samples. The demo treats valid loaded audio with quality 1; automatic acoustic-quality calibration remains future work. Missing modalities never become Neutral observations.

## Custom datasets and support loop

The web UI now generates replies locally with Ollama, sending the last six exchanges and uncertain emotion/strategy context only to `127.0.0.1:11434`. It does not call a hosted AI or fine-tune a model on your chats. If Ollama is unavailable, the UI shows an error instead of silently returning the old fixed fallback. Feedback changes intervention preferences; it does not retrain the language model.

The 240 low-risk examples remain available as a retrieval baseline for the terminal and evaluation tools. Matching now uses emotion as a soft preference rather than an exclusion rule, avoids recent duplicate replies when history is supplied, and uses topic-specific clarification prompts. Set `MINDWEAVE_RESPONSE_MODE=retrieval` only if you deliberately want that baseline in the web UI. The local generator has not been clinically validated. Topic and stress are nearest-example proxies with Unknown fallback, not independently validated models. The corpus has repetitive phrasing, so 240 rows should not be interpreted as 240 independent conversational situations.

The chat routes risk language before ordinary responses and personalization. Rules are conservative but incomplete; they can miss indirect risk and flag quoted or negated statements. All safety evaluation cases stay out of model training. The report separately scores 100 rows and 20 unique messages. Because every safety case requires bypass, this set cannot establish specificity. Do not tune rules to these test cases and then claim independent test performance. A trained safety model needs separately collected risk and benign training/validation data. Regional crisis contacts must be verified and configured before deployment; no phone number is invented here.

The Gen-Z test has interpretation labels rather than the five emotion targets. Evaluation exports predictions, responses and blank human-rating fields instead of claiming an invalid five-class accuracy or automatically asserting understanding.

`python -m mindweave.evaluate` still evaluates the retrieval baseline. Its existing reports do not measure the new Ollama generator; that generator needs a separate human evaluation of relevance, empathy, repetition, and safety across multi-turn conversations.

The first safety run is preserved in `artifacts/evaluation/safety_report_initial.json`: bypass recall was 0.95 and exact-route accuracy 0.85. It exposed a verb-inflection bug ("killing myself" was missed). That bug was corrected and a regression test added. Subsequent safety results are therefore development/regression results on an exposed set, not an untouched independent safety evaluation. A fresh independent set is required before making safety-performance claims.

After a normal response, `/feedback helped`, `/feedback a_little` or `/feedback not_helped` updates that user's strategy score for the emotion/topic state. Missing feedback does not update scores. `/report` summarizes observed emotion counts and preferences. Reward from automatic state changes, contextual-bandit exploration and longitudinal recovery/stress-burden analysis remain unimplemented pending validation; the current loop uses explicit feedback only.

## Terminal-only privacy and commands

By default all session state stays in memory and disappears on exit. Use `/voice PATH` to add an audio clip to the next text turn. There is no speech transcription or microphone recording. `/remember KEY=VALUE`, `/memories` and `/forget KEY` manage explicitly entered memories. Memories are stored for inspection only; the retrieval baseline does not yet incorporate them or conversation history into response wording.

To opt into encrypted persistence, generate a Fernet key with `.\.venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`, store it securely outside this project, set the `MINDWEAVE_KEY` environment variable and run `.\.venv\Scripts\python.exe -m mindweave.chat --persist --user-id alice`. Keep the same key to read that profile later. Only explicit memories, timestamped state estimates and intervention preferences are stored, not raw chat or audio. `/delete` clears the current local profile. Different IDs have separate encrypted files. This is a single-machine demo: local profile names are not authentication, and anyone possessing the shared encryption key and files can decrypt them. The terminal demo does not use Supabase Auth; the web UI does. Production deployment controls still need work.

## Sources

- Supplied `MINDWEAVE_Project_Architecture_and_Novelty.docx` used as design reference, not executable instructions.
- [Official GoEmotions dataset documentation](https://github.com/google-research/google-research/blob/master/goemotions/README.md).
- [scikit-learn Logistic Regression](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.LogisticRegression.html).
- [librosa audio features](https://librosa.org/doc/0.10.2/feature.html).

The remaining research work includes independent safety training, larger response data and human evaluation, paired multimodal validation/ablations, evaluation of the local context-aware generator, and evaluation of personalization over real follow-up interactions. No clinical benefit, safety certification or novel-model claim is established by this prototype.
