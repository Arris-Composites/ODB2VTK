#pragma once

// Internal validation instrumentation. Normal callers do not install a session;
// scopes then skip clocks, allocation and recording. No CLI/product dependency.
#include <array>
#include <chrono>
#include <cstddef>

namespace odb2vtk_core::detail {
enum class Phase : std::size_t {
  odb_open,
  validation,
  mesh_preparation,
  field_discovery,
  field_read,
  field_assembly,
  vtu_serialization,
  file_publication,
  history,
  collection,
  odb_close,
  orchestration,
  count
};
inline constexpr std::array<const char *,
                            static_cast<std::size_t>(Phase::count)>
    phase_names = {"odb_open",          "validation",       "mesh_preparation",
                   "field_discovery",   "field_read",       "field_assembly",
                   "vtu_serialization", "file_publication", "history",
                   "collection",        "odb_close",        "orchestration"};
class PhaseScope;
struct Profile {
  std::array<double, static_cast<std::size_t>(Phase::count)> seconds{};
  PhaseScope *top = nullptr;
};
extern thread_local Profile *active_profile;
class ProfileSession {
public:
  explicit ProfileSession(Profile *profile) noexcept
      : previous_(active_profile) {
    active_profile = profile;
  }
  ~ProfileSession() { active_profile = previous_; }
  ProfileSession(const ProfileSession &) = delete;
  ProfileSession &operator=(const ProfileSession &) = delete;

private:
  Profile *previous_;
};
class PhaseScope {
public:
  explicit PhaseScope(Phase phase) noexcept
      : profile_(active_profile), phase_(phase) {
    if (profile_) {
      parent_ = profile_->top;
      profile_->top = this;
      started_ = Clock::now();
    }
  }
  ~PhaseScope() noexcept {
    if (!profile_)
      return;
    const double elapsed =
        std::chrono::duration<double>(Clock::now() - started_).count();
    profile_->seconds[static_cast<std::size_t>(phase_)] += elapsed - children_;
    profile_->top = parent_;
    if (parent_)
      parent_->children_ += elapsed;
  }
  PhaseScope(const PhaseScope &) = delete;
  PhaseScope &operator=(const PhaseScope &) = delete;

private:
  using Clock = std::chrono::steady_clock;
  Profile *profile_;
  Phase phase_;
  PhaseScope *parent_ = nullptr;
  Clock::time_point started_;
  double children_ = 0;
};
} // namespace odb2vtk_core::detail
