# Evaluation Harness

DeepEval-based RAG evaluation framework. Measures answer faithfulness, answer relevancy, and contextual precision/recall against a curated golden dataset of Nuke documentation questions.

---

## Files

| File | Purpose |
|------|---------|
| `golden_dataset.yaml` | Ground-truth Q&A pairs with expected contexts |
| `dataset.py` | Loads and validates the golden dataset |
| `harness.py` | Runs DeepEval metrics against the live `/ask-agentic` endpoint |
| `run_eval.py` | Entry point — runs a full evaluation and writes results |
| `persistence.py` | Saves evaluation run results to PostgreSQL |
| `compare_runs.py` | Compares metric scores across two saved runs |

---

## Running an Evaluation

The API server must be running before executing an eval:

```bash
# Run a full evaluation against the golden dataset
uv run python -m api.evaluation.run_eval

# Compare two runs by run ID
uv run python -m api.evaluation.compare_runs --run-a <id_a> --run-b <id_b>
```

Results are written to the `eval_runs` table in PostgreSQL and printed to stdout.

---

## Metrics

| Metric | Library | Judge model |
|--------|---------|-------------|
| Answer Faithfulness | DeepEval | `gpt-4o-mini` |
| Answer Relevancy | DeepEval | `gpt-4o-mini` |
| Contextual Precision | DeepEval | `gpt-4o-mini` |
| Contextual Recall | DeepEval | `gpt-4o-mini` |

The judge model is intentionally separate from the production Ollama model. Set `EVAL__JUDGE_MODEL` in `.env` to use a different OpenAI model.

---

## Golden Dataset Format

`golden_dataset.yaml` entries follow this structure:

```yaml
- question: "How do I blur an image in Nuke?"
  expected_answer: "Use the Blur node..."
  expected_contexts:
    - "Blur node applies a convolution..."
```

Add new entries to expand coverage. The dataset is read at eval time; no rebuild step needed.

---

## Configuration

| Env var | Default | Description |
|---------|---------|-------------|
| `EVAL__JUDGE_MODEL` | `gpt-4o-mini` | OpenAI model used as LLM judge |
| `EVAL__GOLDEN_DATASET_PATH` | `api/evaluation/golden_dataset.yaml` | Path to golden dataset |
| `OPENAI_API_KEY` | — | Required for the judge model |
