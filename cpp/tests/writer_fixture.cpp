#include "odb2vtk_core/outputs.hpp"
#include <cmath>
#include <iostream>
#include <limits>

using namespace odb2vtk_core;
int main(int argc, char **argv) {
  if (argc != 2)
    return 2;
  try {
    const auto directory = std::filesystem::absolute(argv[1]);
    const std::string name = u8"values & \"\n\t\r\u03bc";
    const FieldMetadata field{
        name, "PointData", "Scalars", {u8"component <\u03bc>"}, 1};
    const MeshData mesh{Matrix(8, 3,
                               {.12345678901234567,
                                0,
                                0,
                                1,
                                0,
                                0,
                                2,
                                0,
                                0,
                                3,
                                0,
                                0,
                                4,
                                0,
                                0,
                                5,
                                0,
                                0,
                                6,
                                0,
                                0,
                                7,
                                0,
                                0}),
                        {0, 1, 2, 3, 4, 5, 6, 7},
                        {1, 2, 3, 4, 5, 6, 7, 8},
                        {1, 1, 1, 1, 1, 1, 1, 1}};
    const Matrix values(8, 1,
                        {std::numeric_limits<double>::quiet_NaN(),
                         std::numeric_limits<double>::infinity(),
                         -std::numeric_limits<double>::infinity(), -0.0,
                         1.0 + std::ldexp(1.0, -24),
                         1.0 + 3 * std::ldexp(1.0, -24),
                         std::numeric_limits<float>::denorm_min(),
                         std::numeric_limits<float>::max()});
    for (auto format : {VtuFormat::ascii, VtuFormat::binary}) {
      const auto suffix = format == VtuFormat::ascii ? "ascii" : "binary";
      atomic_output(directory / (std::string("special-") + suffix + ".vtu"),
                    [&](std::ostream &out) {
                      VtuWriter writer(out, format);
                      writer.begin_frame({"S", 0, 0}, mesh, {field});
                      writer.field({field, values});
                      writer.end_frame();
                    });
      atomic_output(directory / (std::string("empty-") + suffix + ".vtu"),
                    [&](std::ostream &out) {
                      const MeshData empty{Matrix(0, 3), {}, {}, {}};
                      VtuWriter writer(out, format);
                      writer.begin_frame({"S", 0, 0}, empty, {field});
                      writer.field({field, Matrix(0, 1)});
                      writer.end_frame();
                    });
    }
    atomic_output(directory / "escaped.json", [&](std::ostream &out) {
      write_header(out, {name}, {{name, 10}});
    });
    atomic_output(directory / "escaped.csv", [&](std::ostream &out) {
      write_history(out, {{name}, Matrix(1, 1, {1.25})});
    });
    atomic_output(directory / "escaped.pvd", [&](std::ostream &out) {
      write_collection(out, {{.125, 0, name + ".vtu"}});
    });
    return 0;
  } catch (const std::exception &error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
