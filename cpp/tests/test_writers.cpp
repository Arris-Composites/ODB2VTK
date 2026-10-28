#include "odb2vtk_core/exporter.hpp"
#include "odb2vtk_core/in_memory_source.hpp"
#include <algorithm>
#include <cmath>
#include <cstring>
#include <fstream>
#include <iostream>
#include <limits>
#include <random>
#include <regex>
#include <sstream>
#ifdef _WIN32
#define NOMINMAX
#include <windows.h>
#endif

using namespace odb2vtk_core;
namespace fs = std::filesystem;
namespace {
int checks = 0;
void check(bool value, const char* message) {
  ++checks; if (!value) throw std::runtime_error(message);
}
template<class Error, class F> void rejects(F function, const char* message) {
  ++checks;
  try { function(); } catch (const Error&) { return; }
  throw std::runtime_error(message);
}
std::string read(const fs::path& path) {
  std::ifstream input(path, std::ios::binary);
  return {std::istreambuf_iterator<char>(input), std::istreambuf_iterator<char>()};
}
void put(const fs::path& path, const std::string& value) {
  fs::create_directories(path.parent_path());
  std::ofstream(path, std::ios::binary) << value;
}
std::uint64_t little(const std::string& value, std::size_t start, std::size_t size) {
  check(start + size <= value.size(), "Truncated binary block");
  std::uint64_t result = 0;
  for (std::size_t i = 0; i < size; ++i)
    result |= static_cast<std::uint64_t>(static_cast<unsigned char>(value[start+i])) << (i*8);
  return result;
}
MeshData mesh() { return {Matrix(2,3,{.125,0,0,1.1234567890123457,0,0}), {0,1}, {2}, {3}}; }
void encodings() {
  const auto geometry = mesh();
  const FieldMetadata scalar{"T&\"\n", "PointData", "Scalars", {"x<\t"}, 1};
  const FieldMetadata tensor{"six", "CellData", "Tensors", {}, 6};
  const FieldMetadata vector{"axis", "CellData", "Vectors", {}, 3};
  for (auto format : {VtuFormat::ascii, VtuFormat::binary}) {
    std::ostringstream stream;
    VtuWriter writer(stream, format);
    writer.begin_frame({"Step",0,.5}, geometry, {scalar,tensor,vector});
    writer.field({scalar, Matrix(2,1,{-1.5,1.2345678901234567})});
    writer.field({tensor, Matrix(1,6)});
    writer.field({vector, Matrix(1,3,{1,0,0})});
    writer.end_frame();
    const auto text = stream.str();
    check(text.find("Scalars=\"T&amp;&quot;&#10;\"") != std::string::npos, "Unescaped active scalar");
    check(text.find("Vectors=\"axis\"") != std::string::npos, "Missing active vector");
    check(text.find("Tensors=") == std::string::npos, "Six-component tensor must not be active");
    check(text.find("x&lt;&#9;") != std::string::npos, "Unescaped component label");
    if (format == VtuFormat::ascii) {
      check(text.find("1.1234567890123457") != std::string::npos, "Coordinate precision lost");
      check(text.find("1.2345678901234567") != std::string::npos, "Field precision lost before reader rounding");
    } else {
      const auto start = text.find("\n_") + 2;
      const auto xml = text.substr(0, start);
      std::regex offsets("offset=\"([0-9]+)\"");
      const std::uint64_t lengths[] = {48,8,24,12,16,8,8};
      std::uint64_t expected = 0;
      std::size_t count = 0;
      for (auto i = std::sregex_iterator(xml.begin(), xml.end(), offsets); i != std::sregex_iterator(); ++i) {
        check(count < 7, "Extra binary array");
        const auto offset = std::stoull((*i)[1]);
        check(offset == expected, "Incorrect binary offset");
        check(little(text,start+offset,8) == lengths[count], "Incorrect UInt64 binary length");
        expected += 8 + lengths[count++];
      }
      check(count == 7, "Missing binary arrays");
      check(little(text,start+8,8) == 0x3fc0000000000000ULL, "Float64 is not little endian");
      check(little(text,start+56+8,4) == 0xbfc00000ULL, "Float32 is not little endian");
      check(text.substr(start+expected) == "\n</AppendedData>\n</VTKFile>", "Binary payload has extra/missing bytes");
    }
    rejects<OutputError>([&] { writer.end_frame(); }, "Accepted duplicate frame end");
  }
  std::ostringstream stream;
  VtuWriter writer(stream, VtuFormat::binary);
  const MeshData empty{Matrix(0,3),{},{},{}};
  writer.begin_frame({"Step",0,0},empty,{}); writer.end_frame();
  const auto bytes = stream.str();
  const auto start = bytes.find("\n_")+2;
  for (int i = 0; i < 4; ++i) check(little(bytes,start+8*i,8) == 0, "Empty binary array lacks zero length");
  std::ostringstream missing;
  VtuWriter incomplete(missing);
  incomplete.begin_frame({"Step",0,0},geometry,{scalar});
  rejects<OutputError>([&] { incomplete.end_frame(); }, "Accepted missing field");
  rejects<OutputError>([&] { incomplete.field({scalar,Matrix(1,1)}); }, "Accepted wrong field row count");
  auto changed = scalar; changed.components={"changed"};
  rejects<OutputError>([&] { incomplete.field({changed,Matrix(2,1)}); }, "Accepted changed field metadata");
  std::ostringstream header, csv, pvd;
  write_header(header,{"a\"\\\n"},{{"S",10}});
  check(header.str().find("a\\\"\\\\\\u000a") != std::string::npos, "Invalid JSON escaping");
  check(header.str().find("S-frame-09") != std::string::npos, "Incorrect header frame padding");
  write_history(csv,{{"a,b","q\"\n"},Matrix(1,2,{1.25,-2})});
  check(csv.str() == "\"a,b\",\"q\"\"\n\"\n1.250000,-2.000000\n", "Incorrect CSV escaping or precision");
  write_collection(pvd,{{.125,0,"S&x_0.vtu"}});
  check(pvd.str().find("timestep=\"0.125\" part=\"0\" file=\"S&amp;x_0.vtu\"") != std::string::npos, "Incorrect collection schema");
  std::ostringstream formatted;
  formatted << std::hex << std::showpos << std::uppercase;
  const auto original_flags=formatted.flags();
  write_collection(formatted,{{.125,15,"S.vtu"}});
  check(formatted.str().find("timestep=\"0.125\" part=\"15\"")!=std::string::npos,"Caller formatting corrupted output");
  check(formatted.flags()==original_flags,"Writer changed caller formatting");
}
struct CountBuffer : std::stringbuf {
  std::streamsize maximum = 0;
  std::streamsize xsputn(const char* value, std::streamsize count) override {
    maximum = std::max(maximum,count);
    return std::stringbuf::xsputn(value,count);
  }
};
void bounded_binary() {
  for (auto format : {VtuFormat::ascii,VtuFormat::binary}) {
    CountBuffer buffer; std::ostream stream(&buffer);
    const MeshData geometry{Matrix(40000,3),{},{},{}};
    const FieldMetadata meta{"v","PointData","Vectors",{},3};
    VtuWriter writer(stream,format);
    writer.begin_frame({"Step",0,0},geometry,{meta});
    writer.field({meta,Matrix(40000,3)}); writer.end_frame();
    check(buffer.maximum <= 64*1024, "Numerical writer made an unbounded write");
  }
}
InMemorySource sample(bool bad_second = false) {
  const InstanceMesh part{"A",{10,20},mesh().points,{{7,{10,20},"B31"}}};
  MemoryField field{{"T",{"Scalars",{"T"},"NODAL"},{},1},
      {{"A","NODAL",{10,20},Matrix(2,1,{1,2}),{},std::nullopt}}};
  MemoryFrame first{.25,{field},{}};
  MemoryFrame second=first; second.time=.75;
  if (bad_second) second.fields[0].blocks[0].labels[1]=999;
  return InMemorySource({part},{{"S",{first,second},{{"history",{0,1},{1.25,2.5}}}}});
}
void no_temporary(const fs::path& directory) {
  for (const auto& item : fs::recursive_directory_iterator(directory))
    check(item.path().filename().u8string().find(".odb2vtk-") != 0, "Leaked temporary output");
}
void publication(const fs::path& root) {
  const auto path = root/"old.txt"; put(path,"previous");
  rejects<std::runtime_error>([&] {
    atomic_output(path,[](std::ostream& out) { out << "partial"; throw std::runtime_error("injected serialization failure"); });
  },"Serialization failure was lost");
  check(read(path)=="previous","Serialization failure replaced destination");
  rejects<std::ios_base::failure>([&] {
    atomic_output(path,[](std::ostream& out) { out << "partial"; out.setstate(std::ios::badbit); });
  },"Stream failure was lost");
  check(read(path)=="previous","Stream failure replaced destination");
  rejects<OutputError>([&] {
    atomic_output(path,[](std::ostream& out) {
      const auto geometry=mesh();
      const FieldMetadata metadata{"T","PointData","Scalars",{},1};
      VtuWriter writer(out,VtuFormat::binary);
      writer.begin_frame({"S",0,0},geometry,{metadata});
      writer.field({metadata,Matrix(1,1)});
    });
  },"Writer validation failure was lost");
  check(read(path)=="previous","Writer validation failure replaced destination");
#ifdef _WIN32
  HANDLE lock=CreateFileW(path.c_str(),GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
  check(lock!=INVALID_HANDLE_VALUE,"Cannot lock publication destination");
  bool rejected=false;
  try { atomic_output(path,[](std::ostream& out) { out << "replacement"; }); }
  catch (const OutputError&) { rejected=true; }
  CloseHandle(lock);
  check(rejected,"Locked destination replacement succeeded");
  check(read(path)=="previous","Failed replacement damaged previous file");
#endif
  atomic_output(path,[](std::ostream& out) { out << "complete"; });
  check(read(path)=="complete","Successful replacement failed");
  rejects<OutputError>([&] { OutputOptions(root,"CON"); },"Accepted device filename");
  rejects<OutputError>([&] { OutputOptions(root,"run").frame_path("../S",0); },"Accepted output traversal");
  rejects<OutputError>([&] { validate_destinations({path,path}); },"Accepted colliding outputs");
  const auto named=OutputOptions::from_odb(root/"a.b.odb","_x");
  check(named.run_name()=="a_x","Changed Python first-dot naming policy");
  no_temporary(root);
}
void exports(const fs::path& root) {
  const Selection selection({"A"},{{"S",{0,1}}});
  for (auto format : {VtuFormat::ascii,VtuFormat::binary}) {
    auto source=sample();
    const OutputOptions options(root,format==VtuFormat::ascii ? "ascii" : "binary","",true,format);
    const Exporter exporter(source);
    const auto result=exporter.export_frames(selection,options);
    check(result.frames.size()==2 && result.paths.size()==3,"Incorrect completion receipts");
    exporter.export_header(options); exporter.export_history(selection,options);
    check(fs::is_regular_file(options.header_path()) && fs::is_regular_file(options.history_path()),"Missing auxiliary outputs");
    const auto before=read(options.collection_path());
    exporter.export_collection(selection,options);
    check(read(options.collection_path())==before,"Collection-only changed schema/order");
    check(!source.closed(),"Exporter closed borrowed source");
  }
  const OutputOptions failed_options(root,"source-failure");
  put(failed_options.frame_path("S",1),"old frame");
  put(failed_options.collection_path(),"old collection");
  auto broken=sample(true);
  try {
    Exporter(broken).export_frames(selection,failed_options);
    throw std::runtime_error("Source failure ignored");
  } catch (const ExportFailure& error) {
    check(error.result().frames.size()==1 && error.result().paths.size()==1,"Lost completed frame on source failure");
    check(error.cause()!=nullptr,"Lost failure cause");
  }
  check(read(failed_options.frame_path("S",1))=="old frame","Source failure replaced previous frame");
  check(read(failed_options.collection_path())=="old collection","Source failure replaced collection");
  const OutputOptions progress_options(root,"progress-failure");
  put(progress_options.collection_path(),"old collection");
  auto source=sample();
  try {
    Exporter(source,[](const ProgressEvent&) { throw std::runtime_error("injected progress failure"); }).export_frames(selection,progress_options);
    throw std::runtime_error("Progress failure ignored");
  } catch (const ExportFailure& error) {
    check(error.result().frames.size()==1 && fs::is_regular_file(error.result().frames[0].path),"Progress failure lost published receipt");
  }
  check(read(progress_options.collection_path())=="old collection","Progress failure replaced collection");
  rejects<OutputError>([&] { Exporter(source).export_collection(selection,progress_options); },"Collection accepted missing VTU");
#ifdef _WIN32
  const OutputOptions collection_options(root,"collection-failure");
  put(collection_options.collection_path(),"old collection");
  HANDLE lock=CreateFileW(collection_options.collection_path().c_str(),GENERIC_READ,FILE_SHARE_READ,
                         nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
  check(lock!=INVALID_HANDLE_VALUE,"Cannot lock collection destination");
  bool publication_failed=false;
  try { Exporter(source).export_frames(selection,collection_options); }
  catch (const ExportFailure& error) {
    publication_failed=true;
    check(error.result().frames.size()==2 && error.result().paths.size()==2,"Collection failure lost frame receipts");
  }
  CloseHandle(lock);
  check(publication_failed,"Locked collection replacement succeeded");
  check(read(collection_options.collection_path())=="old collection","Collection failure damaged existing collection");
#endif
  no_temporary(root);
}
}
int main() {
  const auto root=fs::temp_directory_path()/("odb2vtk-writers-"+std::to_string(std::random_device{}()));
  try {
    fs::create_directories(root);
    encodings(); bounded_binary(); publication(root); exports(root);
    fs::remove_all(root);
    std::cout << checks << " writer/publication checks passed\n";
    return 0;
  } catch (const std::exception& error) {
    std::error_code ignored; fs::remove_all(root,ignored);
    std::cerr << error.what() << '\n'; return 1;
  }
}
