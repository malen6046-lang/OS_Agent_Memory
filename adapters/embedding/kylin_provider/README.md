# Kylin embedding provider

This adapter implements the frozen `EmbeddingProvider` protocol through the
Kylin CoreAI embedding C API.  It selects the configured model by its exact SDK
model name, calls `text_embedding_init_model`, verifies the runtime dimension,
serializes access to the session, and destroys every `EmbeddingResult`.

Dynamic implementation path:

```yaml
embedding:
  provider: kylin
  model_name: ensemble-embd_gte-base_uint8-text
  implementation: adapters.embedding.kylin_provider:KylinEmbeddingProvider
```

Without changing the project-owned YAML, the same values can be supplied by
the existing environment override mechanism:

```bash
export OS_AGENT_ENV=kylin
export OS_AGENT_EMBEDDING__MODEL_NAME=ensemble-embd_gte-base_uint8-text
export OS_AGENT_EMBEDDING__IMPLEMENTATION=adapters.embedding.kylin_provider:KylinEmbeddingProvider
```

Optional library override:

```bash
export OS_AGENT_KYLIN_EMBEDDING_LIBRARY=/usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so
```

The provider performs one embedding warmup during application startup so the
first API request does not pay the model's lazy-initialization cost. It can be
disabled for diagnostics with `OS_AGENT_KYLIN_EMBEDDING_WARMUP=false`.

The system package and `kylin-ai-runtime` service must be installed and
available to the same desktop user that runs the Python process.
