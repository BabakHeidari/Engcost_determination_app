Unicode true
!include "MUI2.nsh"
Name "Engcost"
OutFile "${OUTPUT}"
InstallDir "$LOCALAPPDATA\Programs\Engcost"
RequestExecutionLevel user
SetCompressor /SOLID lzma
VIProductVersion "0.11.2.0"
VIAddVersionKey "ProductName" "Engcost"
VIAddVersionKey "FileVersion" "0.11.2"
VIAddVersionKey "ProductVersion" "0.11.2"
VIAddVersionKey "FileDescription" "Offline local Engcost installer"
!define MUI_ICON "..\icons\engcost.ico"
!define MUI_UNICON "..\icons\engcost.ico"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "Farsi"

Function .onInit
  SetShellVarContext current
FunctionEnd

Section "Engcost"
  SetShellVarContext current
  IfFileExists "$INSTDIR\*" 0 checked
  IfFileExists "$INSTDIR\.engcost-install" checked
  Abort "پوشه نصب خالی نیست و متعلق به سامانه نیست؛ پوشه دیگری انتخاب کنید."
  checked:
  IfFileExists "$INSTDIR.next\*" blocked
  IfFileExists "$INSTDIR.previous\*" blocked
  IfFileExists "$INSTDIR\Engcost.exe" 0 stopped
  FileOpen $0 "$INSTDIR\.engcost-upgrading" w
  FileClose $0
  ExecWait '"$INSTDIR\Engcost.exe" --stop' $0
  IntCmp $0 0 stopped
  Abort "سامانه هنوز در حال ذخیره‌سازی است؛ نصب متوقف شد."
  blocked:
  Abort "پوشه نصب موقت از قبل وجود دارد؛ بازیابی نصب قبلی را بررسی کنید."
  stopped:
  SetOutPath "$INSTDIR.next"
  File /r "${BUNDLE}\*"
  WriteUninstaller "$INSTDIR.next\Uninstall.exe"
  FileOpen $0 "$INSTDIR.next\.engcost-install" w
  FileWrite $0 "Engcost 0.11.2"
  FileClose $0
  IfErrors stagingfailed
  SetOutPath "$TEMP"
  IfFileExists "$INSTDIR\*" 0 publish
  Rename "$INSTDIR" "$INSTDIR.previous"
  IfErrors stagingfailed
  publish:
  Rename "$INSTDIR.next" "$INSTDIR"
  IfErrors restore
  RMDir /r "$INSTDIR.previous"
  Goto published
  restore:
  Rename "$INSTDIR.previous" "$INSTDIR"
  stagingfailed:
  RMDir /r "$INSTDIR.next"
  Delete "$INSTDIR\.engcost-upgrading"
  Abort "نصب کامل نشد؛ نسخه قبلی و داده‌ها حفظ شد."
  published:
  CreateDirectory "$SMPROGRAMS\Engcost"
  CreateShortCut "$SMPROGRAMS\Engcost\Engcost.lnk" "$INSTDIR\Engcost.exe"
  CreateShortCut "$DESKTOP\Engcost.lnk" "$INSTDIR\Engcost.exe"
  CreateShortCut "$SMPROGRAMS\Engcost\توقف سامانه.lnk" "$INSTDIR\Engcost.exe" "--stop"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Engcost" "DisplayName" "Engcost"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Engcost" "DisplayVersion" "0.11.2"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Engcost" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Engcost" "DisplayIcon" "$INSTDIR\Engcost.exe"
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Engcost" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Engcost" "NoRepair" 1
SectionEnd

Section "Uninstall"
  SetShellVarContext current
  IfFileExists "$INSTDIR\.engcost-install" owned
  Abort "مالکیت پوشه نصب تأیید نشد؛ هیچ فایلی حذف نشد."
  owned:
  SetOutPath "$TEMP"
  FileOpen $0 "$INSTDIR\.engcost-upgrading" w
  FileClose $0
  ExecWait '"$INSTDIR\Engcost.exe" --stop' $0
  IntCmp $0 0 stopped
  Abort "سامانه هنوز در حال ذخیره‌سازی است؛ حذف متوقف شد."
  stopped:
  Delete "$DESKTOP\Engcost.lnk"
  RMDir /r "$SMPROGRAMS\Engcost"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Engcost"
  RMDir /r "$INSTDIR"
  # User data under LOCALAPPDATA\Engcost or a selected workspace is retained.
SectionEnd
