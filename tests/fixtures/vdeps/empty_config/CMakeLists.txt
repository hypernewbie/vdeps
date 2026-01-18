# Minimal CMakeLists.txt for testing vdeps with libs=null (auto-detect)
# This generates multiple library artefacts without specific names in TOML

cmake_minimum_required(VERSION 3.15)
project(emptyconfig VERSION 1.0.0 LANGUAGES NONE)

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
set(EMPTY_OUTPUT_DIR "${CMAKE_CURRENT_BINARY_DIR}")

# Function to generate a library
function(generate_emptylib lib_name)
    set(LIB_FULLNAME "${lib_name}")
    
    if(WIN32)
        set(LIB_EXT ".lib")
    else()
        set(LIB_EXT ".a")
    endif()
    
    execute_process(
        COMMAND ${Python3_EXECUTABLE}
                "${CMAKE_CURRENT_SOURCE_DIR}/../gen_artifact.py"
                lib
                "${LIB_FULLNAME}"
                "${LIB_EXT}"
                "${EMPTY_OUTPUT_DIR}"
                --platform ${PLATFORM_TAG}
        RESULT_VARIABLE GEN_RESULT
    )
    
    if(NOT GEN_RESULT EQUAL 0)
        message(FATAL_ERROR "Failed to generate ${lib_name} library")
    endif()
endfunction()

# Generate multiple libraries - these should be auto-detected when libs=null
generate_emptylib("emptyfoo")
generate_emptylib("emptybar") 
generate_emptylib("emptybaz")
generate_emptylib("emptyqux")

# Custom target
add_custom_target(emptyconfig ALL
    COMMENT "Generated emptyconfig libraries for "
)
