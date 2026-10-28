#pragma once
#include "odb2vtk_core/outputs.hpp"
#include <fstream>

namespace odb2vtk_core::detail {
// Internal lifetime used by both callback publication and the streaming sink.
class AtomicFile {
public:
  explicit AtomicFile(const std::filesystem::path&);
  ~AtomicFile() noexcept;
  AtomicFile(const AtomicFile&) = delete;
  AtomicFile& operator=(const AtomicFile&) = delete;
  std::ostream& stream() { return stream_; }
  void publish();
private:
  std::filesystem::path destination_, temporary_;
  std::ofstream stream_;
};
}
