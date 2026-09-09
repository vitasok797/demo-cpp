#include <fastcdr/Cdr.h>
#include <fastcdr/exceptions/Exception.h>
#include <fastcdr/FastBuffer.h>
#include <fastdds/dds/core/policy/QosPolicies.hpp>
#include <fastdds/dds/core/status/PublicationMatchedStatus.hpp>
#include <fastdds/dds/domain/DomainParticipant.hpp>
#include <fastdds/dds/domain/DomainParticipantFactory.hpp>
#include <fastdds/dds/publisher/DataWriter.hpp>
#include <fastdds/dds/publisher/Publisher.hpp>
#include <fastdds/dds/publisher/qos/DataWriterQos.hpp>
#include <fastdds/dds/subscriber/DataReader.hpp>
#include <fastdds/dds/subscriber/qos/DataReaderQos.hpp>
#include <fastdds/dds/subscriber/SampleInfo.hpp>
#include <fastdds/dds/subscriber/Subscriber.hpp>
#include <fastdds/dds/topic/Topic.hpp>
#include <fastdds/dds/topic/TopicDataType.hpp>
#include <fastdds/dds/topic/TypeSupport.hpp>
#include <fastdds/rtps/common/SerializedPayload.hpp>

#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <thread>

namespace fastdds = eprosima::fastdds::dds;
namespace rtps = eprosima::fastdds::rtps;

namespace
{

struct NumberSample
{
    uint32_t value{};
};

class NumberType final : public fastdds::TopicDataType
{
  public:
    NumberType()
    {
        set_name("NumberSample");
        max_serialized_type_size = 8U;
    }

    auto serialize(const void* data,
                   rtps::SerializedPayload_t& payload,
                   fastdds::DataRepresentationId_t data_representation) -> bool override
    {
        static_cast<void>(data_representation);
        const auto* sample = static_cast<const NumberSample*>(data);
        auto buffer = eprosima::fastcdr::FastBuffer{reinterpret_cast<char*>(payload.data), payload.max_size};
        auto serializer = eprosima::fastcdr::Cdr{buffer, eprosima::fastcdr::Cdr::LITTLE_ENDIANNESS,
                                                 eprosima::fastcdr::CdrVersion::DDS_CDR};

        try
        {
            payload.encapsulation = CDR_LE;
            serializer.serialize_encapsulation();
            serializer << sample->value;
            payload.length = static_cast<uint32_t>(serializer.get_serialized_data_length());
            return true;
        }
        catch (const eprosima::fastcdr::exception::Exception& exception)
        {
            std::cerr << "Serialization failed: " << exception.what() << '\n';
            return false;
        }
    }

    auto deserialize(rtps::SerializedPayload_t& payload, void* data) -> bool override
    {
        auto* sample = static_cast<NumberSample*>(data);
        auto buffer = eprosima::fastcdr::FastBuffer{reinterpret_cast<char*>(payload.data), payload.length};
        auto deserializer = eprosima::fastcdr::Cdr{buffer, eprosima::fastcdr::Cdr::LITTLE_ENDIANNESS,
                                                   eprosima::fastcdr::CdrVersion::DDS_CDR};

        try
        {
            deserializer.read_encapsulation();
            deserializer >> sample->value;
            return true;
        }
        catch (const eprosima::fastcdr::exception::Exception& exception)
        {
            std::cerr << "Deserialization failed: " << exception.what() << '\n';
            return false;
        }
    }

    auto calculate_serialized_size(const void* data, fastdds::DataRepresentationId_t data_representation)
        -> uint32_t override
    {
        static_cast<void>(data);
        static_cast<void>(data_representation);
        return 8U;
    }

    auto create_data() -> void* override
    {
        return new NumberSample{};
    }

    auto delete_data(void* data) -> void override
    {
        delete static_cast<NumberSample*>(data);
    }

    auto compute_key(rtps::SerializedPayload_t& payload, rtps::InstanceHandle_t& instance_handle, bool force_md5)
        -> bool override
    {
        static_cast<void>(payload);
        static_cast<void>(instance_handle);
        static_cast<void>(force_md5);
        return false;
    }

    auto compute_key(const void* data, rtps::InstanceHandle_t& instance_handle, bool force_md5) -> bool override
    {
        static_cast<void>(data);
        static_cast<void>(instance_handle);
        static_cast<void>(force_md5);
        return false;
    }

    [[nodiscard]]
    auto is_bounded() const -> bool override
    {
        return true;
    }
};

auto report_failure(const char* operation) -> void
{
    std::cerr << operation << " failed.\n";
}

[[nodiscard]]
auto is_ok(fastdds::ReturnCode_t result) -> bool
{
    return result == fastdds::RETCODE_OK;
}

[[nodiscard]]
auto run_demo(fastdds::DomainParticipant* participant) -> int
{
    constexpr auto expected_value = uint32_t{42};
    constexpr auto poll_interval = std::chrono::milliseconds{10};
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds{5};

    const auto type_support = fastdds::TypeSupport{new NumberType{}};
    if (!is_ok(type_support.register_type(participant))) [[unlikely]]
    {
        report_failure("Registering the topic type");
        return EXIT_FAILURE;
    }

    auto* topic = participant->create_topic("NumberTopic", type_support.get_type_name(), fastdds::TOPIC_QOS_DEFAULT);
    auto* publisher = participant->create_publisher(fastdds::PUBLISHER_QOS_DEFAULT);
    auto* subscriber = participant->create_subscriber(fastdds::SUBSCRIBER_QOS_DEFAULT);
    if (topic == nullptr || publisher == nullptr || subscriber == nullptr) [[unlikely]]
    {
        report_failure("Creating the DDS entities");
        return EXIT_FAILURE;
    }

    auto writer_qos = fastdds::DATAWRITER_QOS_DEFAULT;
    writer_qos.representation().m_value = {fastdds::XCDR_DATA_REPRESENTATION};

    auto reader_qos = fastdds::DATAREADER_QOS_DEFAULT;
    reader_qos.representation().m_value = {fastdds::XCDR_DATA_REPRESENTATION};

    auto* writer = publisher->create_datawriter(topic, writer_qos);
    auto* reader = subscriber->create_datareader(topic, reader_qos);
    if (writer == nullptr || reader == nullptr) [[unlikely]]
    {
        report_failure("Creating the DDS endpoints");
        return EXIT_FAILURE;
    }

    while (std::chrono::steady_clock::now() < deadline)
    {
        auto status = fastdds::PublicationMatchedStatus{};
        if (!is_ok(writer->get_publication_matched_status(status))) [[unlikely]]
        {
            report_failure("Getting the publication match status");
            return EXIT_FAILURE;
        }

        if (status.current_count > 0)
        {
            break;
        }

        std::this_thread::sleep_for(poll_interval);
    }

    auto status = fastdds::PublicationMatchedStatus{};
    if (!is_ok(writer->get_publication_matched_status(status)) || status.current_count <= 0) [[unlikely]]
    {
        report_failure("Waiting for a reader match");
        return EXIT_FAILURE;
    }

    const auto sent = NumberSample{expected_value};
    if (!is_ok(writer->write(&sent))) [[unlikely]]
    {
        report_failure("Writing the sample");
        return EXIT_FAILURE;
    }

    while (std::chrono::steady_clock::now() < deadline)
    {
        auto received = NumberSample{};
        auto sample_info = fastdds::SampleInfo{};
        const auto result = reader->take_next_sample(&received, &sample_info);
        if (result == fastdds::RETCODE_NO_DATA)
        {
            std::this_thread::sleep_for(poll_interval);
            continue;
        }

        if (!is_ok(result)) [[unlikely]]
        {
            report_failure("Taking the sample");
            return EXIT_FAILURE;
        }

        if (!sample_info.valid_data || received.value != expected_value) [[unlikely]]
        {
            report_failure("Validating the received sample");
            return EXIT_FAILURE;
        }

        std::cout << "Received: " << received.value << '\n';
        return EXIT_SUCCESS;
    }

    report_failure("Waiting for the expected sample");
    return EXIT_FAILURE;
}

}  // namespace

auto main() -> int
{
    auto exit_code = EXIT_FAILURE;
    auto* factory = fastdds::DomainParticipantFactory::get_instance();
    auto* participant = factory->create_participant(0, fastdds::PARTICIPANT_QOS_DEFAULT);
    if (participant == nullptr) [[unlikely]]
    {
        report_failure("Creating the participant");
        return exit_code;
    }

    exit_code = run_demo(participant);
    if (!is_ok(participant->delete_contained_entities())) [[unlikely]]
    {
        report_failure("Deleting contained entities");
        exit_code = EXIT_FAILURE;
    }

    if (!is_ok(factory->delete_participant(participant))) [[unlikely]]
    {
        report_failure("Deleting the participant");
        exit_code = EXIT_FAILURE;
    }

    return exit_code;
}
