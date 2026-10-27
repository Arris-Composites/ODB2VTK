# Explicit SDK discovery. No solver/GUI library globbing or historical paths.
set(ABQ_SDK_ROOT "" CACHE PATH "Abaqus EstProducts root containing SMAOdb")
find_path(AbqSDK_INCLUDE_DIR NAMES odb_API.h HINTS "${ABQ_SDK_ROOT}"
  PATH_SUFFIXES win_b64/code/include linux_a64/code/include code/include include)
find_path(AbqSDK_PUBLIC_INCLUDE_DIR NAMES SMAOdb/PublicInterfaces/odb_API.h
  HINTS "${ABQ_SDK_ROOT}")
set(_AbqSDK_required AbqSDK_INCLUDE_DIR AbqSDK_PUBLIC_INCLUDE_DIR)
set(_AbqSDK_libraries)
# Direct dependencies verified by compiling/linking with Abaqus 2025 on Windows.
foreach(_component IN ITEMS OdbApi OdbCore BasCoreUtils BasAlloc BasShared)
  find_library(AbqSDK_${_component}_LIBRARY NAMES ABQSMA${_component}
    HINTS "${ABQ_SDK_ROOT}"
    PATH_SUFFIXES win_b64/code/lib linux_a64/code/lib code/lib lib)
  list(APPEND _AbqSDK_required AbqSDK_${_component}_LIBRARY)
  list(APPEND _AbqSDK_libraries "${AbqSDK_${_component}_LIBRARY}")
  mark_as_advanced(AbqSDK_${_component}_LIBRARY)
endforeach()

include(FindPackageHandleStandardArgs)
find_package_handle_standard_args(AbqSDK
  REQUIRED_VARS ${_AbqSDK_required}
  REASON_FAILURE_MESSAGE "Set ABQ_SDK_ROOT to the installed EstProducts directory, or specify the AbqSDK include/library cache entries explicitly.")
mark_as_advanced(AbqSDK_INCLUDE_DIR AbqSDK_PUBLIC_INCLUDE_DIR)

if(AbqSDK_FOUND AND NOT TARGET AbqSDK::Odb)
  add_library(AbqSDK::Odb INTERFACE IMPORTED)
  set_target_properties(AbqSDK::Odb PROPERTIES
    INTERFACE_INCLUDE_DIRECTORIES "${AbqSDK_INCLUDE_DIR};${AbqSDK_PUBLIC_INCLUDE_DIR}"
    INTERFACE_LINK_LIBRARIES "${_AbqSDK_libraries}")
  if(WIN32)
    set_property(TARGET AbqSDK::Odb PROPERTY INTERFACE_COMPILE_DEFINITIONS
      _WINDOWS_SOURCE ABQ_WIN86_64 HKS_NT NTI)
  endif()
endif()
