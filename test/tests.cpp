#include <gmock/gmock.h>
#include <gtest/gtest.h>

#include <fmt/format.h>
#include <grpc/event_engine/event_engine.h>
#include <grpc_gen/greet.grpc.pb.h>
#include <grpc_gen/greet.pb.h>
#include <grpcpp/grpcpp.h>

#include <chrono>
#include <filesystem>
#include <string>

using namespace testing;

// Used instead of GTest::gtest_main to explicitly control the lifetime of
// gRPC's default EventEngine and shut it down before MSVC CRT/STL teardown
auto main(int argc, char** argv) -> int
{
    // Workaround for gRPC EventEngine teardown racing with MSVC CRT/STL shutdown on Windows.
    // Keep the default EventEngine alive for the entire test process
    // https://github.com/grpc/grpc/issues/43440
    grpc_event_engine::experimental::SetDefaultEventEngine(grpc_event_engine::experimental::CreateEventEngine());

    InitGoogleTest(&argc, argv);
    const auto result = RUN_ALL_TESTS();

    // Wait for the default EventEngine and its worker threads to shut down
    // before returning from main() and starting CRT/STL teardown
    grpc_event_engine::experimental::ShutdownDefaultEventEngine();

    return result;
}

namespace test
{

class GreeterImpl final : public greet::Greeter::Service
{
  public:
    auto SayHello(grpc::ServerContext*, const greet::HelloRequest* request, greet::HelloReply* reply)
        -> grpc::Status override
    {
        reply->set_message("Hello, " + request->name() + "!");
        return grpc::Status::OK;
    }
};

static auto test_client(const auto& channel) -> void
{
    auto stub = greet::Greeter::NewStub(channel);

    auto context = grpc::ClientContext{};
    context.set_wait_for_ready(true);
    context.set_deadline(std::chrono::system_clock::now() + std::chrono::seconds(5));

    auto request = greet::HelloRequest{};
    request.set_name("World");

    auto reply = greet::HelloReply{};
    auto status = stub->SayHello(&context, request, &reply);

    ASSERT_TRUE(status.ok()) << status.error_message();
    EXPECT_EQ(reply.message(), "Hello, World!");
}

TEST(DemoGrpcTest, LocalhostTcp)
{
    auto port = 0;
    const auto server_endpoint = "127.0.0.1:0";

    auto service = GreeterImpl{};
    auto builder = grpc::ServerBuilder{};
    builder.AddListeningPort(server_endpoint, grpc::InsecureServerCredentials(), &port);
    builder.RegisterService(&service);
    auto server = builder.BuildAndStart();

    ASSERT_NE(server, nullptr);
    ASSERT_GT(port, 0);

    {
        const auto remote_endpoint = fmt::format("127.0.0.1:{}", port);
        auto channel = grpc::CreateChannel(remote_endpoint, grpc::InsecureChannelCredentials());
        test_client(channel);
    }

    server->Shutdown();
    server->Wait();
}

TEST(DemoGrpcTest, UnixDomainSockets)
{
    const auto socket_path = (std::filesystem::temp_directory_path() / "greet.sock").string();
    const auto server_endpoint = "unix:" + socket_path;
    std::filesystem::remove(socket_path);

    auto service = GreeterImpl{};
    auto builder = grpc::ServerBuilder{};
    builder.AddListeningPort(server_endpoint, grpc::InsecureServerCredentials());
    builder.RegisterService(&service);
    auto server = builder.BuildAndStart();

    ASSERT_NE(server, nullptr);

    {
        const auto channel = grpc::CreateChannel(server_endpoint, grpc::InsecureChannelCredentials());
        test_client(channel);
    }

    server->Shutdown();
    server->Wait();

    std::filesystem::remove(socket_path);
}

TEST(DemoGrpcTest, InProcess)
{
    auto service = GreeterImpl{};
    auto builder = grpc::ServerBuilder{};
    builder.RegisterService(&service);
    auto server = builder.BuildAndStart();

    ASSERT_NE(server, nullptr);

    {
        const auto args = grpc::ChannelArguments{};
        const auto channel = server->InProcessChannel(args);
        test_client(channel);
    }

    server->Shutdown();
    server->Wait();
}

}  // namespace test
