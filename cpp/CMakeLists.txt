cmake_minimum_required(VERSION 3.2)

project(ODB2VTK)

include(GNUInstallDirs)

if(WIN32)
    add_definitions(-D_WINDOWS_SOURCE)
    # Or for a specific target:
    # target_compile_definitions(MyExecutable PRIVATE -D_WINDOWS_SOURCE)
endif()

# find Abaqus SDK
list(INSERT CMAKE_MODULE_PATH 0
${CMAKE_CURRENT_SOURCE_DIR}/cmake)

find_package(AbqSDK)

set(SOURCES main.cpp odb2vtk.cpp)
set(HEADERS odb2vtk.h)

add_executable(ODB2VTK ${SOURCES} ${HEADERS})
target_link_libraries(ODB2VTK ${ABQ_LIB_TARGETS})
