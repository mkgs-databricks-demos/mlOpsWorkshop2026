# Instructor Delivery Guide -- MLOps Workshop

**Delivery model:** Solo instructor, serverless compute (latest environment, no ML Runtime), Git-comfortable audience
**Customer context:** Healthcare / Rx Rebates, pre-sales engagement
**Compute:** All serverless -- Feature Views, scikit-learn, XGBoost, and MLflow all install cleanly via %pip install

## Compute Requirements

**ML Runtime is NOT required.** Feature Views work on serverless compute directly -- you just need `%pip install databricks-feature-engineering>=0.16.0`. Scikit-learn, XGBoost, and MLflow install cleanly on serverless. The only thing that needs ML Runtime is GPU-based deep learning (not in scope). Run everything on **serverless compute, latest environment version**.

## Before They Arrive (30 min prep)

1. **Deploy your own `-infra` bundle** to the workshop catalog -- this is your golden path that you demo from if anyone gets stuck
2. **Run `data_ingestion`** on your schema so you have data ready for live queries
3. **Open 4 browser tabs:** Catalog Explorer, Jobs UI, your terminal (CLI), and the curriculum canvas
4. **Pre-stage the Rx Rebates framing** -- swap customer churn for PBM rebate leakage prediction in your verbal narrative (the code stays generic, the story is healthcare)

## The Rx Rebates Narrative Thread

Frame every module through Rx Rebates without changing the code:

| Workshop Concept | Rx Rebates Translation |
|---|---|
| Customer = `customer_id` | Drug manufacturer or PBM contract |
| Churn = `churned` | Rebate leakage (contract underperformance) |
| Usage events | Claim volume, formulary utilization, market share |
| Billing history | Rebate payments, invoice amounts, true-up adjustments |
| Support interactions | Dispute tickets, audit findings, contract amendments |
| Feature: `avg_daily_sessions_30d` | Average daily claim volume over 30 days |
| Feature: `total_revenue_90d` | Total rebate payments over 90 days |
| Champion model | Current rebate leakage predictor in production |
| Drift detection | Formulary changes, new generics, seasonal patterns |

**Key message to the room:** "The architecture is the same whether you are predicting churn, rebate leakage, or readmission risk. Today we are building the reusable pattern -- your data scientists plug in the domain."

## Module-by-Module Delivery

### Module 1 (09:00-09:45): Set the Stage

**Your move:** Talk, do not type. This is the only module where you are purely presenting.

- Open with the **Rx Rebates pain point**: "Your actuaries know which contracts are leaking margin, but they find out 90 days late from a spreadsheet. What if you knew in 15 days from a model that updates daily?"
- Walk through the **four pillars** (DevOps/DataOps/ModelOps/MLOps) -- frame each through healthcare
- Show the **failure modes** -- training-serving skew is especially resonant
- **Do not touch the CLI yet.** Build anticipation.

**Transition line:** "Everything I just described -- we are going to build it in the next 6 hours. Three bundles, deployed in sequence, fully governed. Let us start."

### Module 2 (09:45-10:30): Three Bundles + Data Ingestion

**Your move:** Live terminal. This is where you earn credibility.

1. Show `01_three_bundle_deployment.html` -- explain why three bundles
2. Deploy `-infra` live -- talk through the YAML while it deploys
3. Run `data_ingestion` -- show `02_data_ingestion_flow.html` while it runs
4. Switch to Catalog Explorer -- query a silver table
5. Participants do the same (10-15 min)

**Pacing:** You demo first (5 min), they do it (10 min), reconvene (5 min).

### Break (10:30-10:45)

Verify 2-3 participants have data. Debug stragglers.

### Module 3 (10:45-12:00): Feature Views

Three acts:
- **Act 1 (20 min):** Define features interactively, `fe.compute_features()`
- **Act 2 (20 min):** `create_training_set()` -- the point-in-time aha moment
- **Act 3 (20 min):** Register + materialize

### Lunch (12:00-13:00)

Spot-check features registered. Catch-up artifact: feature definitions notebook.

### Module 4 (13:00-14:00): Training + Champion/Challenger

1. Train in notebook -- `fe.log_model()` with lineage
2. Show `03_champion_challenger_flow.html`
3. Run training job -- watch task graph in Jobs UI
4. Verify aliases in Catalog Explorer

### Module 5 (14:00-15:00): CI/CD

1. Walk through GitHub Actions YAML
2. Demo a PR workflow
3. Show MLflow 3 deployment job (healthcare compliance resonance)
4. **Demo only -- no participant hands-on**

### Break (15:00-15:15)

### Module 6 (15:15-16:00): Deployment

1. Deploy `-ai` bundle -- explain AI Gateway inference table
2. Test endpoint -- show auto feature lookup
3. Show batch inference `@Champion` pattern
4. Participants deploy their own `-ai` bundles

### Module 7 (16:00-16:45): Monitoring + Dashboard

1. Deploy `-monitors` bundle
2. Show three monitors in Catalog Explorer
3. Walk through MLOps dashboard pages
4. Show retraining trigger -- `04_retraining_loop.html`
5. Participants deploy their own `-monitors` bundles

### Capstone (16:45-17:00)

Open `06_end_to_end_lifecycle.html`. Walk top to bottom. Close with the Rx Rebates hook.

## Sole-Instructor Survival Tips

| Situation | What To Do |
|-----------|-----------|
| Stuck on bundle deploy | Run `databricks bundle validate -t dev` first |
| Serverless takes too long | Talk through YAML/diagram -- never dead air |
| Feature Views fail | Check pip install + restartPython() |
| HIPAA/compliance question | UC governs access, AI Gateway logs calls, MLflow traces decisions |
| Running behind | Cut Module 5 to demo-only, Module 7 to dashboard walkthrough |
| Can we use this for X? | Always yes -- map their use case to workshop components |

## Diagram Usage Map

### Platform Architecture Diagrams

| When | Which Diagram | Purpose |
|------|--------------|---------|
| Module 2 opening | `01_three_bundle_deployment.html` | Three-bundle sequence |
| Module 2 data ingestion | `02_data_ingestion_flow.html` | Dual-path gate |
| Module 4 promotion | `03_champion_challenger_flow.html` | Alias lifecycle |
| Module 7 retraining | `04_retraining_loop.html` | Closed loop |
| Module 5 CI/CD | `05_bundle_resource_dependencies.html` | 14 resources |
| Capstone | `06_end_to_end_lifecycle.html` | Full lifecycle |

### Rx Rebates Domain Diagrams

| When | Which Diagram | Purpose |
|------|--------------|---------|
| Module 1 opening | `07_rx_rebate_lifecycle.html` | Full rebate lifecycle + where MLOps plugs in |
| Module 1 after lifecycle | `10_rx_money_vs_data_flow.html` | Money vs data -- we build on data side |
| Module 2 before hands-on | `08_domain_mapping.html` | Generic to Rx translation table |
| Module 3 feature intro | `09_rx_feature_engineering.html` | Rx-specific features |
| Capstone close | `07_rx_rebate_lifecycle.html` again | You built the bottom section |

### Recommended Module 1 Sequence

1. `07_rx_rebate_lifecycle.html` -- "This is the world you live in"
2. `10_rx_money_vs_data_flow.html` -- "Money vs data -- we build on the data side"
3. `08_domain_mapping.html` -- "Here is the translation table for today"
4. Transition to Module 2 and platform diagrams
