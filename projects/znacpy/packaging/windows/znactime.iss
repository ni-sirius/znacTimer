#ifndef AppVersion
  #error AppVersion must be provided by packaging/build.py
#endif
#ifndef BundleDir
  #error BundleDir must be provided by packaging/build.py
#endif
#ifndef OutputDir
  #error OutputDir must be provided by packaging/build.py
#endif
#ifndef OutputBaseFilename
  #error OutputBaseFilename must be provided by packaging/build.py
#endif
#ifndef AppIcon
  #error AppIcon must be provided by packaging/build.py
#endif
#ifndef LicenseFile
  #error LicenseFile must be provided by packaging/build.py
#endif

[Setup]
AppId={{B9DA5C75-3877-4A4B-BF19-2C8EF8D04EA1}
AppName=znacTime
AppVersion={#AppVersion}
AppPublisher=znac
AppPublisherURL=https://znac.org
DefaultDirName={localappdata}\Programs\znacTime
DefaultGroupName=znacTime
DisableProgramGroupPage=yes
LicenseFile={#LicenseFile}
OutputDir={#OutputDir}
OutputBaseFilename={#OutputBaseFilename}
SetupIconFile={#AppIcon}
UninstallDisplayIcon={app}\znacTime.exe
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupArchitecture=x64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "{#BundleDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\znacTime"; Filename: "{app}\znacTime.exe"
Name: "{autodesktop}\znacTime"; Filename: "{app}\znacTime.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\znacTime.exe"; Description: "Launch znacTime"; Flags: nowait postinstall skipifsilent
