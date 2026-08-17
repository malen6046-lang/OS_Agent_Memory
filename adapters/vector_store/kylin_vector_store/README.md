# Kylin vector-store adapter

This adapter implements the frozen `VectorStoreAdapter` protocol.  The vendor
client exposes C++ classes, so `native/` builds a narrow C ABI bridge and Python
loads the bridge through `ctypes`.

Dynamic implementation path:

```yaml
vector_store:
  provider: kylin
  implementation: adapters.vector_store.kylin_vector_store:KylinVectorStoreAdapter
  collection_name: os_agent_memory
  expected_dimension: 768
  metric: cosine
```

Without changing the project-owned YAML, configure the existing environment
override mechanism:

```bash
export OS_AGENT_VECTOR_STORE__IMPLEMENTATION=adapters.vector_store.kylin_vector_store:KylinVectorStoreAdapter
export OS_AGENT_VECTOR_STORE__COLLECTION_NAME=os_agent_memory
export OS_AGENT_VECTOR_STORE__EXPECTED_DIMENSION=768
export OS_AGENT_VECTOR_STORE__METRIC=cosine
```

Build on Kylin and configure the runtime:

```bash
bash adapters/vector_store/kylin_vector_store/native/build.sh
export OS_AGENT_KYLIN_VECTOR_BRIDGE="$PWD/adapters/vector_store/kylin_vector_store/native/build/libosam_kylin_vector_bridge.so"
export OS_AGENT_KYLIN_VECTOR_DB="$PWD/data/vector.db"
```

Optional settings are `OS_AGENT_KYLIN_VECTOR_APP_ID`,
`OS_AGENT_KYLIN_VECTOR_ENCRYPT`, and `OS_AGENT_KYLIN_VECTOR_KEY`.  Never put an
encryption key in Git, YAML, logs, or screenshots.

The bridge validates existing schema/dimension/index settings.  It never drops
an incompatible collection automatically.
