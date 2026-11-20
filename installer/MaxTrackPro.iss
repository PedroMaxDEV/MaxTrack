[Setup]
AppId=MaxTrackPro
#ifdef MaxHub
AppName=Max Hub
#ifdef HubVersion
AppVersion={#HubVersion}
#else
AppVersion=0.3.3
#endif
#else
AppName=MaxTrack Pro
AppVersion=0.9.21
#endif
SetupIconFile=MaxTrackPro.ico
WizardSmallImageFile=MaxTrackPro-Wizard.bmp
DefaultDirName={localappdata}\Programs\MaxTrackPro
PrivilegesRequired=lowest
OutputDir=..\dist\installer
#ifdef MaxHub
OutputBaseFilename=MaxHub-Setup
#else
OutputBaseFilename=MaxTrackPro-Setup
#endif
Compression=lzma2/fast
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\MaxTrackPro.exe
[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
[Tasks]
Name: "ets2"; Description: "Configurar o ETS2 para rastrear a cabeça sem OpenTrack"
[Files]
#ifdef CommerceBuild
#ifdef FreshTrackBuild
Source: "{#FreshTrackBuild}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
#else
Source: "..\dist\MaxTrackPro\*"; DestDir: "{app}"; Excludes: "MaxTrackPro.exe"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#CommerceBuild}\MaxTrackPro.exe"; DestDir: "{app}"; Flags: ignoreversion
#endif
#else
Source: "..\dist\MaxTrackPro\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
#endif
#ifdef CommerceBuild
Source: "{#CommerceBuild}\MaxTrackETS2Setup.exe"; Flags: dontcopy
#else
Source: "..\dist\installer-tools\MaxTrackETS2Setup.exe"; Flags: dontcopy
#endif
#ifdef MaxHub
#ifdef CommerceBuild
Source: "{#CommerceBuild}\MaxHub.exe"; DestDir: "{app}"; Flags: ignoreversion
#else
Source: "..\dist\MaxHub\MaxHub.exe"; DestDir: "{app}"; Flags: ignoreversion
#endif
Source: "..\dist\MaxHub\telemetry\*"; DestDir: "{app}\telemetry"; Flags: ignoreversion
Source: "..\dist\MaxHub\map-tools\map-builder.zip"; DestDir: "{app}\map-tools"; Flags: ignoreversion
Source: "..\dist\MaxHub\voice\*"; DestDir: "{app}\voice"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\hub\LEIA-ME.txt"; DestDir: "{app}"; DestName: "Max Hub - LEIA-ME.txt"; Flags: ignoreversion
#endif
[Icons]
Name: "{autoprograms}\MaxTrack Pro"; Filename: "{app}\MaxTrackPro.exe"
#ifdef MaxHub
Name: "{autoprograms}\Max Hub"; Filename: "{app}\MaxHub.exe"
#endif
[Run]
#ifdef MaxHub
Filename: "{app}\MaxHub.exe"; Description: "Abrir Max Hub"; Flags: nowait postinstall skipifsilent
Filename: "{app}\MaxHub.exe"; Flags: nowait skipifnotsilent; Check: IsHubUpdate
#else
Filename: "{app}\MaxTrackPro.exe"; Description: "Abrir MaxTrack Pro"; Flags: nowait postinstall skipifsilent
#endif

[Code]
const
  GameExecutable = 'bin\win_x64\eurotrucks2.exe';
  SteamGameKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\Steam App 227300';
  SteamKey = 'Software\Valve\Steam';

var
  GamePage: TInputDirWizardPage;
  ProfilePage: TOutputMsgWizardPage;
  ETS2Documents: String;

function IsHubUpdate: Boolean;
begin
  Result := ExpandConstant('{param:MAXUPDATE|0}') = '1';
end;

function ResolveGameFolder(Selection: String): String;
var Folder, Parent: String;
begin
  Result := '';
  Folder := RemoveQuotes(Trim(Selection));
  if Folder = '' then Exit;
  StringChangeEx(Folder, '/', '\', True);
  if CompareText(ExtractFileName(Folder), 'eurotrucks2.exe') = 0 then begin
    if not FileExists(Folder) then Exit;
    Folder := ExtractFileDir(Folder);
  end;
  Folder := RemoveBackslashUnlessRoot(Folder);

  if not FileExists(AddBackslash(Folder) + GameExecutable) then begin
    if CompareText(ExtractFileName(Folder), 'win_x64') = 0 then begin
      Parent := ExtractFileDir(Folder);
      if CompareText(ExtractFileName(Parent), 'bin') <> 0 then Exit;
      Folder := Parent;
    end;
    if CompareText(ExtractFileName(Folder), 'bin') <> 0 then Exit;
    Folder := ExtractFileDir(Folder);
    if not FileExists(AddBackslash(Folder) + GameExecutable) then Exit;
  end;
  Result := Folder;
end;

function ReadSteamValue(Line, Key: String): String;
var Prefix: String; QuoteAt: Integer;
begin
  Result := '';
  Prefix := '"' + Key + '"';
  Line := Trim(Line);
  if CompareText(Copy(Line, 1, Length(Prefix)), Prefix) <> 0 then Exit;
  Line := Trim(Copy(Line, Length(Prefix) + 1, Length(Line)));
  if Copy(Line, 1, 1) <> '"' then Exit;
  Delete(Line, 1, 1);
  QuoteAt := Pos('"', Line);
  if QuoteAt > 0 then Result := Copy(Line, 1, QuoteAt - 1);
end;

function FindGameInLibrary(LibraryPath: String): String;
var SteamApps, InstallDir: String; Manifest: TArrayOfString; I: Integer;
begin
  SteamApps := AddBackslash(LibraryPath) + 'steamapps\';
  Result := ResolveGameFolder(SteamApps + 'common\Euro Truck Simulator 2');
  if Result <> '' then Exit;
  if not LoadStringsFromFile(SteamApps + 'appmanifest_227300.acf', Manifest) then Exit;
  for I := 0 to GetArrayLength(Manifest) - 1 do begin
    InstallDir := ReadSteamValue(Manifest[I], 'installdir');
    if (InstallDir <> '') and (InstallDir <> '.') and (InstallDir <> '..') and
       (Pos('\', InstallDir) = 0) and (Pos('/', InstallDir) = 0) and (Pos(':', InstallDir) = 0) then begin
      Result := ResolveGameFolder(SteamApps + 'common\' + InstallDir);
      Exit;
    end;
  end;
end;

function SearchSteamLibraries(SteamPath: String): String;
var Libraries: TArrayOfString; LibraryPath: String; I: Integer;
begin
  Result := '';
  if not DirExists(SteamPath) then Exit;
  Result := FindGameInLibrary(SteamPath);
  if Result <> '' then Exit;
  if not LoadStringsFromFile(AddBackslash(SteamPath) + 'steamapps\libraryfolders.vdf', Libraries) then Exit;
  for I := 0 to GetArrayLength(Libraries) - 1 do begin
    LibraryPath := ReadSteamValue(Libraries[I], 'path');
    if LibraryPath <> '' then begin
      StringChangeEx(LibraryPath, '\\', '\', True);
      Result := FindGameInLibrary(LibraryPath);
      if Result <> '' then Exit;
    end;
  end;
end;

function FindSteamGameFolder: String;
var InstallPath, SteamPath: String;
begin
  Result := '';
  if RegQueryStringValue(HKLM64, SteamGameKey, 'InstallLocation', InstallPath) then
    Result := ResolveGameFolder(InstallPath);
  if Result <> '' then Exit;
  if RegQueryStringValue(HKLM32, SteamGameKey, 'InstallLocation', InstallPath) then
    Result := ResolveGameFolder(InstallPath);
  if Result <> '' then Exit;
  if RegQueryStringValue(HKCU, SteamKey, 'SteamPath', SteamPath) then
    Result := SearchSteamLibraries(SteamPath);
  if Result <> '' then Exit;
  if RegQueryStringValue(HKLM32, SteamKey, 'InstallPath', SteamPath) then
    Result := SearchSteamLibraries(SteamPath);
  if Result <> '' then Exit;
  Result := SearchSteamLibraries(ExpandConstant('{commonpf32}\Steam'));
end;

function CountProfiles(Folder: String): Integer;
var Entry: TFindRec;
begin
  Result := 0;
  if not FindFirst(AddBackslash(Folder) + '*', Entry) then Exit;
  try
    repeat
      if ((Entry.Attributes and FILE_ATTRIBUTE_DIRECTORY) <> 0) and
         (Entry.Name <> '.') and (Entry.Name <> '..') and
         FileExists(AddBackslash(Folder) + Entry.Name + '\controls.sii') then
        Result := Result + 1;
    until not FindNext(Entry);
  finally
    FindClose(Entry);
  end;
end;

procedure InitializeWizard;
var GameFolder, GameDescription: String;
begin
  GameFolder := FindSteamGameFolder;
  if GameFolder <> '' then
    GameDescription := 'ETS2 encontrado. Confira a pasta e clique em Avançar.'
  else
    GameDescription := 'Escolha a pasta do ETS2, bin ou win_x64. Você também pode colar o caminho completo de eurotrucks2.exe.';
  GamePage := CreateInputDirPage(wpSelectTasks, 'Pasta do ETS2',
    'Localize a instalação de 64 bits do jogo', GameDescription, False, '');
  GamePage.Add('Pasta do jogo');
  GamePage.Values[0] := GameFolder;
  ETS2Documents := ExpandConstant('{userdocs}\Euro Truck Simulator 2');
  ProfilePage := CreateOutputMsgPage(GamePage.ID, 'Perfis do ETS2',
    'Configuração automática dos controles', '');
end;

procedure CurPageChanged(PageID: Integer);
var Count: Integer;
begin
  if PageID <> ProfilePage.ID then Exit;
  Count := CountProfiles(ETS2Documents + '\profiles') + CountProfiles(ETS2Documents + '\steam_profiles');
  if Count > 0 then
    ProfilePage.MsgLabel.Caption := Format('Perfis encontrados em Documentos: %d.', [Count]) + #13#10#13#10 +
      'Ao instalar, o MaxTrack fará uma cópia de segurança e configurará todos esses perfis. Feche o ETS2 antes de continuar.'
  else
    ProfilePage.MsgLabel.Caption := 'Nenhum perfil com controls.sii foi encontrado em:' + #13#10 + ETS2Documents + #13#10#13#10 +
      'Você pode continuar a instalação do MaxTrack. Para configurar a integração depois, abra o ETS2, carregue um perfil, feche o jogo e execute o instalador novamente.';
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := ((PageID = GamePage.ID) or (PageID = ProfilePage.ID)) and
    not WizardIsTaskSelected('ets2');
end;

function NextButtonClick(PageID: Integer): Boolean;
var GameFolder: String;
begin
  Result := True;
  if PageID = GamePage.ID then begin
    GameFolder := ResolveGameFolder(GamePage.Values[0]);
    if GameFolder = '' then begin
      MsgBox('Não encontrei bin\win_x64\eurotrucks2.exe no caminho informado.' + #13#10 + #13#10 +
        'Na Steam, clique com o botão direito em Euro Truck Simulator 2 e escolha Gerenciar > Explorar arquivos locais.' + #13#10 +
        'Se quiser instalar só o MaxTrack agora, volte e desmarque a opção de configurar o ETS2.', mbError, MB_OK);
      Result := False;
      Exit;
    end;
    GamePage.Values[0] := GameFolder;
  end;
end;

function Quoted(Value: String): String;
begin
  Result := '"' + Value + '"';
end;

procedure CurStepChanged(Step: TSetupStep);
var Args, Exe, Report, MessageText: String; ResultCode: Integer; ReportText: AnsiString;
begin
  if (Step <> ssPostInstall) or WizardSilent or not WizardIsTaskSelected('ets2') then Exit;
  if (CountProfiles(ETS2Documents + '\profiles') + CountProfiles(ETS2Documents + '\steam_profiles')) = 0 then Exit;
  ExtractTemporaryFile('MaxTrackETS2Setup.exe');
  Exe := ExpandConstant('{tmp}\MaxTrackETS2Setup.exe');
  Report := ExpandConstant('{tmp}\maxtrack-ets2-result.txt');
  Args := Quoted(RemoveBackslashUnlessRoot(GamePage.Values[0])) + ' ' +
    Quoted(ETS2Documents) + ' ' + Quoted(ExpandConstant('{localappdata}\MaxTrackPro\config.json')) + ' ' +
    Quoted(ExpandConstant('{app}\bridge\MaxTrackBridge.dll')) + ' ' + Quoted(Report);
  ResultCode := -1;
  if Exec(Exe, Args, '', SW_HIDE, ewWaitUntilTerminated, ResultCode) and (ResultCode = 5) then begin
    MsgBox('O Windows protege a pasta do jogo. Autorize a cópia da ponte no próximo aviso.', mbInformation, MB_OK);
    if not ShellExec('runas', Exe, Args, '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
      ResultCode := -1;
  end;
  MessageText := '';
  if LoadStringFromFile(Report, ReportText) then MessageText := UTF8Decode(ReportText);
  if ResultCode = 0 then
    MsgBox('ETS2 configurado. Na cabine, olhe para frente e aperte F10.' + #13#10 + MessageText, mbInformation, MB_OK)
  else
    MsgBox('O MaxTrack foi instalado. A configuração do ETS2 ficou pendente.' + #13#10 +
      MessageText + #13#10 + 'Feche o jogo e o MaxTrack e execute o instalador novamente para tentar de novo.', mbError, MB_OK);
end;
