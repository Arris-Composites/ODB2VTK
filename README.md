![abaqusCAE](res/abaqusCAE.png)![U+2192.svg](res/U+2192.svg.png)![ParaView_Logo](res/ParaView_Logo.png)

# Abaqus output database to VTK converter

## Introduction

Abaqus output database (.odb extension) is a binary file native to Abaqus. To access the data from ODB file, without reverse engineering, is to use official Abaqus APIs which are provided in Python or C++. This project provides a converter implemented in Python and C++. The C++ version is considerably faster than the Python version but it needs proper configuration to successfully build from the source. This work is inspired by [Liujie](https://github.com/Liujie-SYSU/odb2vtk). And all other similar work doesn't satisfy my needs since I need a converter which is more general and extensible. So I ended up implement my own version of it. This converter will:

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

## Build C++ Project by Visual Studio

Cpp folder has the source code for the C++ implemnetation.
To successully compile the C++ project using Abaqus public APIs, we need to do the following things in Visual Studio (This may look different on your machine depending on where Abaqus is installed, but I will list my directories as an example.):

1. Add the include directories
   ```
   C:\Program Files\Dassault Systemes\SimulationServices\V6R2019x\win_b64\code\include
   C:\Program Files\Dassault Systemes\SimulationServices\V6R2019x
   ```
2. Add the linker lib directories:
   ```
   C:\Program Files\Dassault Systemes\SimulationServices\V6R2019x\win_b64\code\lib
   ```
3. Add static libs

   I simply copied all libs

   ```
   ABQDMP_Core.lib
   ABQSMAAbuBasicUtils.lib
   ABQSMAAbuGeom.lib
   ABQSMAAspCommunications.lib
   ABQSMAAspDiagExtractor.lib
   ABQSMAAspExpKernelComm.lib
   ABQSMAAspSupport.lib
   ABQSMABasAlloc.lib
   ABQSMABasCoreUtils.lib
   ABQSMABasGenericsLib.lib
   ABQSMABasPrfTrkLib.lib
   ABQSMABasRtvUtility.lib
   ABQSMABasShared.lib
   ABQSMABasXmlDocument.lib
   ABQSMABasXmlParser.lib
   ABQSMABlaModule.lib
   ABQSMACseModules.lib
   ABQSMAEliBaseModule.lib
   ABQSMAEliLicenseModule.lib
   ABQSMAEliStaticModule.lib
   ABQSMAElkCore.lib
   ABQSMAFeoModules.lib
   ABQSMAFsmShared.lib
   ABQSMAISimInterface.lib
   ABQSMAISrvInterface.lib
   ABQSMAMsgCommModules.lib
   ABQSMAMsgModules.lib
   ABQSMAMtkApiMod.lib
   ABQSMAMtxCoreModule.lib
   ABQSMAObjSimObjectsMod.lib
   ABQSMAOdbApi.lib
   ABQSMAOdbAttrEO.lib
   ABQSMAOdbCalcK.lib
   ABQSMAOdbCore.lib
   ABQSMAOdbCoreGeom.lib
   ABQSMAOdbDdbOdb.lib
   ABQSMARfmInterface.lib
   ABQSMARomDiagEx.lib
   ABQSMASglSharedLib.lib
   ABQSMASglSimXmlFndLib.lib
   ABQSMAShaDbIface-D.lib
   ABQSMAShaDbIface.lib
   ABQSMAShaShared-D.lib
   ABQSMAShaShared.lib
   ABQSMAShpCore.lib
   ABQSMASimBCompress.lib
   ABQSMASimBulkAPI.lib
   ABQSMASimContainers.lib
   ABQSMASimInterface.lib
   ABQSMASimManifestSubcomp.lib
   ABQSMASimPoolManager.lib
   ABQSMASimS2fSubcomp.lib
   ABQSMASimSerializerAPI.lib
   ABQSMASrvBasic.lib
   ABQSMASrvSimXmlConverters.lib
   ABQSMASspUmaCore.lib
   ABQSMAUsubsLib.lib
   ABQSMAUzlZlib.lib
   CATBBMagic.lib
   CATComBase.lib
   CATComDrvBB.lib
   CATComHTTPEndPoint.lib
   CATComServices.lib
   CATComSidl.lib
   CATComSidlFile.lib
   CATLic.lib
   CATLMjni.lib
   CATP2PBaseUUID.lib
   CATP2PCore.lib
   CATPLMDispatcherItf.lib
   CATPLMDispatcherSpecificItf.lib
   CATScriptEngine.lib
   CATSysAllocator.lib
   CATSysCATIAAI.lib
   CATSysCommunication.lib
   CATSysDbSettings.lib
   CATSysExternApp.lib
   CATSysMainThreadMQ.lib
   CATSysMotifDrv.lib
   CATSysMultiThreading.lib
   CATSysPreview.lib
   CATSysProxy.lib
   CATSysRunBrw.lib
   CATSysTS.lib
   CATSysTSObjectModeler.lib
   CommunicationsUUID.lib
   CSICommandBinder.lib
   CSINodesLauncherSrc.lib
   CSIQueuingDatabaseModule.lib
   CSIQueuingModule.lib
   CSIUtilities.lib
   DSYApplicationMainArch.lib
   DSYSysCnxExit.lib
   DSYSysDlg.lib
   DSYSysIRMSysAdapter.lib
   DSYSysProgressHandler.lib
   DSYSysWebService.lib
   DSYSysWMIDriver.lib
   EKCrypto.lib
   EKPrivateArchive.lib
   EKSSL.lib
   ExperienceKernel.lib
   explicitB-D.lib
   explicitB.lib
   explicitU-D.lib
   explicitU-D_static.lib
   explicitU.lib
   explicitU_static.lib
   HTTPArch.lib
   InstArch.lib
   JS0BASEILB.lib
   JS0CRYPTEXIT.lib
   JS0DLK.lib
   JS0FM.lib
   JS0GROUP.lib
   JS0PCC.lib
   JS0SMT.lib
   jsmn.lib
   mkl_core_dll.lib
   mkl_intel_lp64_dll.lib
   mkl_intel_thread_dll.lib
   mkl_rt.lib
   mkl_sequential_dll.lib
   msmpi.lib
   SecurityContext.lib
   SMAAbuCodeGen.lib
   SMAAspCodeGen.lib
   SMABasCodeGen.lib
   SMAFeaBackbone.lib
   SMAShaCodeGen_DP.lib
   SMAShaCodeGen_SP.lib
   SMASimCodeGen.lib
   standardB.lib
   standardU.lib
   standardU_static.lib
   StringUtilities.lib
   SysSqlite.lib
   SystemTSUUID.lib
   SystemUUID.lib
   ```

4. Add runtime DLL directory to PATH

```
   C:\Program Files\Dassault Systemes\SimulationServices\V6R2019x\win_b64\code\bin
```

Once the project has been successfully built, you can run odb2vtk.exe

```
odb2vtk.exe --header 1 --odbFile C:/test/mixed_elements/collision.odb
```

This generates a header.json file.

```
odb2vtk.exe --header 0 --odbFile C:/test/mixed_elements/collision.odb --instance PART-1-1 PART-2-1 --step  Step-1:8 --writeHistory 0 -- writePVD 0
```

This generates collision_Step-1_8.vtu which represents the data at Step-1 and frame 8.

## Build C++ Project by CMake

Make sure the CMake option `AbqSDK_PRIVATE_INCLUDE_DIR` points to the correct location of Abaqus SDK when configuring the project using CMake. This option tells CMake where to find Abaqus SDK and configures proper linkage and includes.
On my machine, it is

```
   C:\Program Files\Dassault Systemes\SimulationServices\V6R2019x\win_b64\code\include
   C:\Program Files\Dassault Systemes\SimulationServices\V6R2019x
```

Then, you can configure and build the project using CMake.

## TODOS

- [ ] implement writeHistory for C++ version.
- [ ] implement writePVD for C++ version.
