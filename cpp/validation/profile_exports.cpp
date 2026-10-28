#include "../core/profiling.hpp"
#include "odb2vtk_core/abaqus_source.hpp"
#include "odb2vtk_core/exporter.hpp"
#include <chrono>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <numeric>
#include <sstream>
#ifdef _WIN32
#define NOMINMAX
#include <windows.h>

// psapi.h requires the Windows types above; preserve this include group.
#include <psapi.h>
#else
#include <sys/resource.h>
#endif

using namespace odb2vtk_core;
namespace {
std::uint64_t peak_rss() {
#ifdef _WIN32
  PROCESS_MEMORY_COUNTERS counters{};
  if (!GetProcessMemoryInfo(GetCurrentProcess(), &counters, sizeof(counters)))
    throw std::runtime_error("Cannot query process memory");
  return counters.PeakWorkingSetSize;
#else
  struct rusage usage {};
  if (getrusage(RUSAGE_SELF, &usage))
    throw std::runtime_error("Cannot query process memory");
#ifdef __APPLE__
  return usage.ru_maxrss;
#else
  return static_cast<std::uint64_t>(usage.ru_maxrss) * 1024;
#endif
#endif
}
} // namespace
int main(int argc, char **argv) {
  if (argc != 7 && argc != 8) {
    std::cerr << "Usage: odb2vtk_profile_exports ODB INSTANCES FRAMES SUFFIX "
                 "ascii|binary REPORT [--no-phases]\n";
    return 2;
  }
  try {
    const bool enabled = argc == 7;
    if (!enabled && std::string(argv[7]) != "--no-phases")
      throw std::invalid_argument("Invalid profiling option");
    const std::string format = argv[5];
    if (format != "ascii" && format != "binary")
      throw OutputError("Invalid format");
    const auto outputs = OutputOptions::from_odb(
        argv[1], argv[4], true,
        format == "binary" ? VtuFormat::binary : VtuFormat::ascii);
    std::vector<std::string> instances;
    std::vector<std::int64_t> indices;
    std::string token;
    std::istringstream names(argv[2]), frames(argv[3]);
    while (std::getline(names, token, ','))
      instances.push_back(token);
    while (std::getline(frames, token, ','))
      indices.push_back(std::stoll(token));
    const Selection selection(instances, {{"Step-1", indices}});
    detail::Profile profile;
    ExportResult result;
    const auto start = std::chrono::steady_clock::now();
    {
      detail::ProfileSession session(enabled ? &profile : nullptr);
      detail::PhaseScope workflow(detail::Phase::orchestration);
      AbaqusSource source(argv[1]);
      Exporter exporter(source);
      auto history = exporter.export_history(selection, outputs);
      result = exporter.export_frames(selection, outputs);
      result.paths.insert(result.paths.begin(), history.paths.begin(),
                          history.paths.end());
      source.close();
    }
    const double seconds =
        std::chrono::duration<double>(std::chrono::steady_clock::now() - start)
            .count();
    if (enabled)
      profile.seconds[static_cast<std::size_t>(detail::Phase::orchestration)] +=
          seconds -
          std::accumulate(profile.seconds.begin(), profile.seconds.end(), 0.0);
    const auto peak = peak_rss();
    std::uintmax_t bytes = 0;
    for (const auto &path : result.paths)
      bytes += std::filesystem::file_size(path);
    std::ofstream report(argv[6]);
    report.exceptions(std::ios::badbit | std::ios::failbit);
    report << std::setprecision(17)
           << "{\"implementation\":\"cpp\",\"vtu_format\":"
           << std::quoted(format) << ",\"seconds\":" << seconds
           << ",\"peak_rss_bytes\":" << peak << ",\"output_bytes\":" << bytes
           << ",\"history\":true,\"paths\":[";
    for (std::size_t i = 0; i < result.paths.size(); ++i)
      report << (i ? "," : "") << std::quoted(result.paths[i].u8string());
    report << "],\"phases_seconds\":";
    if (!enabled)
      report << "null";
    else {
      report << '{';
      for (std::size_t i = 0; i < profile.seconds.size(); ++i)
        report << (i ? "," : "") << std::quoted(detail::phase_names[i]) << ':'
               << profile.seconds[i];
      report << '}';
    }
    report << ",\"native_sdk_initialization_included_in_odb_open\":true}\n";
    report.close();
    std::cout << seconds << " seconds; " << bytes << " bytes\n";
    return 0;
  } catch (const std::exception &error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
