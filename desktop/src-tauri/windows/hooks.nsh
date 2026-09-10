!macro NSIS_HOOK_PREINSTALL
  ; Sidecar keeps .pyd files locked even after the window is gone.
  ExecWait '"$SYSDIR\taskkill.exe" /F /IM ${MAINBINARYNAME}.exe /T'
  ExecWait '"$SYSDIR\taskkill.exe" /F /IM droidnote-backend.exe /T'
  Sleep 2000
!macroend

!macro NSIS_HOOK_POSTINSTALL
  SetOutPath "$INSTDIR"
  CreateShortCut "$DESKTOP\${PRODUCTNAME}.lnk" "$INSTDIR\${MAINBINARYNAME}.exe" "" "$INSTDIR\${MAINBINARYNAME}.exe" 0 SW_SHOWNORMAL
  CreateDirectory "$APPDATA\DroidNote"
  FileOpen $0 "$APPDATA\DroidNote\install-lang.txt" w
  FileWrite $0 "$LANGUAGE"
  FileClose $0
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  ExecWait '"$SYSDIR\taskkill.exe" /F /IM ${MAINBINARYNAME}.exe /T'
  ExecWait '"$SYSDIR\taskkill.exe" /F /IM droidnote-backend.exe /T'
  Delete "$DESKTOP\${PRODUCTNAME}.lnk"
  Delete "$SMPROGRAMS\${PRODUCTNAME}.lnk"
  Delete "$SMPROGRAMS\DroidNote\${PRODUCTNAME}.lnk"
  RMDir "$SMPROGRAMS\DroidNote"
!macroend

!macro NSIS_HOOK_POSTUNINSTALL
  RMDir /r /REBOOTOK "$LOCALAPPDATA\${BUNDLEID}"
  ${If} $UpdateMode <> 1
    SetShellVarContext current
    RMDir /r /REBOOTOK "$APPDATA\DroidNote"
    RMDir /r /REBOOTOK "$LOCALAPPDATA\DroidNote"
  ${EndIf}
  Delete "$DESKTOP\${PRODUCTNAME}.lnk"
!macroend
