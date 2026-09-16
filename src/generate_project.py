#!/usr/bin/env python3
"""Rebuild the checked-in Xcode project using only Python's standard library."""
from pathlib import Path
import hashlib
ROOT = Path(__file__).resolve().parent
project = ROOT / 'HoverIntentStudy.xcodeproj'
project.mkdir(exist_ok=True)
def uid(name): return hashlib.sha1(name.encode()).hexdigest()[:24].upper()
objects = []
def obj(name, body):
    ident = uid(name); objects.append(f'{ident} = {{ {body} }};'); return ident
files = []
buildfiles = []
for path in sorted((ROOT / 'App').glob('*.swift')):
    ref = obj('file:'+path.name,f'isa = PBXFileReference; lastKnownFileType = sourcecode.swift; path = App/{path.name}; sourceTree = "<group>";')
    files.append(ref); buildfiles.append(obj('build:'+path.name,f'isa = PBXBuildFile; fileRef = {ref};'))
appref = obj('product','isa = PBXFileReference; explicitFileType = wrapper.application; path = HoverIntentStudy.app; sourceTree = BUILT_PRODUCTS_DIR;')
uitestref = obj('uitest-file','isa = PBXFileReference; lastKnownFileType = sourcecode.swift; path = UITests/HoverStudyUITests.swift; sourceTree = "<group>";')
uitestbuild = obj('uitest-build',f'isa = PBXBuildFile; fileRef = {uitestref};')
uitestproduct = obj('uitest-product','isa = PBXFileReference; explicitFileType = wrapper.cfbundle; path = HoverStudyUITests.xctest; sourceTree = BUILT_PRODUCTS_DIR;')
pkg = obj('package','isa = XCLocalSwiftPackageReference; relativePath = HoverStudyCore;')
pkgprod = obj('package-product',f'isa = XCSwiftPackageProductDependency; package = {pkg}; productName = HoverStudyCore;')
pkgbuild = obj('package-build',f'isa = PBXBuildFile; productRef = {pkgprod};')
sources = obj('sources',f'isa = PBXSourcesBuildPhase; buildActionMask = 2147483647; files = ({",".join(buildfiles)},); runOnlyForDeploymentPostprocessing = 0;')
frameworks = obj('frameworks',f'isa = PBXFrameworksBuildPhase; buildActionMask = 2147483647; files = ({pkgbuild},); runOnlyForDeploymentPostprocessing = 0;')
mediaref = obj('media-folder','isa = PBXFileReference; lastKnownFileType = folder; path = App/StudyMedia; sourceTree = "<group>";')
files.append(mediaref)
mediabuild = obj('media-build',f'isa = PBXBuildFile; fileRef = {mediaref};')
resources = obj('resources',f'isa = PBXResourcesBuildPhase; buildActionMask = 2147483647; files = ({mediabuild},); runOnlyForDeploymentPostprocessing = 0;')
products = obj('products',f'isa = PBXGroup; children = ({appref},{uitestproduct},); name = Products; sourceTree = "<group>";')
group = obj('group',f'isa = PBXGroup; children = ({",".join(files)},{uitestref},{products},); sourceTree = "<group>";')
pconfigs=[]; tconfigs=[]; uconfigs=[]
for name in ['Debug','Release']:
    pconfigs.append(obj('project-config:'+name,f'isa = XCBuildConfiguration; name = {name}; buildSettings = {{ CLANG_ENABLE_MODULES = YES; SDKROOT = iphoneos; IPHONEOS_DEPLOYMENT_TARGET = 16.4; SWIFT_VERSION = 5.0; ONLY_ACTIVE_ARCH = {"YES" if name == "Debug" else "NO"}; SWIFT_OPTIMIZATION_LEVEL = "{"-Onone" if name == "Debug" else "-O"}"; }};'))
    settings='''CODE_SIGN_STYLE = Automatic; CURRENT_PROJECT_VERSION = 9; MARKETING_VERSION = 2.4; GENERATE_INFOPLIST_FILE = YES; PRODUCT_BUNDLE_IDENTIFIER = org.hoverresearch.HoverIntentStudy; PRODUCT_NAME = "$(TARGET_NAME)"; TARGETED_DEVICE_FAMILY = 2; SUPPORTED_PLATFORMS = "iphoneos iphonesimulator"; SUPPORTS_MACCATALYST = NO; INFOPLIST_KEY_CFBundleDisplayName = "Hover Intent Study"; INFOPLIST_KEY_NSCameraUsageDescription = "仅在您开启视线采集时使用前置摄像头估计阅读注视位置；不保存面部画面。"; INFOPLIST_KEY_UIApplicationSceneManifest_Generation = YES; INFOPLIST_KEY_UILaunchScreen_Generation = YES; INFOPLIST_KEY_UIRequiresFullScreen = YES; INFOPLIST_KEY_UISupportedInterfaceOrientations_iPad = "UIInterfaceOrientationLandscapeLeft UIInterfaceOrientationLandscapeRight"; INFOPLIST_KEY_UIFileSharingEnabled = YES; INFOPLIST_KEY_LSSupportsOpeningDocumentsInPlace = YES; SWIFT_EMIT_LOC_STRINGS = YES;'''
    tconfigs.append(obj('target-config:'+name,f'isa = XCBuildConfiguration; name = {name}; buildSettings = {{ {settings} }};'))
    uconfigs.append(obj('uitest-config:'+name,f'isa = XCBuildConfiguration; name = {name}; buildSettings = {{ CODE_SIGN_STYLE = Automatic; GENERATE_INFOPLIST_FILE = YES; PRODUCT_BUNDLE_IDENTIFIER = org.hoverresearch.HoverStudyUITests; PRODUCT_NAME = "$(TARGET_NAME)"; TARGETED_DEVICE_FAMILY = 2; TEST_TARGET_NAME = HoverIntentStudy; }};'))
pconfiglist=obj('project-configs',f'isa = XCConfigurationList; buildConfigurations = ({",".join(pconfigs)},); defaultConfigurationIsVisible = 0; defaultConfigurationName = Release;')
tconfiglist=obj('target-configs',f'isa = XCConfigurationList; buildConfigurations = ({",".join(tconfigs)},); defaultConfigurationIsVisible = 0; defaultConfigurationName = Release;')
target=obj('target',f'isa = PBXNativeTarget; buildConfigurationList = {tconfiglist}; buildPhases = ({sources},{frameworks},{resources},); buildRules = (); dependencies = (); name = HoverIntentStudy; packageProductDependencies = ({pkgprod},); productName = HoverIntentStudy; productReference = {appref}; productType = "com.apple.product-type.application";')
uconfiglist=obj('uitest-configs',f'isa = XCConfigurationList; buildConfigurations = ({",".join(uconfigs)},); defaultConfigurationIsVisible = 0; defaultConfigurationName = Release;')
usources=obj('uitest-sources',f'isa = PBXSourcesBuildPhase; buildActionMask = 2147483647; files = ({uitestbuild},); runOnlyForDeploymentPostprocessing = 0;')
dependency=obj('uitest-dependency',f'isa = PBXTargetDependency; target = {target};')
utarget=obj('uitest-target',f'isa = PBXNativeTarget; buildConfigurationList = {uconfiglist}; buildPhases = ({usources},); buildRules = (); dependencies = ({dependency},); name = HoverStudyUITests; productName = HoverStudyUITests; productReference = {uitestproduct}; productType = "com.apple.product-type.bundle.ui-testing";')
proj=obj('project',f'isa = PBXProject; attributes = {{ LastUpgradeCheck = 2620; }}; buildConfigurationList = {pconfiglist}; compatibilityVersion = "Xcode 14.0"; developmentRegion = en; hasScannedForEncodings = 0; knownRegions = (en, Base, "zh-Hans"); mainGroup = {group}; packageReferences = ({pkg},); productRefGroup = {products}; projectDirPath = ""; projectRoot = ""; targets = ({target},{utarget},);')
(project/'project.pbxproj').write_text('// !$*UTF8*$!\n{ archiveVersion = 1; classes = {}; objectVersion = 60; objects = {\n'+'\n'.join(objects)+f'\n}}; rootObject = {proj}; }}\n')
scheme=project/'xcshareddata/xcschemes';scheme.mkdir(parents=True,exist_ok=True)
(scheme/'HoverIntentStudy.xcscheme').write_text(f'''<?xml version="1.0" encoding="UTF-8"?>
<Scheme LastUpgradeVersion="2620" version="1.3">
<BuildAction parallelizeBuildables="YES" buildImplicitDependencies="YES"><BuildActionEntries><BuildActionEntry buildForTesting="YES" buildForRunning="YES" buildForProfiling="YES" buildForArchiving="YES" buildForAnalyzing="YES"><BuildableReference BuildableIdentifier="primary" BlueprintIdentifier="{target}" BuildableName="HoverIntentStudy.app" BlueprintName="HoverIntentStudy" ReferencedContainer="container:HoverIntentStudy.xcodeproj"/></BuildActionEntry></BuildActionEntries></BuildAction>
<TestAction buildConfiguration="Debug" selectedDebuggerIdentifier="Xcode.DebuggerFoundation.Debugger.LLDB" selectedLauncherIdentifier="Xcode.IDEFoundation.Launcher.LLDB" shouldUseLaunchSchemeArgsEnv="YES"><Testables><TestableReference skipped="NO"><BuildableReference BuildableIdentifier="primary" BlueprintIdentifier="{utarget}" BuildableName="HoverStudyUITests.xctest" BlueprintName="HoverStudyUITests" ReferencedContainer="container:HoverIntentStudy.xcodeproj"/></TestableReference></Testables></TestAction>
<LaunchAction buildConfiguration="Debug" selectedDebuggerIdentifier="Xcode.DebuggerFoundation.Debugger.LLDB" selectedLauncherIdentifier="Xcode.IDEFoundation.Launcher.LLDB" launchStyle="0" useCustomWorkingDirectory="NO" ignoresPersistentStateOnLaunch="NO" debugDocumentVersioning="YES" allowLocationSimulation="YES"><BuildableProductRunnable runnableDebuggingMode="0"><BuildableReference BuildableIdentifier="primary" BlueprintIdentifier="{target}" BuildableName="HoverIntentStudy.app" BlueprintName="HoverIntentStudy" ReferencedContainer="container:HoverIntentStudy.xcodeproj"/></BuildableProductRunnable></LaunchAction>
<ProfileAction buildConfiguration="Release" shouldUseLaunchSchemeArgsEnv="YES" useCustomWorkingDirectory="NO" debugDocumentVersioning="YES"><BuildableProductRunnable runnableDebuggingMode="0"><BuildableReference BuildableIdentifier="primary" BlueprintIdentifier="{target}" BuildableName="HoverIntentStudy.app" BlueprintName="HoverIntentStudy" ReferencedContainer="container:HoverIntentStudy.xcodeproj"/></BuildableProductRunnable></ProfileAction>
<AnalyzeAction buildConfiguration="Debug"/><ArchiveAction buildConfiguration="Release" revealArchiveInOrganizer="YES"/>
</Scheme>''')
print(project)
