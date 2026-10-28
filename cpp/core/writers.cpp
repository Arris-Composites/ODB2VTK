#include "odb2vtk_core/writers.hpp"
#include "profiling.hpp"
#include <algorithm>
#include <array>
#include <charconv>
#include <cmath>
#include <cstring>
#include <iomanip>
#include <limits>
#include <locale>
#include <ostream>
#include <sstream>

namespace odb2vtk_core {
namespace {
class Formatting {
public:
  explicit Formatting(std::ostream &out)
      : out_(out), flags_(out.flags()), precision_(out.precision()),
        locale_(out.getloc()) {
    out_.imbue(std::locale::classic());
    out_.flags(std::ios::dec | std::ios::skipws);
    out_ << std::setprecision(std::numeric_limits<double>::max_digits10);
  }
  ~Formatting() noexcept {
    try {
      out_.flags(flags_);
      out_.precision(precision_);
      out_.imbue(locale_);
    } catch (...) {
    }
  }

private:
  std::ostream &out_;
  std::ios::fmtflags flags_;
  std::streamsize precision_;
  std::locale locale_;
};
void checked(std::ostream &out) {
  if (!out)
    throw OutputError("Cannot write serialized output");
}
std::string attribute(const std::string &value) {
  std::string result;
  for (unsigned char c : value) {
    switch (c) {
    case '&':
      result += "&amp;";
      break;
    case '<':
      result += "&lt;";
      break;
    case '>':
      result += "&gt;";
      break;
    case '"':
      result += "&quot;";
      break;
    case '\r':
      result += "&#13;";
      break;
    case '\n':
      result += "&#10;";
      break;
    case '\t':
      result += "&#9;";
      break;
    default:
      if (c < 32)
        throw OutputError("Invalid XML control character");
      result += static_cast<char>(c);
    }
  }
  return result;
}
void json_string(std::ostream &out, const std::string &value) {
  static const char hex[] = "0123456789abcdef";
  out << '"';
  for (unsigned char c : value) {
    if (c == '"' || c == '\\')
      out << '\\' << static_cast<char>(c);
    else if (c < 32)
      out << "\\u00" << hex[c >> 4] << hex[c & 15];
    else
      out << static_cast<char>(c);
  }
  out << '"';
}
void csv_string(std::ostream &out, const std::string &value) {
  if (value.find_first_of(",\"\r\n") == std::string::npos) {
    out << value;
    return;
  }
  out << '"';
  for (char c : value) {
    if (c == '"')
      out << '"';
    out << c;
  }
  out << '"';
}
std::uint64_t byte_count(std::size_t rows, std::size_t width,
                         std::size_t item_size) {
  if (!width)
    throw OutputError("VTU arrays require at least one component");
  const auto count = detail::product(detail::product(rows, width), item_size);
  if (count > std::numeric_limits<std::uint64_t>::max())
    throw OutputError("Binary array size overflow");
  return static_cast<std::uint64_t>(count);
}
void little_endian(unsigned char *bytes, std::uint64_t bits, std::size_t size) {
  for (std::size_t i = 0; i < size; ++i)
    bytes[i] = static_cast<unsigned char>(bits >> (8 * i));
}
std::uint64_t bits(double value) {
  static_assert(sizeof(double) == 8 && std::numeric_limits<double>::is_iec559,
                "IEEE Float64 required");
  std::uint64_t result;
  std::memcpy(&result, &value, sizeof(result));
  return result;
}
std::uint64_t float_bits(double value) {
  static_assert(sizeof(float) == 4 && std::numeric_limits<float>::is_iec559,
                "IEEE Float32 required");
  const float converted =
      std::isfinite(value) &&
              std::abs(value) > std::numeric_limits<float>::max()
          ? (std::signbit(value) ? -std::numeric_limits<float>::infinity()
                                 : std::numeric_limits<float>::infinity())
          : static_cast<float>(value);
  std::uint32_t result;
  std::memcpy(&result, &converted, sizeof(result));
  return result;
}
template <class Values, class Encode>
void binary_array(std::ostream &out, const Values &values,
                  std::size_t item_size, Encode encode) {
  std::array<unsigned char, 64 * 1024> buffer{};
  const auto size = byte_count(values.size(), 1, item_size);
  little_endian(buffer.data(), size, 8);
  out.write(reinterpret_cast<const char *>(buffer.data()), 8);
  std::size_t used = 0;
  for (auto value : values) {
    little_endian(buffer.data() + used, encode(value), item_size);
    used += item_size;
    if (used == buffer.size()) {
      out.write(reinterpret_cast<const char *>(buffer.data()),
                static_cast<std::streamsize>(used));
      checked(out);
      used = 0;
    }
  }
  if (used)
    out.write(reinterpret_cast<const char *>(buffer.data()),
              static_cast<std::streamsize>(used));
  checked(out);
}
class AsciiChunk {
public:
  explicit AsciiChunk(std::ostream &out) : out_(out) {}
  void number(double value) {
    char text[128];
    const auto result = std::to_chars(
        text, text + sizeof(text), value, std::chars_format::general,
        std::numeric_limits<double>::max_digits10);
    append(text, result);
  }
  void number(std::int64_t value) {
    char text[32];
    append(text, std::to_chars(text, text + sizeof(text), value));
  }
  void separator(char value) {
    if (used_ == buffer_.size())
      flush();
    buffer_[used_++] = value;
  }
  void flush() {
    if (used_)
      out_.write(buffer_.data(), static_cast<std::streamsize>(used_));
    checked(out_);
    used_ = 0;
  }

private:
  void append(const char *begin, const std::to_chars_result &result) {
    if (result.ec != std::errc{})
      throw OutputError("Cannot format ASCII number");
    const auto length = static_cast<std::size_t>(result.ptr - begin);
    if (length > buffer_.size() - used_)
      flush();
    std::memcpy(buffer_.data() + used_, begin, length);
    used_ += length;
  }
  std::ostream &out_;
  std::array<char, 64 * 1024> buffer_{};
  std::size_t used_ = 0;
};
void ascii_matrix(std::ostream &out, const Matrix &matrix) {
  AsciiChunk chunk(out);
  std::size_t column = 0;
  for (auto value : matrix.values()) {
    chunk.number(value);
    if (++column == matrix.columns()) {
      chunk.separator('\n');
      column = 0;
    } else
      chunk.separator(' ');
  }
  chunk.flush();
}
bool same(const FieldMetadata &a, const FieldMetadata &b) {
  return a.name == b.name && a.association == b.association &&
         a.kind == b.kind && a.components == b.components && a.width == b.width;
}
void validate_mesh(const MeshData &mesh) {
  if (mesh.points.columns() != 3 ||
      mesh.offsets.size() != mesh.cell_types.size())
    throw OutputError("Invalid VTU mesh shape");
  std::int64_t previous = 0;
  for (auto offset : mesh.offsets) {
    if (offset < previous ||
        static_cast<std::uint64_t>(offset) > mesh.connectivity.size())
      throw OutputError("Invalid VTU cell offset");
    previous = offset;
  }
  if (static_cast<std::uint64_t>(previous) != mesh.connectivity.size())
    throw OutputError("VTU connectivity and offsets disagree");
  for (auto index : mesh.connectivity)
    if (index < 0 || static_cast<std::uint64_t>(index) >= mesh.points.rows())
      throw OutputError("Invalid VTU connectivity index");
}
} // namespace

struct VtuWriter::Impl {
  std::ostream &out;
  Formatting formatting;
  VtuFormat format;
  const MeshData *mesh = nullptr;
  std::vector<FieldMetadata> metadata;
  std::size_t next = 0;
  bool cell_data = false;
  std::uint64_t offset = 0;

  Impl(std::ostream &stream, VtuFormat encoding)
      : out(stream), formatting(stream), format(encoding) {
    if (format != VtuFormat::ascii && format != VtuFormat::binary)
      throw OutputError("Invalid VTU format");
  }
  bool binary() const { return format == VtuFormat::binary; }
  void array(const char *type, std::size_t rows, std::size_t width,
             std::size_t item_size, const std::string *name = nullptr,
             const std::vector<std::string> &components = {},
             bool matrix = true) {
    out << "<DataArray type=\"" << type << '"';
    if (name)
      out << " Name=\"" << attribute(*name) << '"';
    if (matrix)
      out << " NumberOfComponents=\"" << width << '"';
    for (std::size_t c = 0; c < components.size(); ++c)
      out << " ComponentName" << c << "=\"" << attribute(components[c]) << '"';
    if (binary()) {
      const auto size = byte_count(rows, width, item_size);
      if (size > std::numeric_limits<std::uint64_t>::max() - 8 ||
          offset > std::numeric_limits<std::uint64_t>::max() - 8 - size)
        throw OutputError("Binary appended offset overflow");
      out << " format=\"appended\" offset=\"" << offset << "\"/>\n";
      offset += 8 + size;
    } else
      out << " format=\"ascii\">\n";
  }
  void association(const std::string &name) {
    out << '<' << name;
    for (const auto &kind : {std::string("Tensors"), std::string("Vectors"),
                             std::string("Scalars")}) {
      const std::size_t width = kind == "Tensors"   ? 9
                                : kind == "Vectors" ? 3
                                                    : 1;
      for (const auto &field : metadata) {
        if (field.association == name && field.kind == kind &&
            field.width == width) {
          out << ' ' << kind << "=\"" << attribute(field.name) << '"';
          break;
        }
      }
    }
    out << ">\n";
  }
  void cells() {
    out << "<Cells>\n";
    const std::vector<std::int64_t> *arrays[] = {
        &mesh->connectivity, &mesh->offsets, &mesh->cell_types};
    const std::string names[] = {"connectivity", "offsets", "types"};
    for (std::size_t i = 0; i < 3; ++i) {
      array("Int64", arrays[i]->size(), 1, 8, &names[i], {}, false);
      if (!binary()) {
        AsciiChunk chunk(out);
        for (auto value : *arrays[i]) {
          chunk.number(value);
          chunk.separator('\n');
        }
        chunk.flush();
        out << "</DataArray>\n";
      }
    }
    out << "</Cells>\n";
  }
};

VtuWriter::VtuWriter(std::ostream &stream, VtuFormat format)
    : impl_(std::make_unique<Impl>(stream, format)) {}
VtuWriter::~VtuWriter() = default;
void VtuWriter::begin_frame(const FrameInfo &, const MeshData &mesh,
                            const std::vector<FieldMetadata> &metadata) {
  detail::PhaseScope timing(detail::Phase::vtu_serialization);
  auto &s = *impl_;
  if (s.mesh)
    throw OutputError("Previous VTU frame is incomplete");
  validate_mesh(mesh);
  bool cells = false;
  for (const auto &field : metadata) {
    if (field.association == "CellData")
      cells = true;
    else if (field.association != "PointData" || cells)
      throw OutputError("Invalid VTU field association order");
    if (!field.width ||
        (!field.components.empty() && field.components.size() != field.width))
      throw OutputError("Invalid VTU field width");
    attribute(field.name);
    for (const auto &label : field.components)
      attribute(label);
  }
  s.mesh = &mesh;
  s.metadata = metadata;
  s.next = 0;
  s.cell_data = false;
  s.offset = 0;
  s.out << "<VTKFile type=\"UnstructuredGrid\" version=\"1.0\" "
           "byte_order=\"LittleEndian\"";
  if (s.binary())
    s.out << " header_type=\"UInt64\"";
  s.out << ">\n<UnstructuredGrid>\n<Piece NumberOfPoints=\""
        << mesh.points.rows() << "\" NumberOfCells=\"" << mesh.offsets.size()
        << "\">\n<Points>\n";
  s.array("Float64", mesh.points.rows(), 3, 8);
  if (!s.binary()) {
    ascii_matrix(s.out, mesh.points);
    s.out << "</DataArray>\n";
  }
  s.out << "</Points>\n";
  if (s.binary()) {
    for (const auto &association :
         {std::string("PointData"), std::string("CellData")}) {
      s.association(association);
      const auto rows =
          association == "PointData" ? mesh.points.rows() : mesh.offsets.size();
      for (const auto &field : metadata)
        if (field.association == association)
          s.array("Float32", rows, field.width, 4, &field.name,
                  field.components);
      s.out << "</" << association << ">\n";
    }
    s.cells();
    s.out
        << "</Piece>\n</UnstructuredGrid>\n<AppendedData encoding=\"raw\">\n_";
    binary_array(s.out, mesh.points.values(), 8, bits);
  } else
    s.association("PointData");
  checked(s.out);
}
void VtuWriter::field(const FieldArray &field) {
  detail::PhaseScope timing(detail::Phase::vtu_serialization);
  auto &s = *impl_;
  if (!s.mesh || s.next >= s.metadata.size() ||
      !same(field.metadata, s.metadata[s.next]))
    throw OutputError("VTU field differs from declared metadata/order");
  const auto rows = field.metadata.association == "PointData"
                        ? s.mesh->points.rows()
                        : s.mesh->offsets.size();
  if (field.values.rows() != rows ||
      field.values.columns() != field.metadata.width)
    throw OutputError("VTU field differs from declared shape");
  if (s.binary())
    binary_array(s.out, field.values.values(), 4, float_bits);
  else {
    if (!s.cell_data && field.metadata.association == "CellData") {
      s.out << "</PointData>\n";
      s.association("CellData");
      s.cell_data = true;
    }
    s.array("Float32", rows, field.metadata.width, 4, &field.metadata.name,
            field.metadata.components);
    ascii_matrix(s.out, field.values);
    s.out << "</DataArray>\n";
  }
  ++s.next;
  checked(s.out);
}
void VtuWriter::end_frame() {
  detail::PhaseScope timing(detail::Phase::vtu_serialization);
  auto &s = *impl_;
  if (!s.mesh || s.next != s.metadata.size())
    throw OutputError("VTU frame has missing fields");
  if (s.binary()) {
    for (const auto *values :
         {&s.mesh->connectivity, &s.mesh->offsets, &s.mesh->cell_types})
      binary_array(s.out, *values, 8, [](std::int64_t value) {
        return static_cast<std::uint64_t>(value);
      });
    s.out << "\n</AppendedData>\n</VTKFile>";
  } else {
    if (!s.cell_data) {
      s.out << "</PointData>\n";
      s.association("CellData");
    }
    s.out << "</CellData>\n";
    s.cells();
    s.out << "</Piece>\n</UnstructuredGrid>\n</VTKFile>";
  }
  checked(s.out);
  s.mesh = nullptr;
  s.metadata.clear();
}

void write_header(std::ostream &out, const std::vector<std::string> &instances,
                  const std::vector<StepInfo> &steps) {
  Formatting formatting(out);
  out << "{\n    \"instances\": [";
  for (std::size_t i = 0; i < instances.size(); ++i) {
    if (i)
      out << ',';
    out << '\n' << "        ";
    json_string(out, instances[i]);
  }
  out << "\n    ],\n    \"steps\": [";
  for (std::size_t i = 0; i < steps.size(); ++i) {
    if (i)
      out << ',';
    const auto &step = steps[i];
    out << "\n        [";
    json_string(out, step.name);
    out << ", [";
    const auto width = std::to_string(step.frame_count).size();
    for (std::size_t frame = 0; frame < step.frame_count; ++frame) {
      if (frame)
        out << ", ";
      auto index = std::to_string(frame);
      json_string(out, step.name + "-frame-" +
                           std::string(width - index.size(), '0') + index);
    }
    out << "]]";
  }
  out << "\n    ]\n}";
  checked(out);
}
void write_history(std::ostream &out, const HistoryTable &table) {
  Formatting formatting(out);
  if (table.values.columns() != table.headers.size())
    throw OutputError("History shape and headers disagree");
  for (std::size_t i = 0; i < table.headers.size(); ++i) {
    if (i)
      out << ',';
    csv_string(out, table.headers[i]);
  }
  out << '\n' << std::fixed << std::setprecision(6);
  for (std::size_t row = 0; row < table.values.rows(); ++row) {
    for (std::size_t c = 0; c < table.values.columns(); ++c) {
      if (c)
        out << ',';
      out << table.values(row, c);
    }
    out << '\n';
    if (row % 4096 == 0)
      checked(out);
  }
  checked(out);
}
void write_collection(std::ostream &out,
                      const std::vector<CollectionEntry> &entries) {
  Formatting formatting(out);
  out << "<VTKFile type=\"Collection\" version=\"1.0\" "
         "byte_order=\"LittleEndian\" header_type=\"UInt64\">\n<Collection>\n";
  for (const auto &entry : entries) {
    if (!std::isfinite(entry.timestep))
      throw OutputError("Non-finite collection time");
    out << "<DataSet timestep=\"" << entry.timestep << "\" part=\""
        << entry.part << "\" file=\"" << attribute(entry.filename) << "\"/>\n";
  }
  out << "</Collection>\n</VTKFile>";
  checked(out);
}
} // namespace odb2vtk_core
