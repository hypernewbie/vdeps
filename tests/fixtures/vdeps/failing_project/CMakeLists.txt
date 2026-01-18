# Deliberately broken CMakeLists.txt for testing error handling
# This will cause CMake to fail during configuration

cmake_minimum_required(VERSION 3.15)
project(failing_project LANGUAGES NONE)

# Invalid CMake syntax - this should cause a fatal error
this_is_invalid_cmake_syntax_that_will_cause_failure()

# This line should never be reached
add_custom_target(failing_project ALL)
