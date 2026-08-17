# Kylin vector bridge

The vendor vector client exposes a C++ ABI, so Python calls this small C ABI
bridge through `ctypes`.  The bridge owns every `VectorDB` object and returns
only JSON/scalars; vendor types never cross into the frozen Python contracts.

On the Kylin target:

```bash
pkg-config --modversion kysdk-vector-engine-client
# Ensure the nlohmann-json CMake package is installed as well.
bash adapters/vector_store/kylin_vector_store/native/build.sh
export OS_AGENT_KYLIN_VECTOR_BRIDGE="$PWD/adapters/vector_store/kylin_vector_store/native/build/libosam_kylin_vector_bridge.so"
```

The bridge validates an existing collection and refuses to drop or silently
recreate an incompatible one.
