cmake_minimum_required(VERSION 3.30)

project(demo)

include(cmake/modules.cmake)

#--- common --------------------------------------------------------------------------------------

function(configure_cxx_options target)
    target_cxx_standard(${target} 20)
    target_set_cxx_base_compile_options(${target})
    target_treat_warnings_as_errors(${target})
endfunction()

#--- dependencies --------------------------------------------------------------------------------

set(CUR_TARGET dependencies)
add_library(${CUR_TARGET} INTERFACE)

find_package(fmt CONFIG REQUIRED)
target_link_libraries(${CUR_TARGET} INTERFACE fmt::fmt)

#--- grpc_gen ------------------------------------------------------------------------------------

set(CUR_TARGET grpc_gen)
add_library(${CUR_TARGET} STATIC)

find_package(Protobuf CONFIG REQUIRED)
find_package(gRPC CONFIG REQUIRED)

set(PROTO_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/proto")
set(PROTO_GENERATED_DIR "${CMAKE_CURRENT_BINARY_DIR}/grpc_gen")

file(MAKE_DIRECTORY "${PROTO_GENERATED_DIR}")

target_link_libraries(${CUR_TARGET} PUBLIC protobuf::libprotobuf gRPC::grpc++)
target_include_directories(${CUR_TARGET} PUBLIC "${CMAKE_CURRENT_BINARY_DIR}")

target_sources(${CUR_TARGET} PRIVATE
    "${PROTO_ROOT}/greet.proto"
    )

protobuf_generate(
    TARGET ${CUR_TARGET}
    LANGUAGE cpp
    IMPORT_DIRS "${PROTO_ROOT}"
    PROTOC_OUT_DIR "${PROTO_GENERATED_DIR}"
    )

protobuf_generate(
    TARGET ${CUR_TARGET}
    LANGUAGE grpc
    GENERATE_EXTENSIONS .grpc.pb.h .grpc.pb.cc
    IMPORT_DIRS "${PROTO_ROOT}"
    PROTOC_OUT_DIR "${PROTO_GENERATED_DIR}"
    PLUGIN "protoc-gen-grpc=$<TARGET_FILE:gRPC::grpc_cpp_plugin>"
    )

# Suppress C4996 (deprecated) warning from gRPC headers
if(MSVC)
    target_compile_options(${CUR_TARGET} PUBLIC /wd4996)
endif()

#--- executable ----------------------------------------------------------------------------------

set(CUR_TARGET demo)
add_executable(${CUR_TARGET})

target_link_libraries(${CUR_TARGET} PRIVATE dependencies)
target_link_libraries(${CUR_TARGET} PRIVATE grpc_gen)
target_include_directories(${CUR_TARGET} PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}")
configure_cxx_options(${CUR_TARGET})

target_sources(${CUR_TARGET} PRIVATE
    "demo_project/main.cpp"
    )

#--- tests executable ----------------------------------------------------------------------------

option(DEMO_BUILD_TESTS "Build tests" ON)

if(DEMO_BUILD_TESTS AND "${CMAKE_BUILD_TYPE}" STREQUAL "Debug")
    enable_testing()
    find_package(GTest CONFIG REQUIRED)

    set(CUR_TARGET tests)
    add_executable(${CUR_TARGET})

    # GTest::gtest_main is intentionally not used:
    # tests.cpp provides a custom main() to explicitly control gRPC's
    # default EventEngine lifetime and shut it down before MSVC CRT/STL teardown
    target_link_libraries(${CUR_TARGET} PRIVATE
        # GTest::gtest_main
        GTest::gtest
        GTest::gmock
        )

    target_link_libraries(${CUR_TARGET} PRIVATE dependencies)
    target_link_libraries(${CUR_TARGET} PRIVATE grpc_gen)
    target_include_directories(${CUR_TARGET} PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}")
    configure_cxx_options(${CUR_TARGET})

    target_sources(${CUR_TARGET} PRIVATE
        "test/tests.cpp"
        )

    include(GoogleTest)
    gtest_discover_tests(${CUR_TARGET})
endif()
