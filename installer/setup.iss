; Installateur Windows de WELLNESS GYM MANAGER (Inno Setup 6)
; Compilation :  iscc installer\setup.iss   (après PyInstaller)
#define AppNom "Wellness Gym Manager"
#define AppVersion "1.0.0"

[Setup]
AppId={{7A8DAF7A-631E-5070-8670-EAB51643CF8A}
AppName={#AppNom}
AppVersion={#AppVersion}
AppPublisher=WELLNESS HOTEL
DefaultDirName={autopf}\WellnessGymManager
DefaultGroupName=Wellness Gym Manager
OutputDir=Output
OutputBaseFilename=WellnessGymManager-Installation-{#AppVersion}
SetupIconFile=..\gym\static\gym\img\wellness.ico
UninstallDisplayIcon={app}\WellnessGym.exe
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=admin
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "bureau"; Description: "Créer un raccourci sur le Bureau"; GroupDescription: "Raccourcis :"
Name: "demarrage"; Description: "Lancer automatiquement à l'ouverture de session Windows"; GroupDescription: "Raccourcis :"; Flags: unchecked
Name: "reseau"; Description: "Autoriser les téléphones et tablettes du réseau de l'hôtel (application mobile)"; GroupDescription: "Réseau :"; Flags: unchecked

[Dirs]
; Données (base, sauvegardes, logo) : séparées du programme et modifiables par tous les comptes du poste
Name: "{commonappdata}\WellnessGymManager"; Permissions: users-modify

[Files]
Source: "..\dist\WellnessGym\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\docs\*.pdf"; DestDir: "{app}\Documentation"; Flags: ignoreversion skipifsourcedoesntexist

[INI]
Filename: "{commonappdata}\WellnessGymManager\config.ini"; Section: "serveur"; Key: "hote"; String: "0.0.0.0"; Tasks: reseau

[Icons]
Name: "{group}\Wellness Gym Manager"; Filename: "{app}\WellnessGym.exe"; WorkingDir: "{app}"
Name: "{group}\Documentation"; Filename: "{app}\Documentation"
Name: "{group}\Dossier des données et sauvegardes"; Filename: "{commonappdata}\WellnessGymManager"
Name: "{group}\Désinstaller"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Wellness Gym Manager"; Filename: "{app}\WellnessGym.exe"; WorkingDir: "{app}"; Tasks: bureau
Name: "{userstartup}\Wellness Gym Manager"; Filename: "{app}\WellnessGym.exe"; WorkingDir: "{app}"; Tasks: demarrage

[Run]
Filename: "netsh"; Parameters: "advfirewall firewall add rule name=""Wellness Gym Manager"" dir=in action=allow protocol=TCP localport=8000 profile=private"; Flags: runhidden; Tasks: reseau
Filename: "{app}\WellnessGym.exe"; Description: "Lancer Wellness Gym Manager"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "netsh"; Parameters: "advfirewall firewall delete rule name=""Wellness Gym Manager"""; Flags: runhidden; RunOnceId: "pare-feu"

[Messages]
fr.FinishedLabel=Installation terminée. Au premier lancement, créez le compte du responsable. Les données sont conservées dans C:\ProgramData\WellnessGymManager (elles ne sont jamais supprimées par une mise à jour ou une désinstallation).
