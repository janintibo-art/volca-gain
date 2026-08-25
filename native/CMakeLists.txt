cmake_minimum_required(VERSION 3.10)
project(volcagain_syro C)

set(CMAKE_C_STANDARD 99)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

# Sources du SDK Korg (sous-module git, voir native/README.md)
set(SYRO_DIR "${CMAKE_CURRENT_SOURCE_DIR}/volcasample/syro")

if(NOT EXISTS "${SYRO_DIR}/korg_syro_volcasample.c")
    message(FATAL_ERROR
        "SDK Korg absent.\n"
        "  git submodule add https://github.com/korginc/volcasample native/volcasample\n"
        "  git submodule update --init --recursive")
endif()

file(GLOB SYRO_SRC "${SYRO_DIR}/*.c")

add_library(syro SHARED ${SYRO_SRC} syro_wrap.c)
target_include_directories(syro PRIVATE "${SYRO_DIR}")

# Nom de sortie identique partout : libsyro.so / syro.dll / libsyro.dylib
set_target_properties(syro PROPERTIES
    OUTPUT_NAME "syro"
    PREFIX ""
)

if(WIN32)
    set_target_properties(syro PROPERTIES OUTPUT_NAME "syro" SUFFIX ".dll")
else()
    set_target_properties(syro PROPERTIES PREFIX "lib")
endif()

install(TARGETS syro
        RUNTIME DESTINATION .
        LIBRARY DESTINATION .)
