# Minimal CMakeLists.txt for testing vdeps with complex library
# This generates multiple library artefacts using Python

cmake_minimum_required(VERSION 3.15)
project(complex_lib VERSION 1.0.0 LANGUAGES NONE)

# Find Python to generate artefacts
find_package(Python3 REQUIRED COMPONENTS Interpreter)

# Get build type for suffix
if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Debug)
endif()

string(TOLOWER ${CMAKE_BUILD_TYPE} BUILD_TYPE_LOWER)

# Determine platform
if(WIN32)
    set(PLATFORM_TAG "win")
elseif(APPLE)
    set(PLATFORM_TAG "mac")
else()
    set(PLATFORM_TAG "linux")
endif()

# Output directory
set(COMPLEX_OUTPUT_DIR "${CMAKE_CURRENT_BINARY_DIR}")

# Function to generate a library
function(generate_complex_lib target_name)
    # Use clean name without build type suffix (build type is already in build_dir path)
    set(LIB_NAME "complex_${target_name}")
    
    # Determine extension and basename
    if(WIN32)
        set(LIB_EXT ".lib")
        set(LIB_BASENAME "${LIB_NAME}")
    else()
        set(LIB_EXT ".a")
        set(LIB_BASENAME "${LIB_NAME}")
    endif()
    
    # Generate the library file
    execute_process(
        COMMAND ${Python3_EXECUTABLE}
                "${CMAKE_CURRENT_SOURCE_DIR}/../gen_artifact.py"
                lib
                "${LIB_BASENAME}"
                "${LIB_EXT}"
                "${COMPLEX_OUTPUT_DIR}"
                --platform ${PLATFORM_TAG}
        RESULT_VARIABLE GEN_RESULT
    )
    
    if(NOT GEN_RESULT EQUAL 0)
        message(FATAL_ERROR "Failed to generate ${target_name} library")
    endif()
endfunction()

# Generate multiple library targets
generate_complex_lib("core")
generate_complex_lib("utils")
generate_complex_lib("extras")

# Custom target so CMake doesn't complain about no targets
add_custom_target(complex_lib ALL
    COMMENT "Generated complex libraries for ${BUILD_TYPE_LOWER}"
)
