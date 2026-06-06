---

## Predicting Abandonment Probability: From Heuristics to a Production ML System

---

### Phase 1 — Data Collection & Label Definition

**Step 1: Define the prediction target**
- Label a session as **abandoned = 1** if the user reached any funnel step but never hit the payment confirmation event within a session timeout window (e.g., 30 min).
- Label as **completed = 0** if a booking confirmation event fired.
- Be precise: exclude sessions where a server-side error caused the drop (those are noise, not intent signals).

**Step 2: Build the historical event log**
Pull session-level clickstream data from your analytics pipeline (GA4 / Segment / Snowplow). Each row = one session. Columns include:

| Feature Category | Examples |
|---|---|
| Behavioral signals | idle durations, tab switch count, mouse-leave events, back-button presses |
| Funnel position | last step reached (`search`, `selection`, `passenger`, `payment`) |
| Temporal | time-of-day, day-of-week, session duration so far |
| Price context | fare shown, whether price changed since search, price vs. user's past bookings |
| Device/channel | mobile vs. desktop, organic vs. paid, browser |
| User history | past bookings, previous abandoned sessions, loyalty tier |
| Friction signals | form field deletions, rapid clicks, payment page revisits |

**Step 3: Handle class imbalance**
Most sessions complete, so abandonments are ~40–60% depending on the product. If severely imbalanced, use **stratified sampling** or **class weights** in the loss function — not SMOTE on raw events (that distorts temporal signals).

---

### Phase 2 — Feature Engineering

**Step 4: Build time-windowed features**
Don't use raw event counts — create rolling windows:
- Events in last 30s, 60s, 5 min
- Time spent per step vs. median time for that step
- Velocity of field interactions (form fill rate)

**Step 5: Encode funnel position as an ordinal feature**
Later steps = higher intent = different abandonment profile. Encode step as both a numeric ordinal AND as interaction terms with behavioral signals (e.g., `idle_60s × on_payment_step`).

**Step 6: Output a calibrated probability, not just a score**
The goal is $P(\text{abandon} \mid \text{session context})$, not just a ranking. This matters because intervention thresholds (0.45, 0.65, 0.80 in the current README) need to correspond to real probabilities, not arbitrary heuristic scores.

---

### Phase 3 — Model Training

**Step 7: Choose the right model class**

| Model | Why it fits |
|---|---|
| **Gradient Boosted Trees** (XGBoost / LightGBM) | Handles mixed feature types, non-linear interactions, fast to train, good calibration after isotonic regression |
| **Logistic Regression** | Strong baseline, directly interpretable, well-calibrated out of the box |
| **Neural net (LSTM/Transformer)** | If you have raw event sequences; captures temporal ordering |

Start with LightGBM + logistic regression as baseline. Add sequential models only if temporal ordering adds lift.

**Step 8: Split data correctly — time-based, not random**
This is a common interview trap. You **must** split by time:
- Train on sessions from months 1–8
- Validate on month 9
- Test on month 10

Random splits leak future behavioral patterns into training and inflate offline metrics.

**Step 9: Calibrate the output probability**
Tree models output scores, not probabilities. Use **Platt scaling** (logistic calibration) or **isotonic regression** on the validation set to ensure that a predicted score of 0.65 really means 65% of such sessions abandoned. Verify with a **reliability diagram (calibration curve)**.

---

### Phase 4 — Offline Validation

**Step 10: Choose metrics that match the business problem**

| Metric | Why |
|---|---|
| **AUC-ROC** | Overall discrimination across all thresholds |
| **AUC-PR (Precision-Recall)** | Better when positives (abandons you can recover) are the priority |
| **Log-loss / Brier score** | Measures calibration quality of the probability output |
| **Lift curve at top K%** | "If I intervene on the top 20% of sessions by score, what fraction are true abandoners?" |

**Step 11: Backtest intervention thresholds**
Replay the historical log through the trained model. For each candidate threshold (e.g., 0.45, 0.60, 0.70):
- Compute what % of sessions would have been triggered
- Estimate false positive rate (users who would have completed anyway, now shown an intrusive nudge)
- Estimate the upper bound on recoverable sessions (true positives)

This gives you a **Precision-Recall trade-off for interventions** before you touch production.

**Step 12: Feature importance & interpretability**
Use **SHAP values** (not raw feature importances — those are biased for high-cardinality features):
- Identify which signals actually drive abandonment vs. which are correlated noise
- This directly replaces the manual weight table in the current MVP (`idle_60s: 0.35`, `back_button: 0.25`, etc.) with data-driven attribution
- Use SHAP interaction values to find which features compound (e.g., `price_hover` + `on_payment_step` is far more predictive than either alone)

---

### Phase 5 — A/B Testing in Production

**Step 13: Define the experiment unit and randomization**
- Randomize at the **session or user level** (user-level avoids the same person seeing both experiences)
- Control group: no intervention (or current heuristic system)
- Treatment group: ML model-triggered intervention

**Step 14: Define guardrail and success metrics upfront**

| Type | Metric | Direction |
|---|---|---|
| Primary | Booking completion rate in triggered sessions | ↑ |
| Revenue | Revenue per session | ↑ |
| Guardrail | Completion rate for sessions NOT triggered | Must not ↓ |
| Guardrail | Customer satisfaction / complaint rate | Must not ↑ |

The guardrail on non-triggered sessions detects **cannibalization** — if your model flags too aggressively, it may interrupt users who were about to complete anyway.

**Step 15: Run a power analysis before launch**
Calculate minimum detectable effect (MDE) and required sample size. Abandonment recovery rates are often small (2–5% lift), so you may need weeks of data to achieve statistical significance. Use a two-proportion z-test or a Bayesian sequential test.

**Step 16: Monitor for data drift post-launch**
Once live, the model's input distribution will shift (new fare classes, seasonal patterns, UI changes). Set up:
- **Feature drift monitoring** (PSI — Population Stability Index per feature)
- **Prediction drift** (score distribution shift over time)
- **Outcome feedback loop** — pipe confirmed booking events back to retrain the model on a rolling window

---

### How This Replaces the Current MVP's Heuristics

| MVP Today | Production ML System |
|---|---|
| `idle_60s weight = 0.35` (manual) | SHAP value from trained model on real data |
| Thresholds 0.45 / 0.65 / 0.80 (arbitrary) | Calibrated from offline backtest + A/B validated |
| Same intervention for all users | Personalized score per session with context |
| No feedback loop | Continuous retraining on labeled outcomes |

---

This pipeline — **label definition → feature engineering → time-split training → calibration → backtest → A/B test → drift monitoring** — is the standard production loop for any behavioral prediction system and maps directly to the assumption documented in your README.

---

## How Feature Weights Are Calculated

---

### The Core Idea

A model learns weights by finding values that **minimize prediction error** on your training data. The "weight" concept differs by model type:

---

### Logistic Regression — Weights as Coefficients

Logistic regression directly outputs a coefficient $w_i$ per feature:

$$P(\text{abandon}) = \sigma\left(\sum_{i} w_i \cdot x_i + b\right) = \frac{1}{1 + e^{-(\sum w_i x_i + b)}}$$

Training minimizes **log-loss** (binary cross-entropy):

$$\mathcal{L} = -\frac{1}{N}\sum_{j=1}^{N} \left[ y_j \log \hat{p}_j + (1 - y_j) \log(1 - \hat{p}_j) \right]$$

Gradient descent iteratively nudges each $w_i$ in the direction that reduces this loss. After convergence, $w_i$ tells you the **log-odds contribution** of feature $i$ — directly interpretable as a weight.

**Example output after training:**

| Feature | Learned Coefficient $w_i$ |
|---|---|
| `idle_60s` | +1.82 |
| `back_button` | +1.41 |
| `price_hover × payment_step` | +2.10 |
| `form_delete` | +0.74 |
| `session_duration` | -0.31 (longer = less likely to abandon) |

These replace your manual `0.35`, `0.25` guesses with data-derived values.

---

### Gradient Boosted Trees (LightGBM/XGBoost) — Split-Based Importance

Trees don't have explicit coefficients. Instead, importance is measured by **how much a feature reduces prediction error when used to split the data**:

$$\text{Gain}(f) = \sum_{\text{splits using } f} \Delta\text{Impurity}$$

Each time a tree uses `idle_60s` to split a node, it measures how much that split reduced the Gini impurity or MSE. Summed across all trees = that feature's importance score.

The problem: this raw gain importance is **biased** — high-cardinality features (like `session_duration`, a continuous number) get more split opportunities than binary flags like `back_button`, so they appear more important even if they aren't.

---

### SHAP Values — The Correct Way to Measure Importance

SHAP (SHapley Additive exPlanations) fixes the bias problem. For each prediction, it answers: *"how much did each feature push the score up or down from the baseline?"*

$$\hat{p} = \underbrace{\bar{p}}_{\text{baseline}} + \underbrace{\phi_{\text{idle\_60s}}}_{\text{contribution}} + \underbrace{\phi_{\text{back\_button}}}_{\text{contribution}} + \cdots$$

Where $\phi_i$ is the SHAP value for feature $i$ in that session. To get a **global weight**, you average the absolute SHAP values across all sessions:

$$\text{Importance}(f) = \frac{1}{N} \sum_{j=1}^{N} |\phi_f^{(j)}|}$$

**Concrete example:** For a session where the user hovered on price for 8 seconds AND is on the payment step:

```
Baseline P(abandon) = 0.31

+ idle_60s fired        → +0.18
+ price_hover           → +0.09
+ on payment step       → +0.07
+ back_button pressed   → +0.14
- long session duration → -0.04

Final score = 0.75 → triggers "urgent save" intervention
```

This is far more meaningful than a static weight table — the contribution of `price_hover` changes depending on what step the user is on.

---

### Why This Matters for the MVP's Thresholds Too

The thresholds (0.45, 0.65, 0.80) in the current system are also guesses. Once you have a calibrated model:

1. Plot **Precision vs. Recall** at every possible threshold
2. Pick the threshold where the **expected revenue recovered minus cost of false-positive interventions is maximized**
3. Validate that threshold via A/B test

So the weights AND the thresholds both become outputs of the data, not inputs from intuition.

---

**One-line summary:** The model runs an optimization loop over thousands of historical sessions, adjusting weights until predictions match real outcomes. SHAP then decomposes each prediction back into per-feature contributions so you can see exactly what the model learned — and audit whether it makes business sense.