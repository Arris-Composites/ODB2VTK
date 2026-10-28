#pragma once

#include "writers.hpp"
#include <filesystem>
#include <functional>

namespace odb2vtk_core {
class OutputOptions {
public:
  OutputOptions(std::filesystem::path directory, std::string name,
                std::string suffix = "", bool write_pvd = true,
                VtuFormat format = VtuFormat::ascii);
  static OutputOptions from_odb(const std::filesystem::path&, std::string suffix = "",
                              bool write_pvd = true, VtuFormat = VtuFormat::ascii);
  std::string run_name() const { return name_ + suffix_; }
  std::filesystem::path data_directory() const;
  std::filesystem::path header_path() const;
  std::filesystem::path history_path() const;
  std::filesystem::path collection_path() const;
  std::filesystem::path frame_path(const std::string& step, std::size_t frame) const;
  bool write_pvd() const noexcept { return write_pvd_; }
  VtuFormat format() const noexcept { return format_; }
private:
  std::filesystem::path artifact(const std::string&) const;
  std::filesystem::path directory_;
  std::string name_, suffix_;
  bool write_pvd_;
  VtuFormat format_;
};

void validate_destinations(const std::vector<std::filesystem::path>&);

// Same-directory temporary, checked close, then replacement. Exceptions from
// serialize propagate without truncating the previous destination. No request-
// wide transaction or fsync/durability guarantee is implied.
void atomic_output(const std::filesystem::path&,
                   const std::function<void(std::ostream&)>& serialize);
}
