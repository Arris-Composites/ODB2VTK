#include "../core/profiling.hpp"
#include <cmath>
#include <iostream>
#include <numeric>
#include <stdexcept>

using namespace odb2vtk_core::detail;
int main() {
  try {
    Profile profile;
    { PhaseScope inactive(Phase::validation); }
    if (active_profile || std::accumulate(profile.seconds.begin(),profile.seconds.end(),0.0)!=0)
      throw std::runtime_error("Inactive scope recorded timing");
    double elapsed = 0;
    {
      ProfileSession session(&profile);
      const auto started=std::chrono::steady_clock::now();
      {
        PhaseScope root(Phase::orchestration);
        { PhaseScope read(Phase::field_read); { PhaseScope assembly(Phase::field_assembly); } }
        { PhaseScope assembly(Phase::field_assembly); { PhaseScope nested(Phase::field_assembly); } }
      }
      elapsed=std::chrono::duration<double>(std::chrono::steady_clock::now()-started).count();
      if (profile.top) throw std::runtime_error("Unbalanced profile stack");
      try { PhaseScope cleanup(Phase::odb_close); throw std::runtime_error("deliberate"); }
      catch (const std::runtime_error&) {}
      if (profile.top) throw std::runtime_error("Exception left active profile scope");
      { ProfileSession disabled(nullptr); PhaseScope ignored(Phase::history); }
      if (active_profile!=&profile) throw std::runtime_error("Session did not restore recorder");
    }
    if (active_profile) throw std::runtime_error("Session leaked recorder");
    for (auto value : profile.seconds) if (value<0) throw std::runtime_error("Negative exclusive duration");
    const auto sum=std::accumulate(profile.seconds.begin(),profile.seconds.end(),0.0)-profile.seconds[static_cast<std::size_t>(Phase::odb_close)];
    // Equal clock ticks can leave only floating-point accumulation roundoff.
    if (sum>elapsed+1e-12 || profile.seconds[static_cast<std::size_t>(Phase::history)]!=0)
      throw std::runtime_error("Nested scopes double-counted or disabled recording failed");
    std::cout << "Exclusive profiling, nesting, inactive session and exception cleanup passed\n";
    return 0;
  } catch (const std::exception& error) { std::cerr << error.what() << '\n';return 1; }
}
