# Training and verification results

## Web accounts and local generation update

The web UI now defaults to the already installed Ollama `llama3.2:latest` model. A two-turn live inference check confirmed that an exam-panic message and a math/two-hour follow-up receive distinct, context-related replies. This smoke check is not a formal improvement benchmark or a safety validation. The original text/voice model metrics below are unchanged.

Supabase Auth is configured, and all three application tables exist after the user applied the schema. Anonymous requests to these tables are denied. Local HTTP tests cover authentication gating, session separation, logout, opt-in persistence, history reopening, rejection of another account's history ID by the adapter, and explicit save-failure behavior using a simulated provider. Real-user login and two-account row-level isolation still require live account verification; no test accounts or verification emails were created by the assistant.

The test suite has 17 passing tests. New tests also verify that conversation history reaches the local model, the generator endpoint stays on loopback, risk messages bypass generation, and retrieval does not discard an exact match just because emotion classification disagrees.

## Original training run

Run date: 2026-10-07. Exact installed package versions are recorded in `requirements-lock.txt`.

| Branch | Candidate | Validation macro-F1 | Selected test macro-F1 | Selected test accuracy |
|---|---|---:|---:|---:|
| Text | Complement NB | 0.5713 | — | — |
| Text | Logistic Regression | 0.6227 | 0.6320 | 0.7007 |
| Text | Calibrated Linear SVM | 0.6169 | — | — |
| Voice | Random Forest | 0.4337 | — | — |
| Voice | Extra Trees | 0.4020 | — | — |
| Voice | RBF SVM | 0.4476 | 0.4716 | 0.4833 |

Only selected models were evaluated on test. Text splits retain 39,708 train, 4,983 validation and 5,031 test examples after ambiguity and duplicate filtering. Anxiety has only 537 training examples, compared with 16,907 Neutral examples. This imbalance and the difference between Reddit comments and student-support messages limit domain performance. A smoke test classified an explicit exam-panic message as Neutral; do not interpret aggregate performance as reliability on every support message.

All 1,440 speech clips were used across disjoint actor groups: 960 training clips, 240 validation and 240 test. Reports contain per-class metrics, confusion matrices and the voice split manifest.

The response index contains 240 unique messages. All cells in the workbook's three sheets were compared against the corresponding CSVs and matched exactly; the workbook was therefore not added as duplicate training data.

Seven automated tests passed, covering missing/zero-quality modalities, probability validation, voice alignment, safety routing, feedback personalization, encrypted user separation/deletion, actor separation and text leakage/ambiguity filtering. An interactive smoke test exercised a normal response, feedback, explicit memory, reporting, safety bypass and rejection of feedback after a safety turn.

Initial safety rules bypassed ordinary generation on 95/100 rows (19/20 unique messages); exact route accuracy was 85%. The exposed inflection bug was repaired. The original report is preserved separately. Later scores are regression results, not independent evidence of safety. No benign held-out safety set exists, so specificity remains unmeasured. The slang evaluation exports predictions and blank human ratings; no automatic claim of contextual understanding is made.

Remaining architecture components and limitations are described in README.md. This is a runnable local baseline, not a completed production mental-health service or the full set of research experiments.
