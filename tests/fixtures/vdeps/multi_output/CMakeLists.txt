# Minimal CMakeLists.txt for testing vdeps with subdirectory outputs
# This generates artefacts in bin/ and lib/ subdirectories

cmake_minimum_required(VERSION 3.15)
project(multi_output VERSION 1.0.0 LANGUAGES NONE)

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

# Output directories - use subdirectories
set(LIB_OUTPUT_DIR "${CMAKE_CURRENT_BINARY_DIR}/lib")
set(BIN_OUTPUT_DIR "${CMAKE_CURRENT_BINARY_DIR}/bin")

# Generate library in lib/ subdirectory
set(LIB_NAME "multi")
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
            "${LIB_OUTPUT_DIR}"
            --platform ${PLATFORM_TAG}
    RESULT_VARIABLE GEN_LIB_RESULT
)

if(NOT GEN_LIB_RESULT EQUAL 0)
    message(FATAL_ERROR "Failed to generate multi library")
endif()

# Generate first executable in bin/ subdirectory
set(EXE1_NAME "multi_tool1")
if(WIN32)
    set(EXE1_EXT ".exe")
else()
    set(EXE1_EXT "")
endif()

execute_process(
    COMMAND ${Python3_EXECUTABLE}
            "${CMAKE_CURRENT_SOURCE_DIR}/../gen_artifact.py"
            exe
            "${EXE1_NAME}"
            "${EXE1_EXT}"
            "${BIN_OUTPUT_DIR}"
            --platform ${PLATFORM_TAG}
    RESULT_VARIABLE GEN_EXE1_RESULT
)

if(NOT GEN_EXE1_RESULT EQUAL 0)
    message(FATAL_ERROR "Failed to generate multi_tool1")
endif()

# Generate second executable in bin/ subdirectory
set(EXE2_NAME "multi_tool2")
if(WIN32)
    set(EXE2_EXT ".exe")
else()
    set(EXE2_EXT "")
endif()

execute_process(
    COMMAND ${Python3_EXECUTABLE}
            "${CMAKE_CURRENT_SOURCE_DIR}/../gen_artifact.py"
            exe
            "${EXE2_NAME}"
            "${EXE2_EXT}"
            "${BIN_OUTPUT_DIR}"
            --platform ${PLATFORM_TAG}
    RESULT_VARIABLE GEN_EXE2_RESULT
)

if(NOT GEN_EXE2_RESULT EQUAL 0)
    message(FATAL_ERROR "Failed to generate multi_tool2")
endif()

# Custom target
add_custom_target(multi_output ALL
    COMMENT "Generated multi_output artefacts for "
)