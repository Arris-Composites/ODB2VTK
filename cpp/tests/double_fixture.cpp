// Validation-only creator: always copy the input and refuse to overwrite output.
#include <cstdint>
#include <filesystem>
#include <iostream>
#include <odb_API.h>

int main(int argc,char** argv) {
  if (argc!=3) { std::cerr << "Usage: odb2vtk_double_fixture SOURCE OUTPUT\n";return 2; }
  bool initialized=false;odb_Odb* db=nullptr;
  try {
    std::filesystem::copy_file(argv[1],argv[2]);
    odb_initializeAPI();initialized=true;
    db=&openOdb(odb_String(argv[2]),false);
    {
      odb_InstanceRepositoryIT instances(db->rootAssembly().instances());instances.first();
      if (instances.isDone()) throw std::runtime_error("Fixture needs an instance");
      const auto& instance=instances.currentValue();
      const auto nodes=instance.nodes();
      if (nodes.size()<2) throw std::runtime_error("Fixture needs two nodes");
      odb_StepRepositoryIT steps(db->steps());steps.first();
      if (steps.isDone() || !steps.currentValue().frames().size()) throw std::runtime_error("Fixture needs a frame");
      auto& frame=db->steps()[steps.currentKey()].frames()[0];
      odb_SequenceString components;components.append("D1");components.append("D2");components.append("D3");
      auto& field=frame.FieldOutput("DOUBLE_TEST","Double precision fixture",odb_Enum::VECTOR,components);
      odb_SequenceInt labels;labels.append(nodes[0].label());labels.append(nodes[1].label());
      odb_SequenceSequenceDouble values;
      for (int i=0;i<2;++i) {
        odb_SequenceDouble row;
        row.append((i ? -1 : 1)*1.2345678901234567);
        row.append((i ? -1 : 1)*2.3456789012345678);
        row.append((i ? -1 : 1)*3.4567890123456789);
        values.append(row);
      }
      field.addData(odb_Enum::NODAL,instance,labels,values);
      db->save();
    }
    db->close();db=nullptr;odb_finalizeAPI();initialized=false;
    std::cout << "Created double-precision fixture\n";return 0;
  } catch (odb_BaseException& error) { std::cerr << error.UserReport().CStr() << '\n'; }
  catch (const std::exception& error) { std::cerr << error.what() << '\n'; }
  if (db) { try { db->close(); } catch (...) {} }
  if (initialized) { try { odb_finalizeAPI(); } catch (...) {} }
  return 1;
}
