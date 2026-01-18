# Minimal CMakeLists.txt for testing vdeps with mixed artefacts
# This generates libraries, executables, and extra files using Python

cmake_minimum_required(VERSION 3.15)
project(mixed_project VERSION 1.0.0 LANGUAGES NONE)

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
set(MIXED_OUTPUT_DIR "${CMAKE_CURRENT_BINARY_DIR}")

# Note: filenames don't include build type (debug/release is in the build directory path)
# This matches how real CMake projects typically structure their outputs

# Generate library
set(LIB_NAME "mixed")
if(WIN32)
    set(LIB_EXT ".lib")
else()
    set(LIB_EXT ".a")
endif()

execute_process(
    COMMAND ${Python3_EXECUTABLE}
            "${CMAKE_CURRENT_SOURCE_DIR}/../gen_artifact.py"
            lib
            "${LIB_NAME}"
            "${LIB_EXT}"
            "${MIXED_OUTPUT_DIR}"
            --platform ${PLATFORM_TAG}
    RESULT_VARIABLE GEN_LIB_RESULT
)

if(NOT GEN_LIB_RESULT EQUAL 0)
    message(FATAL_ERROR "Failed to generate mixed library")
endif()

# Generate executable
set(EXE_NAME "mixed_tool")
if(WIN32)
    set(EXE_EXT ".exe")
else()
    set(EXE_EXT "")
endif()

execute_process(
    COMMAND ${Python3_EXECUTABLE}
            "${CMAKE_CURRENT_SOURCE_DIR}/../gen_artifact.py"
            exe
            "${EXE_NAME}"
            "${EXE_EXT}"
            "${MIXED_OUTPUT_DIR}"
            --platform ${PLATFORM_TAG}
    RESULT_VARIABLE GEN_EXE_RESULT
)

if(NOT GEN_EXE_RESULT EQUAL 0)
    message(FATAL_ERROR "Failed to generate mixed executable")
endif()

# Generate extra file
set(DATA_NAME "data")

execute_process(
    COMMAND ${Python3_EXECUTABLE}
            "${CMAKE_CURRENT_SOURCE_DIR}/../gen_artifact.py"
            extra
            "${DATA_NAME}.blob"
            ""
            "${MIXED_OUTPUT_DIR}"
            --platform ${PLATFORM_TAG}
    RESULT_VARIABLE GEN_DATA_RESULT
)

if(NOT GEN_DATA_RESULT EQUAL 0)
    message(FATAL_ERROR "Failed to generate data file")
endif()

# Custom target
add_custom_target(mixed_project ALL
    COMMENT "Generated mixed artefacts for ${BUILD_TYPE_LOWER}"
)