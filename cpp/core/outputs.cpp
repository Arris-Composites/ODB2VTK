#include "odb2vtk_core/outputs.hpp"
#include "atomic_file.hpp"
#include "profiling.hpp"
#include <algorithm>
#include <atomic>
#include <cerrno>
#include <cwctype>
#include <iomanip>
#include <random>
#include <set>
#include <sstream>
#include <system_error>
#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#else
#include <fcntl.h>
#include <unistd.h>
#endif

namespace odb2vtk_core {
namespace fs = std::filesystem;
namespace {
const std::string& leaf(const std::string& name) {
  bool invalid = name.empty() || name == "." || name == "..";
  if (!name.empty()) invalid = invalid || name.back() == '.' || name.back() == ' ';
  for (unsigned char c : name)
    if (c < 32 || std::string("<>:\"/\\|?*").find(c) != std::string::npos) invalid = true;
  auto base = name.substr(0, name.find('.'));
  std::transform(base.begin(), base.end(), base.begin(), [](unsigned char c) {
    return c >= 'a' && c <= 'z' ? c - 'a' + 'A' : c;
  });
  if (base == "CON" || base == "PRN" || base == "AUX" || base == "NUL" ||
      (base.size() == 4 && (base.substr(0,3) == "COM" || base.substr(0,3) == "LPT") &&
       base[3] >= '1' && base[3] <= '9')) invalid = true;
  if (invalid) throw OutputError("Invalid output filename: " + name);
  return name;
}
void check_directory(const fs::path& file) {
  if (fs::is_directory(file)) throw OutputError("Output file is a directory: " + file.u8string());
  auto parent = file.parent_path();
  while (!parent.empty() && !fs::exists(parent)) {
    const auto next = parent.parent_path();
    if (next == parent) break;
    parent = next;
  }
  if (!parent.empty() && !fs::is_directory(parent))
    throw OutputError("Output parent is not a directory: " + parent.u8string());
}
fs::path reserve_temporary(const fs::path& parent) {
  static std::atomic<std::uint64_t> counter{0};
  std::random_device random;
  for (int attempt = 0; attempt < 100; ++attempt) {
    std::ostringstream name;
    name << ".odb2vtk-" << std::hex << random() << '-' << random() << '-' << counter++ << ".tmp";
    const auto path = parent / name.str();
#ifdef _WIN32
    HANDLE handle = CreateFileW(path.c_str(), GENERIC_WRITE, 0, nullptr, CREATE_NEW,
                                FILE_ATTRIBUTE_NORMAL, nullptr);
    if (handle != INVALID_HANDLE_VALUE) { CloseHandle(handle); return path; }
    const auto error = GetLastError();
    if (error != ERROR_FILE_EXISTS && error != ERROR_ALREADY_EXISTS)
      throw OutputError("Cannot prepare temporary output: " + std::system_category().message(error));
#else
    const int descriptor = ::open(path.c_str(), O_WRONLY | O_CREAT | O_EXCL, 0600);
    if (descriptor >= 0) { ::close(descriptor); return path; }
    if (errno != EEXIST)
      throw OutputError("Cannot prepare temporary output: " + std::generic_category().message(errno));
#endif
  }
  throw OutputError("Cannot reserve unique temporary output");
}
}
OutputOptions::OutputOptions(fs::path directory, std::string name, std::string suffix,
                             bool pvd, VtuFormat format)
    : directory_(std::move(directory)), name_(std::move(name)), suffix_(std::move(suffix)),
      write_pvd_(pvd), format_(format) {
  leaf(name_); leaf(run_name());
  if (directory_.u8string().find('\0') != std::string::npos) throw OutputError("Output directory contains NUL");
  if (format != VtuFormat::ascii && format != VtuFormat::binary) throw OutputError("Invalid VTU format");
  try { directory_ = fs::absolute(directory_.empty() ? fs::path(".") : directory_).lexically_normal(); }
  catch (const fs::filesystem_error& error) { throw OutputError(error.what()); }
}
OutputOptions OutputOptions::from_odb(const fs::path& odb, std::string suffix, bool pvd, VtuFormat format) {
  const auto name = odb.filename().u8string();
  return OutputOptions(odb.parent_path(), name.substr(0, name.find('.')), std::move(suffix), pvd, format);
}
fs::path OutputOptions::data_directory() const { return directory_ / fs::u8path(run_name()); }
fs::path OutputOptions::header_path() const { return directory_ / fs::u8path(run_name() + ".json"); }
fs::path OutputOptions::artifact(const std::string& filename) const { return data_directory() / fs::u8path(leaf(filename)); }
fs::path OutputOptions::history_path() const { return artifact(run_name() + ".csv"); }
fs::path OutputOptions::collection_path() const { return artifact(run_name() + ".pvd"); }
fs::path OutputOptions::frame_path(const std::string& step, std::size_t frame) const {
  return artifact(step + "_" + std::to_string(frame) + ".vtu");
}
void validate_destinations(const std::vector<fs::path>& paths) {
  try {
    std::set<fs::path::string_type> identities;
    for (const auto& path : paths) {
      auto identity = fs::absolute(path).lexically_normal().native();
#ifdef _WIN32
      std::transform(identity.begin(), identity.end(), identity.begin(), [](wchar_t c) { return std::towlower(c); });
#endif
      if (!identities.insert(identity).second) throw OutputError("Requested output filenames collide");
      check_directory(path);
    }
  } catch (const fs::filesystem_error& error) { throw OutputError(error.what()); }
}

detail::AtomicFile::AtomicFile(const fs::path& path) {
  PhaseScope timing(Phase::file_publication);
  try {
    destination_ = fs::absolute(path).lexically_normal();
    check_directory(destination_);
    fs::create_directories(destination_.parent_path());
    temporary_ = reserve_temporary(destination_.parent_path());
    stream_.exceptions(std::ios::badbit | std::ios::failbit);
    stream_.open(temporary_, std::ios::binary | std::ios::out | std::ios::trunc);
  } catch (const std::exception& error) {
    std::error_code ignored;
    if (!temporary_.empty()) fs::remove(temporary_, ignored);
    throw OutputError(std::string("Cannot prepare output: ") + error.what());
  }
}
detail::AtomicFile::~AtomicFile() noexcept {
  PhaseScope timing(Phase::file_publication);
  try { if (stream_.is_open()) stream_.close(); } catch (...) {}
  if (!temporary_.empty()) { std::error_code ignored; fs::remove(temporary_, ignored); }
}
void detail::AtomicFile::publish() {
  PhaseScope timing(Phase::file_publication);
  if (temporary_.empty()) throw OutputError("Output already published");
  try { stream_.flush(); stream_.close(); }
  catch (const std::exception& error) { throw OutputError(std::string("Cannot complete output: ") + error.what()); }
#ifdef _WIN32
  if (!MoveFileExW(temporary_.c_str(), destination_.c_str(), MOVEFILE_REPLACE_EXISTING))
    throw OutputError("Cannot publish output: " + std::system_category().message(GetLastError()));
#else
  std::error_code error;
  fs::rename(temporary_, destination_, error);
  if (error) throw OutputError("Cannot publish output: " + error.message());
#endif
  temporary_.clear();
}
void atomic_output(const fs::path& path, const std::function<void(std::ostream&)>& serialize) {
  detail::AtomicFile file(path);
  serialize(file.stream());
  file.publish();
}
}
