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

find_package(nlohmann_json REQUIRED)  # FIX: fastdds vcpkg port dependency bug
find_package(fastdds CONFIG REQUIRED)
target_link_libraries(${CUR_TARGET} INTERFACE fastdds)

#--- executable ----------------------------------------------------------------------------------

set(CUR_TARGET demo)
add_executable(${CUR_TARGET})

target_link_libraries(${CUR_TARGET} PRIVATE dependencies)
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

    target_link_libraries(${CUR_TARGET} PRIVATE GTest::gtest_main GTest::gmock)
    target_link_libraries(${CUR_TARGET} PRIVATE dependencies)
    target_include_directories(${CUR_TARGET} PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}")
    configure_cxx_options(${CUR_TARGET})

    target_sources(${CUR_TARGET} PRIVATE
        "test/tests.cpp"
        )

    include(GoogleTest)
    gtest_discover_tests(${CUR_TARGET})
endif()
