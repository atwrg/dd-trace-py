include(FindCppcheck)

function(add_ddup_config target)
    target_compile_options(${target} PRIVATE
      "$<$<CONFIG:Debug>:-Og -ggdb3>"
      "$<$<CONFIG:Release>:-Os>"
      -ffunction-sections -fno-semantic-interposition -Wall -Werror -Wextra -Wshadow -Wnon-virtual-dtor -Wold-style-cast
    )
    target_link_options(${target} PRIVATE
      "$<$<CONFIG:Release>:-s>"
      -Wl,--as-needed -Wl,-Bsymbolic-functions -Wl,--gc-sections
    )
    set_property(TARGET ${target} PROPERTY INTERPROCEDURAL_OPTIMIZATION TRUE)

    # Propagate sanitizers
    if (SANITIZE_OPTIONS)
        # Some sanitizers (or the analysis--such as symbolization--tooling thereof) work better with frame
        # pointers, so we include it here.
        target_compile_options(${target} PRIVATE -fsanitize=${SANITIZE_OPTIONS} -fno-omit-frame-pointer)
        target_link_options(${target} PRIVATE -fsanitize=${SANITIZE_OPTIONS})
    endif()

    # If DO_FANALYZER is specified and we're using gcc, then we can use -fanalyzer
    if (DO_FANALYZER AND CMAKE_CXX_COMPILER_ID MATCHES "GNU")
      target_compile_options(${target} PRIVATE -fanalyzer)
    endif()

    # If DO_CPPCHECK is specified, then we can use cppcheck
    add_cppcheck_target(cppcheck_dd_${target} ${CMAKE_CURRENT_SOURCE_DIR})
endfunction()