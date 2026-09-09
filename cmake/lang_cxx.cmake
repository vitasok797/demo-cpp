function(target_cxx_standard target cxx_standard)
    set_target_properties(${target} PROPERTIES
        CXX_STANDARD ${cxx_standard}
        CXX_STANDARD_REQUIRED YES
        CXX_EXTENSIONS OFF
        )
endfunction()

function(target_set_cxx_base_compile_options target)
    if(MSVC)
        target_compile_options(${target} PRIVATE
            /W4
            /utf-8
            /Zc:preprocessor
            /wd4068  # Suppress "unknown pragma" warning
            /wd4702  # Suppress false positive warning (https://github.com/fmtlib/fmt/issues/4810)
            )
    else()
        target_compile_options(${target} PRIVATE
            -Wall
            -Wextra
            -Wpedantic
            -Wconversion
            -Wsign-conversion
            -Wsign-compare
            -Wtype-limits
            -Wswitch-enum
            -Wimplicit-fallthrough
            )
    endif()
endfunction()
