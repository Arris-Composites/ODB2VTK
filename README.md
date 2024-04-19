![abaqusCAE](res/abaqusCAE.png)![U+2192.svg](res/U+2192.svg.png)![ParaView_Logo](res/ParaView_Logo.png)

# Abaqus output database to VTK converter

## Introduction

Abaqus output database (.odb extension) is a binary file native to Abaqus. To access the data from ODB file, without reverse engineering, is to use official Abaqus APIs which are provided in Python or C++. This project provides a converter implemented in Python and C++. The C++ version is considerably faster than the Python version but it needs proper configuration to successfully build from the source. This work is inspired by [Liujie](https://github.com/Liujie-SYSU/odb2vtk). And all other similar work doesn't satisfy my needs since I need a converter which is more general and extensible. So I ended up implement my own version of it. This converter will:

1. Convert all the field outputs which exist in the ODB file.
2. Convert data at integrations points / section points and material orientation.
3. Map Abaqus element to VTK cell at your will.

If you want to know more about the design of ODB2VTK, checkout this [article](https://www.sciencedirect.com/science/article/pii/S2352711023000274).

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
   C:\SIMULIA\EstProducts\2023\win_b64\code\include
   C:\SIMULIA\EstProducts\2023
   ```
2. Add the linker lib directories:
   ```
   C:\SIMULIA\EstProducts\2023\win_b64\code\lib
   ```
3. Add static libs

   I simply copied all libs

```
ABQDMP_Core.lib                                        
ABQMPI_api.lib                                         
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
ABQSMAElkCore.lib                                      
ABQSMAFeoModules.lib                                   
ABQSMAFsmShared.lib                                    
ABQSMAMsgModules.lib                                   
ABQSMAMtxCoreModule.lib                                
ABQSMAObjSimObjectsMod.lib                             
ABQSMAOdbApi.lib                                       
ABQSMAOdbAttrEO.lib                                    
ABQSMAOdbAttrEO2.lib                                   
ABQSMAOdbCalcK.lib                                     
ABQSMAOdbCore.lib                                      
ABQSMAOdbCoreGeom.lib                                  
ABQSMAOdbDdbOdb.lib                                    
ABQSMARfmInterface.lib                                 
ABQSMARomDiagEx.lib                                    
ABQSMASfsModule.lib                                    
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
AfrInterfacesUUID.lib                                  
AutomationInterfacesUUID.lib                           
CAT3DBehaviorItf.lib                                   
CAT3DPhysicalRepItf.lib                                
CATAfrComponentsModel.lib                              
CATAfrFoundation.lib                                   
CATAfrFoundationUUID.lib                               
CATAfrGeometryWshop.lib                                
CATAfrImmersiveRender.lib                              
CATAfrItf.lib                                          
CATAfrMePreferenceCtls.lib                             
CATAfrPalette.lib                                      
CATAfrPreferenceModel.lib                              
CATAfrPrferenceOptions.lib                             
CATAfrProgressTask.lib                                 
CATAfrProperties.lib                                   
CATAfrSelection.lib                                    
CATAuthoringUIInterfaces.lib                           
CATAutoItf.lib                                         
CATBBMagic.lib                                         
CATClnBase.lib                                         
CATComBase.lib                                         
CATComDrvBB.lib                                        
CATComHTTPEndPoint.lib                                 
CATComServices.lib                                     
CATComSidl.lib                                         
CATComSidlFile.lib                                     
CATDbProvider.lib                                      
CATDegUUID.lib                                         
CATDialogEngine.lib                                    
CATDiscover.lib                                        
CATDlgA2XWatcher.lib                                   
CATDlgAuxStatic.lib                                    
CATDlgBitmap.lib                                       
CATDlgHtml.lib                                         
CATDlgStandard.lib                                     
CATDWCInfra.lib                                        
CATFmuFileAccessInterfacesUUID.lib                     
CATFmuFileAccessItf.lib                                
CATGhosting.lib                                        
CATGraphicProperties.lib                               
CATImmVPMInterfaces.lib                                
CATImmVPMInterfacesLFT.lib                             
CATImmVPMInterfacesUUID.lib                            
CATImmVPMLegacyInterfaces.lib                          
CATImmVPMLegacyInterfacesUUID.lib                      
CATImmVPMNavInterfaces.lib                             
CATImmWtpItfUUID.lib                                   
CATInfInterfaces.lib                                   
CATInteractiveInterfaces.lib                           
CATJNIBridge.lib                                       
CATLic.lib                                             
CATLMjni.lib                                           
CATMagnitude.lib                                       
CATMathematics.lib                                     
CATMathStream.lib                                      
CATMecModLiveUseItf.lib                                
CATMecModLiveUseItfUUID.lib                            
CATMecModUseItf.lib                                    
CATMecModUseItfUUID.lib                                
CATMetaModelerProtocol.lib                             
CATMetaModelerProtocolUUID.lib                         
CATMMediaCore.lib                                      
CATMMediaCore2.lib                                     
CATMMediaPixelImage.lib                                
CATMMediaRasterFormats_SB_File.lib                     
CATMMediaRasterProcessor.lib                           
CATMMediaXMP.lib                                       
CATMMRasterEngineGDIplus.lib                           
CATMMRasterEngineIM.lib                                
CATMMRasterEngineIM_DBG.lib                            
CATMMRasterEngineOpenAPI.lib                           
CATObjectModelerBase.lib                               
CATObjectModelerContBase.lib                           
CATObjectModelerItf.lib                                
CATObjectModelerNavigator.lib                          
CATOmbLinkNavigationAccess.lib                         
CATOme.lib                                             
CATOmx.lib                                             
CATOmxBase.lib                                         
CATOmyLocalStorageCollector.lib                        
CATOpDataItf.lib                                       
CATP2PBaseUUID.lib                                     
CATP2PCore.lib                                         
CATPLMClientCoreItf.lib                                
CATPLMComponentInterfaces.lib                          
CATPLMComponentInterfacesUUID.lib                      
CATPLMDictionaryUUID.lib                               
CATPLMDispatcherItf.lib                                
CATPLMDispatcherSpecificItf.lib                        
CATPLMIdentification.lib                               
CATPLMIdentificationAccess.lib                         
CATPLMIdentificationAccessUUID.lib                     
CATPLMImplAdapterBase.lib                              
CATPLMIntegrationAccess.lib                            
CATPLMIntegrationAccessItf.lib                         
CATPLMIntegrationAccessUUID.lib                        
CATPLMIntegrationInterfaces.lib                        
CATPLMIntegrationInterfacesUUID.lib                    
CATPLMIntegrationUse.lib                               
CATPLMIntegrationUseUUID.lib                           
CATPLMKweDicoServices.lib                              
CATPLMModelBuilder.lib                                 
CATPLMModelerBaseInterfaces.lib                        
CATPLMModelerLanguage.lib                              
CATPLMServicesItf.lib                                  
CATPLMStreamDescriptor.lib                             
CATPrdAccessCAA.lib                                    
CATPrdAccessImpl.lib                                   
CATProductStructureInterfaces.lib                      
CATProductStructureUseItf.lib                          
CATProviderItf.lib                                     
CATScriptEngine.lib                                    
CATScriptReplayInteractions.lib                        
CATSGManagerUUID.lib                                   
CATSGV6Streaming.lib                                   
CATSimpleCommandMessage.lib                            
CATStyleProcessor.lib                                  
CATSWXVisu.lib                                         
CATSysCATIAAI.lib                                      
CATSysCATIASF.lib                                      
CATSysCommunication.lib                                
CATSysDbSettings.lib                                   
CATSysExternApp.lib                                    
CATSysMotifDrv.lib                                     
CATSysMultiThreadingSecured.lib                        
CATSysPreview.lib                                      
CATSysProxy.lib                                        
CATSysRunBrw.lib                                       
CATSysTS.lib                                           
CATSysTSObjectModeler.lib                              
CATUVEncoding.lib                                      
CATVBAInfra.lib                                        
CATView.lib                                            
CATViewSync.lib                                        
CATVirtualVaultSystem.lib                              
CATVis3DGrid.lib                                       
CATVisCIDPanel.lib                                     
CATVisColorChooser.lib                                 
CATVisCommands.lib                                     
CATVisController.lib                                   
CATVisControllerUUID.lib                               
CATVisDmuStream.lib                                    
CATVisFoundation.lib                                   
CATVisFoundationUUID.lib                               
CATVisHDRILightProcessing.lib                          
CATVisHeadlessAPI.lib                                  
CATVisHLR.lib                                          
CATVisIblPreconvolver.lib                              
CATVisImmersivePanel.lib                               
CATVisInteropXMLMesh.lib                               
CATVisItf.lib                                          
CATVisItfUUID.lib                                      
CATVisKDop.lib                                         
CATVisKDopLOD.lib                                      
CATVisLOD.lib                                          
CATVisMagnifier.lib                                    
CATVisMarshalling.lib                                  
CATVisNoGraphicalAPI.lib                               
CATVisOctreeTools.lib                                  
CATVisPanel.lib                                        
CATVisPropertiesUI.lib                                 
CATVisTesselation.lib                                  
CATVisuPerfoAddin.lib                                  
CATVisViewRotation.lib                                 
CATVisVoxels.lib                                       
CATVizGlider.lib                                       
CatXmlCls.lib                                          
CatXmlItf.lib                                          
CatXmlItfBase.lib                                      
CatXmlItfExt.lib                                       
CoexUPSJsonMapping.lib                                 
CommunicationsUUID.lib                                 
DataAdmin.lib                                          
DataCommonProtocolUse.lib                              
DI0BUILD.lib                                           
DI0PANV2.lib                                           
DialogDeclarativeEngine.lib                            
DSYApplicationMainArch.lib                             
DSYSysCnxExit.lib                                      
DSYSysDlg.lib                                          
DSYSysIRDriver.lib                                     
DSYSysIRManagerPlus.lib                                
DSYSysIRMSysAdapter.lib                                
DSYSysIRSendReport00.lib                               
DSYSysIRSendReportCom.lib                              
DSYSysIRSendReportItfPlugin.lib                        
DSYSysProgressHandler.lib                              
DSYSysTrayIcon.lib                                     
DSYSysWatchDogHelp.lib                                 
DSYSysWatchDogRegisterKeys.lib                         
DSYSysWMIDriver.lib                                    
DWCLink.lib                                            
EKCrypto.lib                                           
EKNvidiaGPUMonitoring.lib                              
EKPrivateArchive.lib                                   
EKSSL.lib                                              
ExperienceKernel.lib                                   
explicitB-D.lib                                        
explicitB.lib                                          
explicitU-D.lib                                        
explicitU-D_static.lib                                 
explicitU.lib                                          
explicitU_static.lib                                   
filenames.txt                                          
GraphicsOptimizer.lib                                  
GraphicsOptimizerUUID.lib                              
HTTPArch.lib                                           
ImageMagick.lib                                        
InfModelInterfaces.lib                                 
InfOSIDLImpl.lib                                       
InfOSIDLItf.lib                                        
InstArch.lib                                           
InteractiveInterfacesUUID.lib                          
IntroInfra.lib                                         
IVInterfaces.lib                                       
JS0CRYPTEXIT.lib                                       
JS0DLK.lib                                             
JS0FM.lib                                              
JS0GROUP.lib                                           
JS0PCC.lib                                             
JS0SMT.lib                                             
KnowledgeInterfacesUUID.lib                            
KnowledgeItf.lib                                       
libjpegCode.lib                                        
libpngCode.lib                                         
libtiffCode.lib                                        
LPCommonEditorItf.lib                                  
lz4_static.lib                                         
MaskedAttributeImpl.lib                                
MaskedAttributeItf.lib                                 
mkl_core_dll.lib                                       
mkl_intel_ilp64_dll.lib                                
mkl_intel_lp64_dll.lib                                 
mkl_intel_thread_dll.lib                               
mkl_rt.lib                                             
mkl_sequential_dll.lib                                 
MPROCTools.lib                                         
msmpi.lib                                              
MultimediaItf.lib                                      
NewTypingMigrationDBDI.lib                             
nvml.lib                                               
ObjectModelerNavigatorUUID.lib                         
ObjectModelerSystem.lib                                
PLMBatchInfraServices.lib                              
PLMBLTempoDevFlags.lib                                 
PLMBusinessLogicInterfaces.lib                         
PLMBusinessLogicInterfacesUUID.lib                     
PLMDictionaryInterfaces.lib                            
PLMDictionaryNavServices.lib                           
PLMExchangeCompletionServices.lib                      
PLMExchangeFileServices.lib                            
PLMExchangeGlobalServices.lib                          
PLMExchangeModel.lib                                   
PLMExchangeWebServices.lib                             
PLMFLPCommonModeler.lib                                
PLMModelerBase.lib                                     
PLMModelerBaseInterfacesUUID.lib                       
PLMPSISessionInterfaces.lib                            
PLMPSIUserExit.lib                                     
ProductStructure3DPartItf.lib                          
RecordToolsLib.lib                                     
RunTimeStackManager.lib                                
SceneGraphManager.lib                                  
SecurityContext.lib                                    
SGInfra.lib                                            
SG_UUID.lib                                            
SMAAbuCodeGen.lib                                      
SMAAspCodeGen.lib                                      
SMABasCodeGen.lib                                      
SMAFeaBackbone.lib                                     
SMAFsmCodeGen.lib                                      
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
UIModelInterfaces.lib                                  
UIModelInterfacesUUID.lib                              
UIVCoreTools.lib                                       
UndoRedoUI.lib                                         
VBAIntegration.lib                                     
VBAUUID.lib                                            
VisCore.lib                                            
VisGDIAPIUtility.lib                                   
VisGltf.lib                                            
VisQualityManagement.lib                               
VisRayTracingToggleCommand.lib                         
VisREKernel.lib                                        
VisREKernelTools.lib                                   
VisREMath.lib                                          
VisSceneGraph.lib                                      
VisTootle.lib                                          
VisuDialog.lib                                         
VisuDialogEx.lib                                       
VisuDialogImpl.lib                                     
VisuImmersive3D.lib                                    
VisuImmersiveDialogExUUID.lib                          
VPMEditorInterfaces.lib                                
VPMIDicInterfaces.lib                                  
XPDMServices.lib                                       
zLibCode.lib 
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

Make sure the CMake option `AbqSDK_PRIVATE_INCLUDE_DIR`, `AbqSDK_PRIVATE_LIB`, and `AbqSDK_PRIVATE_PUBLIC_DIR` point to the correct location of Abaqus SDK when configuring the project using CMake. This option tells CMake where to find Abaqus SDK and configures proper linkage and includes.
On my machine, 
`AbqSDK_PRIVATE_INCLUDE_DIR` = C:/SIMULIA/EstProducts/2023/win_b64/code/include
`AbqSDK_PRIVATE_PUBLIC_DIR` = C:/SIMULIA/EstProducts/2023
`AbqSDK_PRIVATE_LIB` = C:/SIMULIA/EstProducts/2023/win_b64/code/lib

They should be automatically configured by CMake if you have the same directories as mine. After this, you can configure and build the project using CMake.

## Convert a range of frames by one command

Now a new parse rule which accepts a range of frames has been added to the C++ version. This will be convenient to convert a large quantity of consecutive frames by one command.

```
odb2vtk.exe --header 0 --odbFile C:/test/mixed_elements/collision.odb --instance PART-1-1 PART-2-1 --step  Step-1:0-1000 --writeHistory 0 -- writePVD 0
```

converts frames ranging from 0 to 1000. So, it will generate 1001 individual vtu files. Do not mix it with single digit frame arguments.

## Abaqus Version Updates
Both the C++ and Python builds have been updated for Abaqus 2023. The C+

## TODOS

- [ ] implement writeHistory for C++ version.
- [ ] implement writePVD for C++ version.
