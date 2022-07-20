![[abaqusCAE 1.png|35]]![[U+2192.svg.png|50]]![[ParaView_Logo.png|45]]
# Abaqus output database to VTK converter

## Introduction

Abaqus output database (.odb extension) is a binary file native to Abaqus. To access the data from ODB file, without reverse engineering, is to use official Abaqus APIs which are provided in Python or C++. This project is a Python 
implementation to generate .vtu files for visualization in ParaView.

## Usage

ODB2VTK is a command line tool which uses Abaqus Python. So Abaqus must be installed to use this tool.
`abaqus python odb2vtk.py --header 1 --odbFile <my_odb_file_path>/my_odb_file.odb`
This will open the odb file, extract instances, steps, and frames, and save them into a JSON file in the same directory of the odb file.  
![[Pasted image 20220719182140.png]]
`abaqus python odb2vtk.py --header 0 --instance "Part-1" --step "Step-1:0,1" --odbFile <my_odb_file_path>/my_odb_file.odb`
With 0 passed to header, it will write vtu data for instance "Part-1" at "Step-1" with frame number 0 and 1.
`abaqus python odb2vtk.py --header 0 --instance "Part-1" "Part-2" --step "Step-1:0,1" "Step-2:0,1,2,3,4,5" "Step-3:0,1,2,3" --odbFile <my_odb_file_path>/my_odb_file.odb`
The above command will convert frame 0 to 1 in step 1, 0 to 5 in step 2, and 0 to 3 in step 3 for instance "Part-1" and "Part-2".
`python multiprocess.py --header 0 --instance "Part-1" "Part-2" --step "Step-1:1" "Step-3:2" --odbFile <my_odb_file_path>/my_odb_file.odb`
The above command utilizes multiprocessing in Python to spawn multiple abaqus python call in parallel. Another script `multiprocess.py` is provided for this purpose. It will split the frame in a one .vtu file per frame pattern and equivalent to the following three commands executed in parallel.
`abaqus python odb2vtk.py --header 0 --instance "Part-1" "Part-2" --step "Step-1:1" --odbFile <my_odb_file_path>/my_odb_file.odb`
`abaqus python odb2vtk.py --header 0 --instance "Part-1" "Part-2" --step "Step-3:2" --odbFile <my_odb_file_path>/my_odb_file.odb`
`abaqus python odb2vtk.py --header 0 --instance "Part-1" "Part-2" --step "Step-1:1" "Step-3:2" --odbFile <my_odb_file_path>/my_odb_file.odb --writePVD 1`
The last command will generate a .pvd file. 
Suppose the odb directory looks like this
```

project

│───Job-1.odb  

```
After `python multiprocess.py --header 0 --instance "Part-1" "Part-2" --step "Step-1:1" "Step-3:2" --odbFile ./Job-1.odb` has been executed, we will get
```

project

│───Job-1.odb  
└───Job-1
    │____Job-1.pvd
	│____Step-1_1.vtu
	│____Step-3_2.vtu

```

If you are converting different instances from the odb with the same step and frame, use '--suffix name' to append 'name' to the folder to avoid name clash. 

## Design

### Generality

Abaqus ODB file has the following tree structure[^1]. For generality, we want to give end-users the freedom to specify which instance, which step, and which frame in the step to be converted. It is not uncommon to have a large ODB file with many instances, steps and frames but we only want to extract a few of them. ODB2VTK can handle the output at integration points and section points (this will be addressed in detail in the following section). ODB2VTK is also designed to be extendable. New element can be easily added to the source code with only two lines of code.
![[Pasted image 20220719193323.png]]

### Performance

Performance will be an issue. The first principle is to avoid explicit for loop to traverse nodes and elements in Python, but to use vectorization. But data array has to be written line by line per node and cell into VTU file. Nevertheless, performance is not too bad.

On my machine (i7-8750H CPU@2.20GHz, 32GB ram), I converted a ~ 1GB .odb file which has C3D4 C3D8R C3D10 element types, 117972 elements, and 81959 nodes within less 3 minutes for 1 frame. Generality comes at a cost of performance. Converting multiple instances with different element types into one VTU file will be slower than converting them into separate VTU files. This is because VTK XML format requires the data array to have the same number of components. Suppose I have the first instance which has 8 integration points (6 * 8=48 components per element) and the second instance which has 1 integration point (6 * 1=6 components per element). When ODB2VTK writes stress output at integration points, the number of components is set to be the largest (48 in the case). Untouched data entry for elements from the second instance will be 0 and written to VTU. This chunk of data is redundant which inevitably increases file size as well as runtime. So if you have an odb file where integration points vary greatly, just convert each instance separately. 
 
Since VTK format can't divide geometry/topology (nodes and cells) and data (which will be visualized either per node or cell), performance will also deteriorate in the case of CFD/explicit solver which generates a large number of frames in the ODB file. Ideally, if all the frames share the same nodes and elements, it only needs to be written to disk once and shared by all the frames. But in the current implementation, each frame generates its corresponding VTU file which requests nodes and element data to be present. 

A niche solution will be HDF5 which is already supported by ParaView. Utilizing a HDF5 Python library allows us to directly converts data structures extracted from ODB (which are essentially numpy arrays) to HDF5 data structures at the speed close to C/C++ and avoid writing repetitive data.  But this requires the HDF5 library to be manually installed in the site-packages of Abaqus Python because everything must be run inside the python interpreter installed by Abaqus (e.g. Abaqus 2019 installed on my machine uses Python 2.7.3).  And the selected HDF5 library must be compatible in Abaqus Python. This will be put into future work.

### Responsibility

ODB2VTK should do nothing more than extract data in 'as-is' condition in the ODB file and write it to a VTU file. Any extra computation, especially the ones which perform at the element or node level if they can't be vectorized, will slow down the conversion process. So, the responsibility of ODB2VTK is just write data from ODB in 'as is' condition. Any post-processing operation is recommended to be placed in ParaView. For instance, applying a scale factor to displacement field to visualize the deformed shape can be easily achieved using 'wrap by vector' filter in ParaView.  

## Abaqus label to VTK index mapping

Abaqus ODB file uses different indexing system than VTK XML file. Each node and element in Abaqus has a label which is used to define their connectivity. A VTK XML file has index of nodes and elements starting from 0 whereas an ODB file has label starting from 1. Additionally, each instance in an ODB file has their own labeling for both nodes and elements which means two different instances can have identical labels for their own nodes and elements. Therefore, we need to have some kind of hashmap to map a label in an ODB file to an index in a VTK XML file. This is done via two private dictionaries in the ODB2VTK class:

self._nodes_map = {} 
self._elements_map = {}

self._nodes_map['instanceName'][label] gives us the index of the node with the label in instanceName instance.

self._elements_map['instanceName'][label] gives us the index of the element with the label in instanceName instance.

## Abaqus element to VTK cell

See [Linear Cells](https://raw.githubusercontent.com/Kitware/vtk-examples/gh-pages/src/Testing/Baseline/Cxx/GeometricObjects/TestLinearCellDemo.png) and [Isoparametric Cells](https://raw.githubusercontent.com/Kitware/vtk-examples/gh-pages/src/Testing/Baseline/Cxx/GeometricObjects/TestIsoparametricCellsDemo.png) as a reference to map Abaqus element to VTK cell. Abaqus python API provides a member variable 'type' in the element object, e.g., ele.type which returns a string like 'C3D10'. ODB2VTK is designed in such a way that we only need to create the map to convert abaqus element type to the enum value corresponding to the correct cell type in VTK. This is done in ABAQUS_VTK_CELL_MAP. If you want to add a new element type from Abaqus, all you have to do is to add a new elif condition to return the correct enum for VTK.

```
def ABAQUS_VTK_CELL_MAP(abaqusElementType):
	if 'C3D4' in abaqusElementType:
		return 10
	elif 'C3D6' in abaqusElementType:
		return 13
	elif 'C3D8' in abaqusElementType:
		return 12
	elif 'C3D10' in abaqusElementType:
		return 24
	elif 'C3D15' in abaqusElementType:
		return 26
	elif 'C3D20' in abaqusElementType:
		return 25
	elif 'S3' in abaqusElementType:
		return 5
	elif 'S4' in abaqusElementType:
		return 9
	elif 'S8' in abaqusElementType:
		return 23	
	elif 'S9' in abaqusElementType:
		return 28
	elif 'R3D3' in abaqusElementType:
		return 5
	elif 'R3D4' in abaqusElementType:
		return 9
	else:
		return None
```


## Integration points and section points

In VTK, data can be visualized either per cell or per node. For all the nodal output from Abaqus, we just create data array for each node. But things get tricky for element output as one element can have more than one data array. In particular, we need to address two properties: integration points and section points.

Elements with only one integration point don't cause any issue as it meets 'one data per element' pattern. But for the case of higher order elements which have more than one integration points, we usually have two options in terms of visualization in VTK: 1) get the weighted averaged value from all the integration points of the element and visualize it per element. 2) Extrapolate values at the nodal positions from the integration points and visualize it per node. The default contour plot in Abaqus uses the latter. For more reference, see Abaqus reference [here](https://abaqus-docs.mit.edu/2017/English/SIMACAECAERefMap/simacae-c-resconceptcompute.htm) and [here](https://abaqus-docs.mit.edu/2017/English/SIMACAECAERefMap/simacae-c-conconceptcompute.htm). We can use `getSubset(position=CNETROID)` to the get the weighted averaged value at the centroid of the element or use `getSubset(position=ELEMENT_NODAL)` to get the extrapolated values at the node. Unfortunately, the API `getSubset(position=ELEMENT_NODAL)` doesn't get the post-averaged values in Abaqus. So, we have to average it by ourselves. Moreover, Abaqus implements a threshold to instruct how a value at a nodal position is averaged over each adjacent element. This just makes it more complicated if we want to generate the same contour plot in Abaqus. While this logic is not difficult to implement in Python, I haven't yet found an efficient way to achieve this without using nested for loops. It must be noted that both approaches do not represent the actual state of the output. You must interpret it with discretion. A classic artifact from extrapolating values from integration points to nodal points and averaging is stress singularity due to the fact that shape functions are not guaranteed to be C$^1$ continuous from one element to its adjacent element. For this reason and also practicing the principle of "only extracts data in as-is condition", the current version of ODB2VTK class only writes output at integration points to centroid, which is very convenient since getSubset(position=CENTROID) directly gives us weighted averaged values per element. The data at integration points from FEA is like a raw data which can be post-processed for visualization. You can implement your own rules to visualize them using filters in ParaView in a much faster and easier way than in Abaqus Python. For instance, to generate a failure plot, we will use neither the weighted average stress/strain at the centroid nor extrapolated value at nodes, but use the stress/strain at integration points. In VTK XML, each element has a n component tensor data array where n = number of integration x 6. Once the .vtu file is opened in ParaView, we can create filters to access this data.

Another scenario when a element has more than one data array is that the element has multiple section points. This usually happens for reduced dimension elements such as shell elements. Section point is used to get output values at a different location in the thickness direction of the element. This is handled by ODB2VTK class. It will export as many section points as requested in the odb file. For instance, 'S4R' element by default has SPOS (stress state at the top surface) and SNEG (stress state at the bottom surface) for stress output. ODB2VTK will export all of them.

## Additional output

In ODB2VTK class, there is a method WriteLocalCS to write material orientation. This is just a custom output written into VTK. You can use the same pattern to write other custom output from ODB file.

## History output

ODB2VTK also extracts (using argument "--writeHistory 1") all the historyOutput in the odb file and write them into a CSV file which can be opened by ParaView to have a line chart view.

  

## Reference

[^1]:: [Abaqus Scripting Reference Manual](http://130.149.89.49:2080/v2016/books/ker/default.htm)