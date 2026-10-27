// Native integration probe; does not invoke the legacy exporter or write ODBs.
#include <cstdint>
#include <iostream>
#include <sstream>
#include <string>
#include <odb_API.h>

namespace {
class Runtime {
public:
  Runtime() { odb_initializeAPI(); }
  ~Runtime() noexcept { if (active_) { try { odb_finalizeAPI(); } catch (...) {} } }
  void finalize() { odb_finalizeAPI(); active_ = false; }
  Runtime(const Runtime&) = delete;
  Runtime& operator=(const Runtime&) = delete;
private:
  bool active_ = true;
};
class Database {
public:
  explicit Database(const char* path) : value_(&openOdb(odb_String(path), true)) {}
  ~Database() noexcept { if (value_) { try { value_->close(); } catch (...) {} } }
  Database(const Database&) = delete;
  Database& operator=(const Database&) = delete;
  odb_Odb& get() { return *value_; }
  void close() { value_->close(); value_ = nullptr; }
private:
  odb_Odb* value_;
};
std::string quote(const char* value) {
  std::ostringstream out; out << '"';
  for (const unsigned char c : std::string(value)) {
    if (c == '"' || c == '\\') out << '\\' << c;
    else if (c < 32) {
      const char* hex = "0123456789abcdef";
      out << "\\u00" << hex[c >> 4] << hex[c & 15];
    } else out << c;
  }
  return out.str() + '"';
}
}
int main(int argc, char** argv) {
  if (argc != 2) { std::cerr << "Usage: odb2vtk_sdk_smoke FILE.odb\n"; return 2; }
  try {
    std::ostringstream result;
    {
      Runtime runtime;
      Database database(argv[1]);
      {
        result << "{\"instances\":[";
        odb_InstanceRepositoryIT instances(database.get().rootAssembly().instances());
        bool first = true;
        for (instances.first(); !instances.isDone(); instances.next()) {
          if (!first) result << ',';
          first = false;
          result << quote(instances.currentKey().CStr());
        }
        result << "],\"steps\":[";
        odb_StepRepositoryIT steps(database.get().steps());
        first = true;
        for (steps.first(); !steps.isDone(); steps.next()) {
          if (!first) result << ',';
          first = false;
          result << "{\"name\":" << quote(steps.currentKey().CStr())
                 << ",\"frame_count\":" << steps.currentValue().frames().size() << '}';
        }
      }
      database.close();
      runtime.finalize();
    }
    result << "],\"closed\":true}";
    std::cout << result.str() << '\n'; return 0;
  } catch (odb_BaseException& error) { std::cerr << error.UserReport().CStr() << '\n'; }
  catch (const std::exception& error) { std::cerr << error.what() << '\n'; }
  catch (...) { std::cerr << "Unknown SDK failure\n"; }
  return 1;
}
