![abaqusCAE](res/abaqusCAE.png)![U+2192.svg](res/U+2192.svg.png)![ParaView_Logo](res/ParaView_Logo.png)

# Abaqus output database to VTK converter

## Introduction

Abaqus output database (.odb extension) is a binary file native to Abaqus. To access the data from ODB file, without reverse engineering, is to use official Abaqus APIs which are provided in Python or C++. This project is a Python
implementation to generate .vtu files for visualization in ParaView. This work is inspired by [Liujie](https://github.com/Liujie-SYSU/odb2vtk). And all other similar work doesn't satisfy my needs since I need a converter which is more general and extensible. So I ended up implement my own version of it. This converter will:

1. Convert all the field outputs which exist in the ODB file.
2. Convert data at integrations points / section points and material orientation.
3. Map Abaqus element to VTK cell at your will.

## Usage Python

![](res/odb2vtk_tutorial.gif)
ODB2VTK is a command line tool which uses Abaqus Python. So Abaqus must be installed to use this tool.

`abaqus python odb2vtk.py --header 1 --odbFile <my_odb_file_path>/my_odb_file.odb`

This will open the odb file, extract instances, steps, and frames, and save them into a JSON file in the same directory of the odb file.

![json_header](res/json_header.png)

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

## Usage C++

To successully compile the C++ project using Abaqus public APIs, we need to do the following things in Visual Studio:

1. Add the include directories
   On my machine, they are:
   C:\Program Files\Dassault Systemes\SimulationServices\V6R2019x\win_b64\code\include
   C:\Program Files\Dassault Systemes\SimulationServices\V6R2019x
2. Add the linker lib directories:
   C:\Program Files\Dassault Systemes\SimulationServices\V6R2019x\win_b64\code\lib
3. Add static libs
4. Add runtime DLL directory to PATH
   C:\Program Files\Dassault Systemes\SimulationServices\V6R2019x\win_b64\code\bin
