#include "odb2vtk_core/converter.hpp"
#include "odb2vtk_core/conversion.hpp"
#include "odb2vtk_core/in_memory_source.hpp"
#include <cmath>
#include <iostream>
#include <limits>
#include <stdexcept>

using namespace odb2vtk_core;
namespace {
int checks=0;
void check(bool value,const char* message) { ++checks; if (!value) throw std::runtime_error(message); }
template<class Error,class F> void rejects(F function,const char* message) {
  ++checks;
  try { function(); } catch (const Error&) { return; }
  throw std::runtime_error(message);
}
InstanceMesh part(const std::string& name,double start=0) {
  return {name,{10,20},Matrix(2,3,{start,0,0,start+1,0,0}),{{7,{10,20},"B31"}}};
}
FieldBlock block(std::string instance,std::string position,std::vector<Label> labels,
    Matrix values,std::vector<std::int64_t> points={},std::optional<SectionPoint> section={}) {
  return {std::move(instance),std::move(position),std::move(labels),std::move(values),std::move(points),section};
}
InMemorySource sample(bool stress=true) {
  MemoryFrame frame{.5,{},{{"A",{7},Matrix(1,4,{0,0,0,1})}}};
  frame.fields.push_back({{"U",{"Vectors",{"U1","U2","U3"},"NODAL"},{},1},
      {block("A","NODAL",{20,10},Matrix(2,3,{20,21,22,10,11,12})),
       block("B","NODAL",{20,10},Matrix(2,3,{120,121,122,110,111,112}))}});
  frame.fields.push_back({{"TEMP",{"Scalars",{"0"},"NODAL"},{},1},
      {block("A","NODAL",{10,20},Matrix(2,1,{1,2})),block("B","NODAL",{10,20},Matrix(2,1,{101,102}))}});
  if (stress) {
    MemoryField s{{"S",{"Tensors",{"S11","S22"},"INTEGRATION_POINT"},{},1},{}};
    for (const auto& name : {std::string("A"),std::string("B")}) {
      const double base=name=="A" ? 0 : 100;
      for (int section=1; section<=2; ++section) {
        const SectionPoint point{section,section==1 ? "Top" : "Bottom"};
        const double offset=base+(section-1)*1000;
        s.blocks.push_back(block(name,"CENTROID",{7},Matrix(1,2,{90+offset,91+offset}),{},point));
        s.blocks.push_back(block(name,"INTEGRATION_POINT",{7,7},Matrix(2,2,{30+offset,31+offset,10+offset,11+offset}),{3,1},point));
      }
    }
    frame.fields.push_back(std::move(s));
  }
  MemoryFrame second=frame; second.time=1.5;
  for (auto& value : second.fields[0].blocks)
    for (std::size_t i=0;i<value.values.rows();++i)
      for (std::size_t c=0;c<value.values.columns();++c) value.values(i,c)+=1000;
  return InMemorySource({part("A"),part("B",100)},
    {{"Step-1",{frame,second},{{"same",{0,1},{1,2}},{"same",{.5},{4}}}},
     {"Step-2",{frame},{{"third",{0},{9}}}}});
}
struct Collector : FrameSink {
  std::vector<FrameInfo> frames;
  std::vector<MeshData> meshes;
  std::vector<std::vector<FieldArray>> arrays;
  std::size_t ended=0;
  void begin_frame(const FrameInfo& frame,const MeshData& mesh,const std::vector<FieldMetadata>& metadata) override {
    frames.push_back(frame);meshes.push_back(mesh);arrays.emplace_back();
    check(!metadata.empty(),"Missing frame metadata");
  }
  void field(const FieldArray& array) override { arrays.back().push_back(array); }
  void end_frame() override { ++ended; }
};
void selections() {
  rejects<SelectionError>([]{Selection({"A","A"},{{"S",{0}}});},"Duplicate instances accepted");
  rejects<SelectionError>([]{Selection({"A"},{{"S",{0,0}}});},"Duplicate frames accepted");
  rejects<SelectionError>([]{Selection({},{{"S",{-1}}});},"Negative frame accepted");
  rejects<SelectionError>([]{Selection({},{{"S",{}},{"S",{}}});},"Duplicate steps accepted");
  rejects<SelectionError>([]{Selection({},{});},"Missing steps accepted");
  std::vector<std::string> names{"B","A"};std::vector<StepSelection> steps{{"Z",{1,0}}};
  Selection selected(names,steps);names.clear();steps.clear();
  check(selected.instances()==std::vector<std::string>({"B","A"}),"Selection aliases input");
  check(selected.steps()[0].frames==std::vector<std::int64_t>({1,0}),"Frame order changed");
}
void geometry() {
  auto prepared=prepare_mesh({part("B",100),part("A")});
  check(prepared.geometry.connectivity==std::vector<std::int64_t>({0,1,2,3}),"Instance label namespaces overlap");
  check(prepared.geometry.points(0,0)==100 && prepared.geometry.points(2,0)==0,"Instance order changed");
  check(prepared.geometry.offsets==std::vector<std::int64_t>({2,4}),"Cell offsets incorrect");
  check(prepared.nodes.at("B").row(10)==0 && prepared.nodes.at("A").row(10)==2,"Wrong global indices");
  auto bad=part("A");bad.node_labels[1]=10;
  rejects<SourceError>([&]{prepare_mesh({bad});},"Duplicate nodes accepted");
  bad=part("A");bad.elements.push_back(bad.elements[0]);
  rejects<SourceError>([&]{prepare_mesh({bad});},"Duplicate elements accepted");
  bad=part("A");bad.elements[0].connectivity[0]=999;
  rejects<SourceError>([&]{prepare_mesh({bad});},"Unknown connectivity accepted");
  bad=part("A");bad.coordinates=Matrix(2,2);
  rejects<SourceError>([&]{prepare_mesh({bad});},"Invalid coordinate width accepted");
  rejects<SourceError>([]{prepare_mesh({part("A"),part("A")});},"Duplicate instance identity accepted");
  auto empty=prepare_mesh({{"empty",{},Matrix(0,3),{}}});
  check(empty.geometry.points.rows()==0 && empty.geometry.offsets.empty(),"Empty geometry failed");
  rejects<std::overflow_error>([]{Matrix(std::numeric_limits<std::size_t>::max(),2);},"Matrix product wrapped");
  rejects<SourceError>([]{Matrix(2,2,{1});},"Matrix storage mismatch accepted");
  rejects<std::out_of_range>([]{Matrix(2,2)(0,2)=1;},"Matrix column overflow accepted");
  Matrix original(1,2,{1,2});Matrix moved(std::move(original));
  check(original.rows()==0 && original.columns()==0 && original.values().empty(),"Moved-from matrix invariant broken");
  rejects<std::out_of_range>([&]{original(0,0)=3;},"Moved-from matrix index accepted");
  Matrix copied;copied=moved;copied(0,0)=9;
  check(moved(0,0)==1,"Matrix copy assignment aliases storage");
  bad=part("A");bad.elements[0].type="UNSUPPORTED";
  rejects<SourceError>([&]{prepare_mesh({bad});},"Unsupported element accepted");
}
void placement() {
  LabelLookup lookup;lookup.add(10,2);lookup.add(10000000,0);
  Matrix values(3,2);
  place_points(block("A","NODAL",{10,10000000,10},Matrix(3,2,{1,2,3,4,5,6})),lookup,values);
  check(values.values()==std::vector<double>({3,4,0,0,5,6}),"Repeated/sparse nodal placement incorrect");
  const auto before=values.values();
  rejects<SourceError>([&]{place_points(block("A","NODAL",{10,99},Matrix(2,2,{9,9,8,8})),lookup,values);},"Unknown label accepted");
  check(before==values.values(),"Missing label partially changed destination");
  Matrix ip(3,6);
  place_cells(block("A","INTEGRATION_POINT",{10,10000000,10,10000000},
      Matrix(4,2,{23,24,1,2,21,22,3,4}),{3,1,1,2}),lookup,ip);
  check(ip.values()==std::vector<double>({1,2,3,4,0,0,0,0,0,0,0,0,21,22,0,0,23,24}),"Global IP stride/padding incorrect");
  const auto initial=ip.values();
  rejects<SourceError>([&]{place_cells(block("A","INTEGRATION_POINT",{10,10000000},Matrix(2,2,{9,9,8,8}),{1,4}),lookup,ip);},"Out-of-range IP accepted");
  check(ip.values()==initial,"Invalid IP partially changed destination");
  rejects<SourceError>([&]{place_cells(block("A","INTEGRATION_POINT",{10},Matrix(1,2,{1,2})),lookup,ip);},"Missing IP IDs accepted");
  place_cells(block("A","INTEGRATION_POINT",{},Matrix(0,2)),lookup,ip);
  check(ip.values()==initial,"Empty IP block changed destination");
  const double q=std::sqrt(.5);
  const auto directions=quaternion_directions(Matrix(3,4,{0,0,0,0,0,0,0,1,0,0,q,q}));
  check(directions(0,0)==0 && directions(1,0)==1 && std::abs(directions(2,1)+1)<1e-14,"Quaternion/default directions incorrect");
}
void pipeline() {
  auto source=sample();
  const auto info=source.describe_field("Step-1",0,"S",{"B","A"});
  check(info.sections.size()==2 && info.max_integration_point==3,"Sections not deduplicated or maximum IP ID ignored");
  Collector sink;Converter converter(source);
  const auto result=converter.convert(Selection({"B","A"},{{"Step-1",{1,0}}}),sink);
  check(result.frames==2 && sink.ended==2,"Frame request incomplete");
  check(sink.frames[0].index==1 && sink.frames[1].index==0 && sink.frames[0].time==1.5,"Frame order/time incorrect");
  check(sink.arrays[0].size()==7 && sink.arrays[1].size()==7,"Unexpected field plan count");
  check(sink.arrays[1][0].values(0,0)==110 && sink.arrays[1][0].values(2,0)==10,"Per-instance point labels incorrect");
  check(sink.arrays[0][0].values(0,0)==1110,"Frame data reused incorrectly");
  check(sink.arrays[1][4].metadata.name=="S_IntegrationPointsTop","Field order/name incorrect");
  check(sink.arrays[1][4].values.values()==std::vector<double>({110,111,0,0,130,131,10,11,0,0,30,31}),"IP assembly does not match Python layout");
  check(sink.arrays[1].back().values.values()==std::vector<double>({0,0,0,1,0,0}),"Missing orientations not zero padded");
  check(!source.closed(),"Converter closed a borrowed source");
  Collector ordered;
  converter.convert(Selection({"A"},{{"Step-2",{0}},{"Step-1",{0}}}),ordered);
  check(ordered.frames[0].step=="Step-2" && ordered.frames[1].step=="Step-1","Step order changed");
  auto owned=source.mesh("A");owned.coordinates(0,0)=999;
  check(source.mesh("A").coordinates(0,0)==0,"Mesh snapshot aliases source");
  auto history=converter.history(Selection({},{{"Step-2",{}},{"Step-1",{}}}));
  check(history.headers==std::vector<std::string>({"third","same","same"}),"History columns/order overwritten");
  check(history.values.values()==std::vector<double>({9,1,4,0,2,0}),"History padding or sampling changed");
  source.close();source.close();
  check(owned.coordinates(0,0)==999 && history.values(0,0)==9,"Owned data invalid after closure");
  rejects<SourceError>([&]{source.instance_names();},"Closed source accepts queries");
  rejects<SourceError>([&]{converter.convert(Selection({"A"},{{"Step-1",{0}}}),sink);},"Closed source accepted by converter");
  auto no_stress=sample(false);Collector plain;
  Converter(no_stress).convert(Selection({"A"},{{"Step-1",{0}}}),plain);
  check(plain.arrays[0].size()==2,"Orientation emitted without stress");
}
void failures() {
  auto invalid=part("A");invalid.coordinates=Matrix(2,2);
  InMemorySource source({invalid},{{"S",{{0,{},{}}},{}}});Collector sink;Converter converter(source);
  rejects<SelectionError>([&]{converter.convert(Selection({"A"},{{"S",{9}}}),sink);},"Selection not validated before geometry");
  check(sink.frames.empty(),"Invalid request reached sink");
  rejects<SourceError>([&]{converter.convert(Selection({"A"},{{"S",{0}}}),sink);},"Malformed mesh accepted");
  check(sink.frames.empty(),"Invalid geometry reached sink");
  auto live=sample();
  struct Closer : FrameSink {
    Source& source;int fields=0;explicit Closer(Source& value):source(value){}
    void begin_frame(const FrameInfo&,const MeshData&,const std::vector<FieldMetadata>&) override {}
    void field(const FieldArray&) override { ++fields;source.close(); }
    void end_frame() override { throw std::runtime_error("Unexpected completion"); }
  } closer(live);
  rejects<SourceError>([&]{Converter(live).convert(Selection({"A"},{{"Step-1",{0}}}),closer);},"Fields eagerly read before sink consumption");
  check(closer.fields==1,"Field stream advanced after closure");
}
}
int main() {
  try { selections();geometry();placement();pipeline();failures(); }
  catch (const std::exception& error) { std::cerr << error.what() << '\n';return 1; }
  std::cout << checks << " numerical/source checks passed\n";
}
