#include "odb2vtk_core/cli.hpp"
#include "odb2vtk_core/in_memory_source.hpp"
#include <fstream>
#include <iostream>
#include <random>
#include <sstream>

using namespace odb2vtk_core;
namespace fs = std::filesystem;
namespace {
int checks = 0;
void check(bool value, const char *message) {
  ++checks;
  if (!value)
    throw std::runtime_error(message);
}
void put(const fs::path &file, const std::string &text = "old") {
  fs::create_directories(file.parent_path());
  std::ofstream(file) << text;
}
std::string read(const fs::path &file) {
  std::ifstream stream(file, std::ios::binary);
  return {std::istreambuf_iterator<char>(stream),
          std::istreambuf_iterator<char>()};
}
struct State {
  int opens = 0, closes = 0, destroyed = 0, meshes = 0;
  bool fail_close = false, fail_history = false, bad_field = false;
};
InMemorySource sample(bool bad) {
  const InstanceMesh mesh{"Part-1",
                          {10, 20},
                          Matrix(2, 3, {0, 0, 0, 1, 0, 0}),
                          {{1, {10, 20}, "B31"}}};
  const MemoryField field{
      {"U", {"Vectors", {"U1", "U2", "U3"}, "NODAL"}, {}, 1},
      {{"Part-1",
        "NODAL",
        {10, 20},
        Matrix(2, 3, {1, 2, 3, 4, 5, 6}),
        {},
        std::nullopt}}};
  MemoryFrame first{.25, {field}, {}}, second{.75, {field}, {}};
  if (bad)
    second.fields[0].blocks[0].labels[1] = 999;
  return InMemorySource({mesh},
                        {{"Step-1", {first, second}, {{"H", {0, 1}, {1, 2}}}},
                         {"Step-2", {first}, {{"other", {0}, {3}}}}});
}
class TrackedSource final : public Source {
public:
  explicit TrackedSource(std::shared_ptr<State> state)
      : state_(std::move(state)), inner_(sample(state_->bad_field)) {
    ++state_->opens;
  }
  ~TrackedSource() override { ++state_->destroyed; }
  bool closed() const noexcept override { return inner_.closed(); }
  void close() override {
    ++state_->closes;
    inner_.close();
    if (state_->fail_close)
      throw SourceError("injected close failure");
  }
  std::vector<std::string> instance_names() const override {
    return inner_.instance_names();
  }
  std::vector<StepInfo> steps() const override { return inner_.steps(); }
  InstanceMesh mesh(const std::string &name) const override {
    ++state_->meshes;
    return inner_.mesh(name);
  }
  double frame_time(const std::string &step, std::size_t frame) const override {
    return inner_.frame_time(step, frame);
  }
  std::vector<std::string> field_names(const std::string &step,
                                       std::size_t frame) const override {
    return inner_.field_names(step, frame);
  }
  FieldInfo
  describe_field(const std::string &step, std::size_t frame,
                 const std::string &name,
                 const std::vector<std::string> &instances) const override {
    return inner_.describe_field(step, frame, name, instances);
  }
  void field_blocks(const std::string &step, std::size_t frame,
                    const std::string &name, const std::string &instance,
                    const std::string &position,
                    const std::optional<SectionPoint> &section,
                    const BlockVisitor &visit) const override {
    inner_.field_blocks(step, frame, name, instance, position, section, visit);
  }
  void orientation_blocks(const std::string &step, std::size_t frame,
                          const std::vector<std::string> &instances,
                          const OrientationVisitor &visit) const override {
    inner_.orientation_blocks(step, frame, instances, visit);
  }
  std::vector<HistorySeries> history(const std::string &step) const override {
    if (state_->fail_history)
      throw SourceError("injected history failure");
    return inner_.history(step);
  }

private:
  std::shared_ptr<State> state_;
  InMemorySource inner_;
};
SourceFactory factory(const std::shared_ptr<State> &state) {
  return [state](const fs::path &) {
    return std::make_unique<TrackedSource>(state);
  };
}
std::vector<std::string> frames(const fs::path &file,
                                const std::string &suffix = "") {
  return {"--header", "0",      "--odbFile",  file.u8string(), "--instance",
          "Part-1",   "--step", "Step-1:0,1", "--suffix",      suffix};
}
void parsing(const fs::path &odb) {
  auto request = parse_request(frames(odb));
  check(request && request->mode == ExportMode::frames,
        "Default mode is not frames");
  check(request->outputs.format() == VtuFormat::ascii &&
            !request->outputs.write_pvd() && !request->write_history,
        "Incorrect CLI defaults");
  check(request->selection->steps()[0].frames ==
            std::vector<std::int64_t>({0, 1}),
        "Incorrect frame parsing");
  auto order = frames(odb);
  order[7] = "Step-2:0";
  order.insert(order.begin() + 8, "Step-1:1,0");
  request = parse_request(order);
  check(request->selection->steps()[0].name == "Step-2" &&
            request->selection->steps()[1].frames ==
                std::vector<std::int64_t>({1, 0}),
        "Step/frame order was sorted");
  request = parse_request({"--header=0", "--odbFile=" + odb.u8string(),
                           "--instance=Part-1", "--step=Phase:Step:00,01",
                           "--suffix=", "--format=binary"});
  check(request->selection->steps()[0].name == "Phase:Step" &&
            request->outputs.format() == VtuFormat::binary,
        "Equals syntax or last-colon parsing failed");
  auto state = std::make_shared<State>();
  std::ostringstream out, err;
  check(cli_main({"--help"}, factory(state), out, err) == 0 &&
            state->opens == 0,
        "Help initialized source");
  check(out.str().find("--format") != std::string::npos && err.str().empty(),
        "Incomplete help");
  const std::vector<std::vector<std::string>> invalid = {
      {},
      {"--header"},
      {"--header", "0"},
      {"--header", "0", "--odbFile"},
      {"--header", "2", "--odbFile", odb.u8string()},
      {"--header", "1", "--odbFile", odb.parent_path().u8string()},
      {"--header", "1", "--odbFile", odb.u8string(), "extra"},
      {"--header", "1", "--odbFile", odb.u8string(), "--unknown", "1"},
      {"--header", "1", "--odbFile", odb.u8string(), "--format", "compressed"},
      {"--header", "1", "--odbFile", odb.u8string(), "--writeHistory", "3"},
      {"--header", "1", "--odbFile", odb.u8string(), "--writePVD", "-1"},
      {"--header", "1", "--odbFile", odb.u8string(), "--header", "1"},
      {"--header", "0", "--odbFile", odb.u8string(), "--instance", "Part-1"},
      {"--header", "1", "--odbFile", odb.u8string(), "--suffix", "/bad"},
      {"--header", "1", "--odbFile", odb.u8string(), "--jobs", "2"},
  };
  for (const auto &args : invalid) {
    std::ostringstream output, errors;
    check(cli_main(args, factory(state), output, errors) == 2,
          "Invalid arguments did not return 2");
    check(state->opens == 0 && !errors.str().empty(),
          "Invalid arguments initialized source or lacked error");
  }
  for (const auto &token :
       {"S:", "S:0,", "S:,0", "S:0,,1", "S:0-1", "S:-1", "S:+1", "S:1.5",
        "S:1x", "S:0, 1", "S:9223372036854775808", "S:0,00", ":0"}) {
    auto args = frames(odb);
    args[7] = token;
    std::ostringstream output, errors;
    check(cli_main(args, factory(state), output, errors) == 2 &&
              state->opens == 0,
          "Invalid frame list initialized source");
  }
  auto duplicate = frames(odb);
  duplicate.insert(duplicate.begin() + 6, "Part-1");
  check(cli_main(duplicate, factory(state), out, err) == 2 && state->opens == 0,
        "Duplicate instance accepted");
  duplicate = frames(odb);
  duplicate.insert(duplicate.begin() + 8, "Step-1:1");
  check(cli_main(duplicate, factory(state), out, err) == 2 && state->opens == 0,
        "Duplicate step accepted");
}
void execution(const fs::path &odb) {
  auto state = std::make_shared<State>();
  auto args = frames(odb, "_ordered");
  args[7] = "Step-2:0";
  args.insert(args.begin() + 8, "Step-1:1,0");
  args.insert(args.end(), {"--format", "binary", "--writeHistory", "1"});
  const auto request = *parse_request(args);
  auto result = execute_request(request, factory(state));
  check(result.paths.size() == 4 && result.frames.size() == 3,
        "History/frame receipts incorrect");
  check(result.frames[0].frame.step == "Step-2" &&
            result.frames[1].frame.index == 1 &&
            result.frames[2].frame.index == 0,
        "Execution reordered request");
  check(state->closes == 1 && state->destroyed == 1 && state->meshes == 1,
        "Execution did not close/destroy source or reused mesh incorrectly");
  check(!fs::exists(request.outputs.collection_path()),
        "Default frame CLI wrote PVD");
  const auto before = read(result.frames[0].path);
  args.insert(args.end(), {"--writePVD", "1"});
  state = std::make_shared<State>();
  const auto collection = *parse_request(args);
  result = execute_request(collection, factory(state));
  check(result.frames.empty() && result.paths.size() == 2,
        "Collection mode converted frames or lost history");
  check(state->meshes == 0 && state->closes == 1 && state->destroyed == 1,
        "Collection mode read geometry or leaked source");
  check(read(collection.outputs.frame_path("Step-2", 0)) == before,
        "Collection mode rewrote existing frame");
  check(read(collection.outputs.collection_path()).find("Step-2_0.vtu") !=
            std::string::npos,
        "Collection lost selected order");
  state = std::make_shared<State>();
  std::ostringstream out, err;
  check(cli_main({"--header", "1", "--odbFile", odb.u8string(), "--step",
                  "invalid", "--writeHistory", "1", "--suffix", "_header"},
                 factory(state), out, err) == 0,
        "Header did not ignore data selection");
  check(state->closes == 1 && state->destroyed == 1 && state->meshes == 0,
        "Header source lifecycle incorrect");
  for (const auto &token : {"Step-1:2", "Missing:0"}) {
    state = std::make_shared<State>();
    args = frames(odb, "_invalid_selection");
    args[7] = token;
    check(cli_main(args, factory(state), out, err) == 2,
          "Unknown/out-of-range selection did not return 2");
    check(state->meshes == 0 && state->closes == 1 && state->destroyed == 1,
          "Selection validation read mesh or leaked source");
  }
  state = std::make_shared<State>();
  args = frames(odb, "_preflight");
  args.insert(args.end(), {"--writeHistory", "1"});
  const auto blocked = *parse_request(args);
  fs::create_directories(blocked.outputs.frame_path("Step-1", 1));
  check(cli_main(args, factory(state), out, err) == 1,
        "Output conflict did not return 1");
  check(!fs::exists(blocked.outputs.history_path()) && state->meshes == 0 &&
            state->closes == 1,
        "Preflight published history before discovering conflict");
  args = frames(odb, "_missing");
  args.insert(args.end(), {"--writePVD", "1", "--writeHistory", "1"});
  state = std::make_shared<State>();
  check(cli_main(args, factory(state), out, err) == 1 && state->meshes == 0,
        "Missing collection references accepted");
  check(!fs::exists(parse_request(args)->outputs.history_path()),
        "Missing collection preflight wrote history");
}
void failures(const fs::path &odb) {
  std::ostringstream out, err;
  const SourceFactory broken = [](const fs::path &) -> std::unique_ptr<Source> {
    throw SourceError("injected open failure");
  };
  check(cli_main(frames(odb, "_open"), broken, out, err) == 1,
        "Open failure did not return 1");
  auto args = frames(odb, "_partial");
  args.insert(args.end(), {"--writeHistory", "1"});
  auto state = std::make_shared<State>();
  state->bad_field = true;
  const auto request = *parse_request(args);
  put(request.outputs.frame_path("Step-1", 1), "old frame");
  try {
    execute_request(request, factory(state));
    throw std::runtime_error("Field failure ignored");
  } catch (const ExportFailure &error) {
    check(error.result().paths.size() == 2 && error.result().frames.size() == 1,
          "Lost prior history or frame on failure");
    check(error.result().paths[0] == request.outputs.history_path(),
          "History receipt order changed");
  }
  check(read(request.outputs.frame_path("Step-1", 1)) == "old frame" &&
            state->closes == 1 && state->destroyed == 1,
        "Failed execution damaged frame or leaked source");
  state = std::make_shared<State>();
  state->bad_field = true;
  check(cli_main(args, factory(state), out, err) == 1 &&
            err.str().find("Completed before failure:") != std::string::npos,
        "CLI omitted partial output report");
  state = std::make_shared<State>();
  state->fail_close = true;
  args = frames(odb, "_close");
  check(cli_main(args, factory(state), out, err) == 1 && state->destroyed == 1,
        "Close failure reported success or leaked source");
  check(err.str().find("injected close failure") != std::string::npos,
        "Close failure message lost");
  state = std::make_shared<State>();
  state->fail_close = true;
  state->bad_field = true;
  try {
    execute_request(*parse_request(frames(odb, "_both")), factory(state));
    throw std::runtime_error("Source failure ignored");
  } catch (const ExportFailure &error) {
    check(std::string(error.what()).find("close failure") == std::string::npos,
          "Cleanup replaced originating source failure");
    check(state->destroyed == 1, "Cleanup failure leaked source");
  }
  state = std::make_shared<State>();
  state->fail_history = true;
  args = frames(odb, "_history");
  args.insert(args.end(), {"--writeHistory", "1"});
  check(cli_main(args, factory(state), out, err) == 1 && state->meshes == 0 &&
            state->closes == 1,
        "History failure lifecycle incorrect");
  state = std::make_shared<State>();
  std::ostringstream bad_output;
  bad_output.setstate(std::ios::badbit);
  check(cli_main(frames(odb, "_progress"), factory(state), bad_output, err) ==
                1 &&
            state->closes == 1,
        "Progress failure did not close source");
}
} // namespace
int main() {
  const auto root = fs::temp_directory_path() /
                    ("odb2vtk-cli-" + std::to_string(std::random_device{}()));
  try {
    const auto odb = root / "with spaces" / "Job-1.odb";
    put(odb, "fake source fixture");
    parsing(odb);
    execution(odb);
    failures(odb);
    for (const auto &item : fs::recursive_directory_iterator(root))
      check(item.path().filename().u8string().find(".odb2vtk-") != 0,
            "Leaked CLI temporary file");
    fs::remove_all(root);
    std::cout << checks << " CLI/execution checks passed\n";
    return 0;
  } catch (const std::exception &error) {
    std::error_code ignored;
    fs::remove_all(root, ignored);
    std::cerr << error.what() << '\n';
    return 1;
  }
}
