#include "profiling.hpp"
namespace odb2vtk_core::detail {
thread_local Profile *active_profile = nullptr;
}
