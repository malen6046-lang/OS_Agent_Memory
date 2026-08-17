#include <kysdk-vector-engine-client/Database.h>
#include <kysdk-vector-engine-client/types/CollectionDesc.h>
#include <kysdk-vector-engine-client/types/CollectionSchema.h>
#include <kysdk-vector-engine-client/types/Constants.h>
#include <kysdk-vector-engine-client/types/DmlResults.h>
#include <kysdk-vector-engine-client/types/FieldData.h>
#include <kysdk-vector-engine-client/types/FieldSchema.h>
#include <kysdk-vector-engine-client/types/IndexDesc.h>
#include <kysdk-vector-engine-client/types/SearchArguments.h>
#include <kysdk-vector-engine-client/types/SearchResults.h>

#include <nlohmann/json.hpp>

#include <algorithm>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <exception>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace {

constexpr const char* kPrimaryKey = "vector_pk";
constexpr const char* kMemoryId = "memory_id";
constexpr const char* kUserId = "user_id";
constexpr const char* kStatus = "status";
constexpr const char* kMetadata = "metadata";
constexpr const char* kVector = "dense_vector";
constexpr const char* kIndexName = "dense_vector_flat";

struct BridgeHandle {
    std::shared_ptr<VectorDB::Database> database;
};

char* duplicate(const std::string& value) {
    auto* copy = static_cast<char*>(std::malloc(value.size() + 1));
    if (copy == nullptr) {
        return nullptr;
    }
    std::memcpy(copy, value.c_str(), value.size() + 1);
    return copy;
}

void set_output(char** target, const std::string& value) {
    if (target != nullptr) {
        *target = duplicate(value);
    }
}

int fail(char** error, int code, const std::string& message) {
    set_output(error, message);
    return code == 0 ? 1 : code;
}

int status_code(const VectorDB::Status& status) {
    return static_cast<int>(status.Code());
}

int check_status(
    const char* operation,
    const VectorDB::Status& status,
    char** error
) {
    if (status.IsOk()) {
        return 0;
    }
    std::ostringstream message;
    message << operation << " failed (SDK code " << status_code(status)
            << "): " << status.Message();
    return fail(error, status_code(status), message.str());
}

VectorDB::MetricType metric_from(const std::string& value) {
    if (value == "cosine") {
        return VectorDB::MetricType::COSINE;
    }
    if (value == "inner_product") {
        return VectorDB::MetricType::IP;
    }
    if (value == "l2") {
        return VectorDB::MetricType::L2;
    }
    throw std::invalid_argument("unsupported metric: " + value);
}

std::string quote_expression(const char* value) {
    std::string escaped;
    for (const char* current = value; *current != '\0'; ++current) {
        if (*current == '\\' || *current == '"') {
            escaped.push_back('\\');
        }
        escaped.push_back(*current);
    }
    return "\"" + escaped + "\"";
}

const VectorDB::FieldSchema* find_field(
    const VectorDB::CollectionSchema& schema,
    const std::string& name
) {
    const auto& fields = schema.Fields();
    const auto found = std::find_if(
        fields.begin(), fields.end(),
        [&name](const VectorDB::FieldSchema& field) {
            return field.Name() == name;
        }
    );
    return found == fields.end() ? nullptr : &*found;
}

void validate_existing_collection(
    VectorDB::Database& database,
    const std::string& collection,
    int dimension,
    VectorDB::MetricType metric
) {
    VectorDB::CollectionDesc description;
    auto status = database.DescribeCollection(collection, description);
    if (!status.IsOk()) {
        throw std::runtime_error(
            "DescribeCollection failed: " + status.Message()
        );
    }
    const auto& schema = description.Schema();
    const auto* primary_key = find_field(schema, kPrimaryKey);
    const auto* vector = find_field(schema, kVector);
    const auto* memory_id = find_field(schema, kMemoryId);
    const auto* user_id = find_field(schema, kUserId);
    const auto* memory_status = find_field(schema, kStatus);
    const auto* metadata = find_field(schema, kMetadata);
    if (primary_key == nullptr || !primary_key->IsPrimaryKey() ||
        primary_key->AutoID() ||
        primary_key->FieldDataType() != VectorDB::DataType::INT64 ||
        vector == nullptr ||
        vector->FieldDataType() != VectorDB::DataType::FLOAT_VECTOR ||
        static_cast<int>(vector->Dimension()) != dimension ||
        memory_id == nullptr || user_id == nullptr || memory_status == nullptr ||
        metadata == nullptr) {
        throw std::runtime_error(
            "existing collection schema is incompatible; refusing to drop or recreate it"
        );
    }
    VectorDB::IndexDesc index;
    status = database.DescribeIndex(collection, kVector, index);
    if (!status.IsOk()) {
        throw std::runtime_error("DescribeIndex failed: " + status.Message());
    }
    if (index.IndexType() != VectorDB::IndexType::FLAT ||
        index.MetricType() != metric) {
        throw std::runtime_error(
            "existing dense_vector index is not FLAT with the configured metric"
        );
    }
}

void add_schema_field(
    VectorDB::CollectionSchema& schema,
    VectorDB::FieldSchema field
) {
    const auto name = field.Name();
    if (!schema.AddField(std::move(field))) {
        throw std::runtime_error("failed to add schema field: " + name);
    }
}

void require_argument_status(
    const char* operation,
    const VectorDB::Status& status
) {
    if (!status.IsOk()) {
        throw std::runtime_error(
            std::string(operation) + " failed: " + status.Message()
        );
    }
}

template <typename T>
std::shared_ptr<T> output_field(
    const VectorDB::SingleResult& result,
    const std::string& name
) {
    auto raw = result.OutputField(name);
    auto typed = std::dynamic_pointer_cast<T>(raw);
    if (!typed) {
        throw std::runtime_error("missing or invalid search output field: " + name);
    }
    return typed;
}

template <typename Function>
int guard(char** error, Function&& function) {
    try {
        return function();
    } catch (const std::exception& exception) {
        return fail(error, 1, exception.what());
    } catch (...) {
        return fail(error, 1, "unknown C++ exception");
    }
}

}  // namespace

extern "C" {

__attribute__((visibility("default"))) void* osam_kve_open(
    const char* app_id,
    const char* db_file,
    int encrypt,
    const char* key,
    std::uint32_t connect_timeout_ms,
    char** error
) {
    try {
        if (app_id == nullptr || app_id[0] == '\0' || db_file == nullptr ||
            db_file[0] == '\0') {
            set_output(error, "app_id and db_file are required");
            return nullptr;
        }
        auto handle = std::make_unique<BridgeHandle>();
        handle->database = VectorDB::Database::Create();
        if (!handle->database) {
            set_output(error, "VectorDB::Database::Create returned null");
            return nullptr;
        }
        VectorDB::ConnectParam params(app_id);
        params.SetConnectTimeout(connect_timeout_ms);
        auto status = handle->database->Connect(params);
        if (!status.IsOk()) {
            set_output(error, "Connect failed: " + status.Message());
            return nullptr;
        }
        status = handle->database->LoadDBFile(
            db_file, encrypt != 0, key == nullptr ? "" : key
        );
        if (!status.IsOk()) {
            handle->database->Disconnect();
            set_output(error, "LoadDBFile failed: " + status.Message());
            return nullptr;
        }
        return handle.release();
    } catch (const std::exception& exception) {
        set_output(error, exception.what());
        return nullptr;
    } catch (...) {
        set_output(error, "unknown C++ exception");
        return nullptr;
    }
}

__attribute__((visibility("default"))) void osam_kve_close(void* opaque) {
    auto* handle = static_cast<BridgeHandle*>(opaque);
    if (handle == nullptr) {
        return;
    }
    if (handle->database) {
        handle->database->Disconnect();
    }
    delete handle;
}

__attribute__((visibility("default"))) int osam_kve_ensure_collection(
    void* opaque,
    const char* collection_name,
    int dimension,
    const char* metric_name,
    char** error
) {
    return guard(error, [&]() {
        auto* handle = static_cast<BridgeHandle*>(opaque);
        if (handle == nullptr || !handle->database || collection_name == nullptr ||
            metric_name == nullptr || dimension <= 0) {
            return fail(error, 1, "invalid ensure_collection arguments");
        }
        const auto metric = metric_from(metric_name);
        bool exists = false;
        auto status = handle->database->HasCollection(collection_name, exists);
        if (auto code = check_status("HasCollection", status, error); code != 0) {
            return code;
        }
        if (exists) {
            validate_existing_collection(
                *handle->database, collection_name, dimension, metric
            );
            return 0;
        }

        VectorDB::CollectionSchema schema(collection_name);
        add_schema_field(schema, VectorDB::FieldSchema(
            kPrimaryKey, VectorDB::DataType::INT64, "stable vector primary key", true, false
        ));
        add_schema_field(schema,
            VectorDB::FieldSchema(kMemoryId, VectorDB::DataType::VARCHAR)
                .WithMaxLength(64)
        );
        add_schema_field(schema,
            VectorDB::FieldSchema(kUserId, VectorDB::DataType::VARCHAR)
                .WithMaxLength(256)
        );
        add_schema_field(schema,
            VectorDB::FieldSchema(kStatus, VectorDB::DataType::VARCHAR)
                .WithMaxLength(24)
        );
        add_schema_field(
            schema, VectorDB::FieldSchema(kMetadata, VectorDB::DataType::JSON)
        );
        add_schema_field(schema,
            VectorDB::FieldSchema(kVector, VectorDB::DataType::FLOAT_VECTOR)
                .WithDimension(static_cast<std::uint32_t>(dimension))
        );
        VectorDB::IndexDesc index(
            kVector, kIndexName, VectorDB::IndexType::FLAT, metric
        );
        status = handle->database->CreateCollection(schema, index);
        return check_status("CreateCollection", status, error);
    });
}

__attribute__((visibility("default"))) int osam_kve_upsert(
    void* opaque,
    const char* collection_name,
    std::size_t count,
    const std::int64_t* vector_pks,
    const char* const* memory_ids,
    const char* const* user_ids,
    const char* const* statuses,
    const char* const* metadata_json,
    const float* vectors,
    int dimension,
    char** error
) {
    return guard(error, [&]() {
        auto* handle = static_cast<BridgeHandle*>(opaque);
        if (handle == nullptr || !handle->database || collection_name == nullptr ||
            count == 0 || vector_pks == nullptr || memory_ids == nullptr ||
            user_ids == nullptr || statuses == nullptr || metadata_json == nullptr ||
            vectors == nullptr || dimension <= 0) {
            return fail(error, 1, "invalid upsert arguments");
        }
        std::vector<std::int64_t> pks(vector_pks, vector_pks + count);
        std::vector<std::string> memories;
        std::vector<std::string> users;
        std::vector<std::string> memory_statuses;
        std::vector<nlohmann::json> metadata;
        std::vector<std::vector<float>> dense_vectors;
        memories.reserve(count);
        users.reserve(count);
        memory_statuses.reserve(count);
        metadata.reserve(count);
        dense_vectors.reserve(count);
        for (std::size_t index = 0; index < count; ++index) {
            memories.emplace_back(memory_ids[index]);
            users.emplace_back(user_ids[index]);
            memory_statuses.emplace_back(statuses[index]);
            metadata.push_back(nlohmann::json::parse(metadata_json[index]));
            const auto* first = vectors + index * static_cast<std::size_t>(dimension);
            dense_vectors.emplace_back(first, first + dimension);
        }
        std::vector<VectorDB::FieldDataPtr> fields{
            std::make_shared<VectorDB::Int64FieldData>(kPrimaryKey, std::move(pks)),
            std::make_shared<VectorDB::VarCharFieldData>(kMemoryId, std::move(memories)),
            std::make_shared<VectorDB::VarCharFieldData>(kUserId, std::move(users)),
            std::make_shared<VectorDB::VarCharFieldData>(kStatus, std::move(memory_statuses)),
            std::make_shared<VectorDB::JsonFieldData>(kMetadata, std::move(metadata)),
            std::make_shared<VectorDB::FloatVecFieldData>(kVector, std::move(dense_vectors)),
        };
        VectorDB::DmlResults results;
        const auto status = handle->database->Upsert(
            collection_name, fields, results
        );
        if (auto code = check_status("Upsert", status, error); code != 0) {
            return code;
        }
        if (results.IdArray().IntIDArray().size() != count) {
            return fail(error, 1, "Upsert returned an unexpected ID count");
        }
        return 0;
    });
}

__attribute__((visibility("default"))) int osam_kve_query(
    void* opaque,
    const char* collection_name,
    const char* user_id,
    const char* memory_status,
    const float* vector,
    int dimension,
    int top_k,
    int timeout_ms,
    const char* metric_name,
    char** output_json,
    char** error
) {
    return guard(error, [&]() {
        auto* handle = static_cast<BridgeHandle*>(opaque);
        if (handle == nullptr || !handle->database || collection_name == nullptr ||
            user_id == nullptr || memory_status == nullptr || vector == nullptr ||
            dimension <= 0 || top_k <= 0 || metric_name == nullptr) {
            return fail(error, 1, "invalid query arguments");
        }
        VectorDB::SearchArguments arguments(
            collection_name, top_k, metric_from(metric_name)
        );
        require_argument_status(
            "AddOutputField(memory_id)", arguments.AddOutputField(kMemoryId)
        );
        require_argument_status(
            "AddOutputField(user_id)", arguments.AddOutputField(kUserId)
        );
        require_argument_status(
            "AddOutputField(status)", arguments.AddOutputField(kStatus)
        );
        require_argument_status(
            "AddOutputField(metadata)", arguments.AddOutputField(kMetadata)
        );
        require_argument_status("SetExpression", arguments.SetExpression(
            std::string(kUserId) + " == " + quote_expression(user_id) +
            " && " + kStatus + " == " + quote_expression(memory_status)
        ));
        require_argument_status("AddTargetVector", arguments.AddTargetVector(
            kVector, std::vector<float>(vector, vector + dimension)
        ));
        VectorDB::SearchResults results;
        const auto status = handle->database->Search(
            arguments, results, timeout_ms
        );
        if (auto code = check_status("Search", status, error); code != 0) {
            return code;
        }
        nlohmann::json output = nlohmann::json::array();
        if (!results.Results().empty()) {
            const auto& result = results.Results().front();
            const auto& ids = result.Ids().IntIDArray();
            const auto& scores = result.Scores();
            const auto memories = output_field<VectorDB::VarCharFieldData>(result, kMemoryId);
            const auto users = output_field<VectorDB::VarCharFieldData>(result, kUserId);
            const auto statuses = output_field<VectorDB::VarCharFieldData>(result, kStatus);
            const auto metadata = output_field<VectorDB::JsonFieldData>(result, kMetadata);
            const bool l2_metric = std::string(metric_name) == "l2";
            const std::size_t count = std::min(
                {ids.size(), scores.size(), memories->Data().size(),
                 users->Data().size(), statuses->Data().size(), metadata->Data().size()}
            );
            for (std::size_t index = 0; index < count; ++index) {
                output.push_back({
                    {"vector_pk", ids[index]},
                    {"memory_id", memories->Data()[index]},
                    {"user_id", users->Data()[index]},
                    {"status", statuses->Data()[index]},
                    {"score", l2_metric ? 1.0F / (1.0F + std::max(0.0F, scores[index])) : scores[index]},
                    {"metadata", metadata->Data()[index]},
                });
            }
        }
        set_output(output_json, output.dump());
        return 0;
    });
}

__attribute__((visibility("default"))) int osam_kve_delete(
    void* opaque,
    const char* collection_name,
    const std::int64_t* vector_pks,
    std::size_t count,
    char** output_json,
    char** error
) {
    return guard(error, [&]() {
        auto* handle = static_cast<BridgeHandle*>(opaque);
        if (handle == nullptr || !handle->database || collection_name == nullptr ||
            vector_pks == nullptr || count == 0) {
            return fail(error, 1, "invalid delete arguments");
        }
        std::ostringstream expression;
        expression << kPrimaryKey << " in [";
        for (std::size_t index = 0; index < count; ++index) {
            if (index != 0) {
                expression << ',';
            }
            expression << vector_pks[index];
        }
        expression << ']';
        VectorDB::DmlResults results;
        const auto status = handle->database->Delete(
            collection_name, expression.str(), results
        );
        if (auto code = check_status("Delete", status, error); code != 0) {
            return code;
        }
        set_output(output_json, nlohmann::json(results.IdArray().IntIDArray()).dump());
        return 0;
    });
}

__attribute__((visibility("default"))) void osam_kve_free(char* value) {
    std::free(value);
}

}  // extern "C"
