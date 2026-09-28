#
# OREMO 主窗口的顶部菜单 (简体中文)
#
set t(file)                 "文件"
set t(file,choosesaveDir)   "更改保存文件夹"
set t(file,readRecList)     "读取录音表"
set t(file,saveRecList)     "保存录音表"
set t(file,readTypeList)    "读取发声类型表"
set t(file,readCommentList) "读取备注文件"
set t(file,makeRecList)     "从保存文件夹中的wav文件生成发声列表"
set t(file,makeRecList,msg) "已更新录音表和发声类型表"
set t(file,makeRecListFromUst)     "从ust文件生成发声列表"
set t(file,makeRecListFromUst,msg) "已更新录音表和发声类型表"
set t(file,saveSettings)    "将当前设置保存到初始化文件"
set t(file,Exit)            "退出"

set t(show)                 "显示"
set t(show,showWave)        "显示波形"
set t(show,showSpec)        "显示频谱"
set t(show,showpow)         "显示响度"
set t(show,showf0)          "显示F0（音高）"
set t(show,pitchGuide)      "显示音叉窗口"
set t(show,tempoGuide)      "显示节拍器"

set t(option)               "选项"
set t(option,removeDC)      "录音后去除直流分量"
set t(option,bgmGuide)      "录音方式设置"
set t(option,ioSettings)    "音频I/O设置"
set t(option,settings)      "高级设置"
set t(option,setBind)       "快捷键设置"
set t(option,setFontSize)   "字体大小设置"

set t(oto)                  "生成oto.ini"
set t(oto,auto)             "录音类型"
set t(oto,auto,tandoku)     "单独音"
set t(oto,auto,renzoku)     "连续音"

set t(help)                 "帮助"
set t(help,onlineHelp)      "在线手册"
set t(help,Version)         "版本"
set t(help,official1)       "打开官方网页"
set t(help,official2)       "打开官方网页(下载页)"

#
# OREMO 主窗口的其他标签
#
set t(.saveDir.midashi)     "保存文件夹："
set t(.recComment.midashi)  "搜索备注"
