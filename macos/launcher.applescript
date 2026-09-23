-- Built using macOS's stay-open applet runtime; no login item or launch daemon.
property projectRoot : __PROJECT_ROOT__
property servicePort : __SERVICE_PORT__
property serviceURL : __SERVICE_URL__
property displayName : __DISPLAY_NAME__
property startupFailed : false

on controlService(actionName)
    return do shell script "/bin/bash " & quoted form of (projectRoot & "/scripts/app-control.sh") & " " & actionName & " --port " & servicePort
end controlService

on launchCompanion()
    set startupFailed to false
    try
        my controlService("start")
    on error messageText
        set startupFailed to true
        display alert "無法開啟伴讀" message messageText as critical
        quit
        return
    end try
    try
        open location serviceURL
    on error
        display alert "服務已啟動" message ("請在瀏覽器開啟 " & serviceURL)
    end try
end launchCompanion

on run
    my launchCompanion()
end run

on reopen
    activate
    set choice to button returned of (display dialog "伴讀 App 正在執行。\n\n關閉網頁不會結束服務；要完整關閉，請選「關閉服務並退出」，或使用 App 選單的「退出」。" with title displayName buttons {"關閉服務並退出", "繼續執行", "開啟伴讀網頁"} default button "開啟伴讀網頁" with icon (path to resource "StudyPartner.icns"))
    if choice is "關閉服務並退出" then
        quit
    else if choice is "開啟伴讀網頁" then
        my launchCompanion()
    end if
end reopen

on idle
    return 30
end idle

on quit
    if not startupFailed then
        try
            my controlService("stop")
        on error messageText
            display alert "服務尚未關閉" message messageText as warning
            return
        end try
    end if
    continue quit
end quit
