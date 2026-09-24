# L200-02 — `-ai` Bundle: Model Serving Endpoint

**Classification:** Level 200 — Per-Component Detailed Design
**Bundle:** `mlops-workshop-ai`
**Scope:** Model Serving endpoint with AI Gateway inference table logging, champion/challenger traffic splitting
**Cross-cutting patterns:** See L100 §3

---

## 1. Overview

The `-ai` bundle deploys the Model Serving endpoint. It is a separate bundle because the endpoint requires at least one model version to exist in the UC registered model — which only happens after the `-infra` bundle's training job runs.

**Deployment command:**
```bash
cd mlops-workshop-ai
databricks bundle deploy -t dev
```

---

## 2. Dependencies

| Depends On | Provided By | Contract |
|------------|-------------|----------|
| Registered model with ≥1 version | `-infra` training job | `${var.registered_model_name}` matches `-infra` output |
| Catalog + schema | `-infra` schema resource | `${var.catalog}` + `${var.user_schema}` must match |

---

## 3. Bundle Resources

### 3.1 Model Serving Endpoint

```yaml
resources:
  model_serving_endpoints:
    churn_serving:
      name: "churn-serving-${var.user_schema}"
      config:
        served_entities:
          - entity_name: ${var.registered_model_name}
            entity_version: "1"
            workload_size: "Small"
            scale_to_zero_enabled: true
      ai_gateway:
        inference_table_config:
          catalog_name: ${var.catalog}
          schema_name: ${var.user_schema}
          table_name_prefix: "churn_serving"
          enabled: true
```

### 3.2 Cross-Bundle Reference Pattern

The registered model lives in the `-infra` bundle. Cross-bundle `${resources...}` references aren't supported, so the `-ai` bundle uses variables:

```yaml
variables:
  registered_model_name:
    description: "Full 3-level name of the registered model from -infra"
    # Value: mlops_workshop.user_${bundle.user_name}.churn_model
```

In CI/CD, this variable is wired automatically from the `-infra` bundle's output.

---

## 4. AI Gateway Configuration

### 4.1 Inference Table

When the endpoint receives its first request, Databricks auto-creates:
- **Table:** `${catalog}.${schema}.churn_serving_payload`
- **Schema:** `request` (JSON STRING), `response` (JSON STRING), `timestamp_ms`, `status_code`, `request_metadata`, `sampling_fraction`
- **Purpose:** Monitored by `serving_monitor` in the `-monitors` bundle

### 4.2 Champion/Challenger Traffic Splitting

For A/B testing after multiple model versions exist:

```yaml
config:
  served_entities:
    - entity_name: ${var.registered_model_name}
      entity_version: "3"    # Champion
      workload_size: "Small"
      scale_to_zero_enabled: true
    - entity_name: ${var.registered_model_name}
      entity_version: "4"    # Challenger
      workload_size: "Small"
      scale_to_zero_enabled: true
  traffic_config:
    routes:
      - served_model_name: "churn_model-3"
        traffic_percentage: 90
      - served_model_name: "churn_model-4"
        traffic_percentage: 10
```

---

## 5. Feature Lookup at Serving Time

When a model is logged with `fe.log_model(training_set=...)`, the model retains feature lineage. Model Serving automatically looks up features from the online store at inference time — no manual feature retrieval code in the serving path.

**Request payload (caller sends only the entity key):**
```json
{"dataframe_records": [{"customer_id": "CUST-00042"}]}
```

**What happens internally:**
1. Endpoint receives `customer_id`
2. Feature Store looks up all features for that customer from the online store
3. Model receives the full feature vector
4. Prediction returned to caller

---

## 6. Non-Functional Requirements

| NFR | Target |
|-----|--------|
| Deploy time | < 5 minutes (endpoint provisioning) |
| Scale-to-zero | Enabled (workshop cost control) |
| Latency | < 500ms P95 (Small workload) |
| Inference logging | Every request logged to UC table |

---

## 7. Testing

| Test | What | How |
|------|------|-----|
| Endpoint health | Endpoint is READY | `GET /serving-endpoints/{name}` |
| Prediction | Returns valid response | `POST /serving-endpoints/{name}/invocations` |
| Inference table | Payload table created | `SELECT COUNT(*) FROM churn_serving_payload` after first request |
| Feature lookup | Features auto-resolved | Send request with only `customer_id`, verify full prediction |

---

*Document Level: L200 — Per-Component Detailed Design*
*Bundle: mlops-workshop-ai*
*References: L100 §3.1 (resource reference pattern), L100 §3.5 (champion/challenger)*
