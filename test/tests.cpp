#include <gmock/gmock.h>
#include <gtest/gtest.h>

#include <proto_gen/user.pb.h>

#include <string>

using namespace testing;

namespace test
{

TEST(DemoProtobufTest, SerializeAndParseUser)
{
    auto original = user::User{};
    original.set_name("Alice");
    original.set_id(42);

    auto bytes = std::string{};
    ASSERT_TRUE(original.SerializeToString(&bytes));

    auto restored = user::User{};
    ASSERT_TRUE(restored.ParseFromString(bytes));
    EXPECT_EQ(restored.name(), "Alice");
    EXPECT_EQ(restored.id(), 42);
}

}  // namespace test
