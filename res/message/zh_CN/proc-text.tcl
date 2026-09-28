#--------------------------------
# ※特殊设置
# 界面使用的字体 (若系统中没有该字体，会自动改用可用的日文/中文字体)
#
set t(fontName) "Microsoft YaHei"


#--------------------------------
# 消息 (简体中文)
#

# 对话框常用文字
set t(.confm)        "确认"
set t(.confm.r)      "读取"
set t(.confm.nr)     "不读取"
set t(.confm.fioErr) "文件I/O错误"
set t(.confm.yes)    "是"
set t(.confm.no)     "否"
set t(.confm.ok)     "确认"
set t(.confm.apply)  "应用"
set t(.confm.run)    "运行"
set t(.confm.c)      "取消"
set t(.confm.errTitle) "错误"
set t(.confm.warnTitle) "警告"
set t(.confm.delParam)  "当前的原音参数将被清除。确定吗？"

# 读取保存文件夹中的wav文件并记入列表
set t(makeRecListFromDir,q)  "要读取原音参数文件吗？"
set t(makeRecListFromDir,a)  "自动生成参数"

# 读取ust文件并记入列表
set t(makeRecListFromUst,title1)    "打开ust文件"
set t(makeRecListFromUst,errMsg)    "无法读取ust文件"
set t(makeRecListFromUst,doneMsg)   "已读取ust文件"

# 启动时自动推定参数的向导
set t(genParamWizard,title)  "音频数据的类型"
set t(genParamWizard,q)      "请选择要处理的音频数据类型。"
set t(genParamWizard,a1)     "单独发声数据"
set t(genParamWizard,a2)     "连续发声数据"

# 保存 reclist.txt
set t(saveRecList,title)     "保存录音表"
set t(saveRecList,errMsg)    "无法写入 \$v(recListFile)"
set t(saveRecList,errMsg2)   "无法写入音名"
set t(saveRecList,doneMsg)   "已将录音表保存到 \$v(recListFile)"

# 保存备注
set t(saveCommentList,errMsg) "无法保存备注"

# 读取录音表文件
set t(readRecList,title1)    "打开录音表"
set t(readRecList,errMsg)    "无法读取录音表文件 (\$v(recListFile))"
set t(readRecList,errMsg2)   "无法读取录音音名"
set t(readRecList,doneMsg)   "已读取 \$v(recListFile)"
set t(readRecList,overwrite) "录音表所在文件夹中有备注文件。要清除当前备注并读取它吗？"

# 读取备注文件
set t(readCommentList,errMsg)   "无法读取备注数据"
set t(readCommentList,doneMsg)  "\"已读取 \$commNum 条备注\""
set t(readCommentList,doneMsg2) "\"已读取 \$commNum 条备注 (其中 \$ignoreNum 条重复)\""

# 读取发声类型表文件
set t(readTypeList,title)    "打开发声类型表"
set t(readTypeList,errMsg)   "无法读取发声类型表文件 (\$v(typeListFile))"
set t(readTypeList,errMsg2)  "无法读取发声类型表"
set t(readTypeList,doneMsg)  "已读取 \$v(typeListFile)"

# 指定保存文件夹
set t(choosesaveDir,title)   "选择保存文件夹"
set t(choosesaveDir,doneMsg) "已更改保存文件夹"
set t(choosesaveDir,q)       "要同时读取原音参数文件吗？"

# 若未保存则把波形保存到文件
set t(saveWavFile,doneMsg)   "已保存 \$v(saveDir)/\$v(recLab)\$v(typeLab).wav"

# F0计算中限制键盘/鼠标输入的窗口
set t(waitWindow,title)      "正在计算F0（音高）"

# 录音BGM窗口
set t(bgmGuide,title)  "录音方式设置"
set t(bgmGuide,mode)   "录音模式："
set t(bgmGuide,r1)     "手动录音。按住「r」键期间处于录音状态（与OREMO ver 1.0相同）。"
set t(bgmGuide,r2)     "自动录音1。按「r」键后播放一次BGM，并自动进入录音状态。切换录音项需手动。"
set t(bgmGuide,r3)     "自动录音2。按「r」键后循环播放BGM，自动进入录音状态，并自动切换录音项。"
set t(bgmGuide,r4)     "禁用。"
set t(bgmGuide,bgm)    "BGM文件："
set t(bgmGuide,bTitle) "指定BGM文件"
set t(bgmGuide,play)   "播放"
set t(bgmGuide,stop)   "停止"
set t(bgmGuide,tplay)  "试听录音示例："

# 读取并播放指定文件
set t(testPlayBGM,errMsg)   "无法读取文件"
set t(testPlayBGM,errTitle) "播放错误"

# 节拍器窗口
set t(tempoGuide,title)             "节拍器"
set t(tempoGuide,click)             "咔嗒声："
set t(tempoGuide,clickTitle)        "指定咔嗒声"
set t(tempoGuide,tempo)             "速度："
set t(tempoGuide,bpm)               "BPM = "
set t(tempoGuide,bpmUnit)           "毫秒/拍"
set t(tempoGuide,comment)           "※按「m」键切换播放/停止。"

# 指定频率播放正弦波
set t(pitchGuide,title)             "音叉窗口"
set t(pitchGuide,sel)               "选择引导音："
set t(pitchGuide,vol)               "音量："
set t(pitchGuide,comment)           "※快捷键：o、上下方向键、2,4,6,8、ESC"

# 由自动录制的连续发声生成oto.ini
set t(genParam,title)  "生成连续音用oto.ini"
set t(genParam,tempo)  "录音速度："
set t(genParam,bpm)    "单位： bpm"
set t(genParam,S)      "发声开始位置："
set t(genParam,unit)   "单位："
set t(genParam,haku)   "拍"
set t(genParam,darrow) "↓　↓"
set t(genParam,bInit)  "根据录音速度初始化各参数值"
set t(genParam,O)      "重叠："
set t(genParam,msec)   "单位：毫秒"
set t(genParam,P)      "先行发声："
set t(genParam,C)      "固定范围："
set t(genParam,E)      "右空白："
set t(genParam,do)     "生成参数"
set t(genParam,aliasMax)          "※别名重复时是否添加序号"
set t(genParam,aliasMaxNo)        "不添加(保持重复)"
set t(genParam,aliasMaxYes)       "添加"
set t(genParam,aliasMaxNum)       "序号上限(0=无限制)"
set t(genParam,autoAdjustRen)     "使用自动修正1(基于响度)"
set t(genParam,vLow)              "先行发声的响度凹陷："
set t(genParam,sRange)            "先行发声的可移动范围："
set t(genParam,f0pow)             "※除上述外还会使用F0（音高）、响度相关参数。"
set t(genParam,db)                "单位：dB"
set t(genParam,autoAdjustRen2)    "使用自动修正2(基于MFCC，耗时较长)"
set t(genParam,autoAdjustRen2Opt) "选项"
set t(genParam,autoAdjustRen2Pattern) "适用对象"

# 自动生成连续发声的参数
set t(doGenParam,doneMsg) "已读取 \$v(paramFile)"

# 生成oto.ini前检查是否有未保存的wav
set t(checkWavForOREMO,saveQ)  "当前显示的wav文件尚未保存。"
set t(checkWavForOREMO,saveA1) "保存并继续"
set t(checkWavForOREMO,saveA2) "不保存继续"
set t(checkWavForOREMO,saveA3) "取消"

# 一览表的搜索窗口
set t(searchParam,title)     "搜索"
set t(searchParam,search)    "搜索"
set t(searchParam,rup)       "向开头搜索"
set t(searchParam,rdown)     "向末尾搜索"
set t(searchParam,doneTitle) "搜索结束"
set t(searchParam,doneMsg)   "未找到。"

# 开始自动录音(带BGM)
set t(autoRecStart,errMsg)   "无法读取BGM文件 (\$v(bgmFile))"
set t(autoRecStart,errMsg2)  "无法读取BGM设置文件 \$v(bgmParamFile)"
set t(autoRecStart,errMsg3)  "单位指定不正确"
set t(autoRecStart,errMsg4)  "设置文件 (\$v(bgmParamFile)) 的最后一行必须设置 repeat。"
set t(autoRecStart,unit)     "单位"

# 停止自动录音
set t(autoRecStop,doneMsg)   "已受理停止自动录音"

# 节拍器播放/停止切换
set t(toggleMetroPlay,stopMsg)  "节拍器已停止"
set t(toggleMetroPlay,errTitle) "节拍器错误"
set t(toggleMetroPlay,errMsg)   "节拍器速度请设在50～200bpm范围内。"
set t(toggleMetroPlay,errMsg2)  "找不到节拍器用wav文件 (\$v(clickWav))。"
set t(toggleMetroPlay,playMsg)  "节拍器播放中...(按「m」停止)"
set t(toggleMetroPlay,errPa)  "节拍器播放失败。"

# 音叉播放/停止切换
set t(toggleOnsaPlay,stopMsg) "音叉已停止"
set t(toggleOnsaPlay,playMsg) "音叉持续播放中...(按o停止)"

# 播放/停止切换
set t(togglePlay,stopMsg) "停止播放"
set t(togglePlay,playMsg) "播放中..."

# 选择颜色
set t(chooseColor,title) "颜色设置"

# 波形颜色设置
set t(setColor,selColor) "颜色设置"

# 生成打包了音名选择菜单的框架
set t(packToneList,play)   "播放"
set t(packToneList,repeat) "持续"

# 保存当前设置
set t(saveSettings,title)  "生成初始化文件"

# 把输入输出设备设置窗口的值应用到设备
set t(setIODevice,errPa)  "PortAudio设备设置失败。"
set t(setIODevice,errPa2) "请选择PortAudio的输入设备。"
set t(setIODevice,errPa3) "请检查PortAudio的输入声道数。"
set t(setIODevice,errPa4) "请检查PortAudio的采样率。"
set t(setIODevice,errPa5) "请检查PortAudio的缓冲区大小。"
set t(setIODevice,errPaOut2) "请选择PortAudio的输出设备。"

# 输入输出设备设置窗口
set t(ioSettings,title)    "音频I/O设置"
set t(ioSettings,inDev)    "输入设备："
set t(ioSettings,outDev)   "输出设备："
set t(ioSettings,inGain)   "输入增益(部分设备无效)："
set t(ioSettings,outGain)  "输出增益(部分设备无效)："
set t(ioSettings,latency)  "延迟(部分设备无效)："
set t(ioSettings,sndBuffer) "录音缓冲区大小："
set t(ioSettings,bgmBuffer) "引导BGM缓冲区大小："
set t(ioSettings,comment0) "※本设置窗口请尽量保持默认(设备=声音映射器/Wave Mapper)。"
set t(ioSettings,comment0b) "　 选用DirectSound等设备时可能导致运行不稳定。"
set t(ioSettings,comment1) "※ 修改上述设置后请务必按「应用」或「确定」。"
set t(ioSettings,comment2) "　 不按的话设置不会生效。"
set t(ioSettings,useRequestRec)  "录音"
set t(ioSettings,useRequestPlay) "播放"
set t(ioSettings,sampleRate) "采样率(Hz)："
set t(ioSettings,format)     "格式(量化位数)："
set t(ioSettings,inChannel)  "输入声道数："
set t(ioSettings,bufferSize)  "缓冲区大小："
set t(ioSettings,portaudio)   "使用PortAudio进行"

# 单独音的UTAU原音参数推定设置窗口
set t(estimateParam,title)       "原音参数自动推定(单独音用)"
set t(estimateParam,pFLen)       "响度采样单位"
set t(estimateParam,preemph)     "预加重"
set t(estimateParam,pWinLen)     "响度窗口宽度"
set t(estimateParam,pWinkind)    "窗口类型"
set t(estimateParam,pUttMin)     "发声中的响度最小值"
set t(estimateParam,vLow)        "元音的响度最小值"
set t(estimateParam,pUttMinTime) "最短发声时间"
set t(estimateParam,uttLen)      "发声中的响度波动"
set t(estimateParam,silMax)      "静音中的响度最大值"
set t(estimateParam,silMinTime)  "最短静音时间"
set t(estimateParam,minC)        "辅音长(固定范围)的最小值"
set t(estimateParam,f0)          "※除上述外，还会使用F0（音高）相关参数进行推定。"
set t(estimateParam,target)      "推定对象"
set t(estimateParam,S)           "左空白"
set t(estimateParam,C)           "辅音部"
set t(estimateParam,E)           "右空白"
set t(estimateParam,P)           "先行发声"
set t(estimateParam,O)           "重叠"
set t(estimateParam,overWrite)   "将覆盖当前的原音参数。确定吗？"
set t(estimateParam,runAll)      "对全部wav执行"
set t(estimateParam,runSel)      "对选中范围执行"

# UTAU原音参数的推定
set t(doEstimateParam,startMsg)  "正在推定参数… "
set t(doEstimateParam,doneMsg)   "参数推定结束"

# 读取原音参数
set t(readParamFile,selMsg)   "选择原音参数"
set t(readParamFile,startMsg) "正在读取原音参数..."
set t(readParamFile,errMsg)   "\$v(paramFile) 引用了 \$v(saveDir)/ 下不存在的wav文件。"
set t(readParamFile,example)  "例："
set t(readParamFile,errMsg2)  "\$v(paramFile) 的条目行不足，将追加。"
set t(readParamFile,doneMsg)  "已读取 \$v(paramFile)"

# 保存原音参数
set t(saveParamFile,selFile)  "保存原音参数"
set t(saveParamFile,startMsg) "正在保存原音参数… "
set t(saveParamFile,doneMsg)  "已保存原音参数"

# 详细设置
set t(settings,title)        "高级设置"
set t(settings,wave)         "<波形>"
set t(settings,waveColor)    "波形颜色："
set t(settings,waveScale)    "纵轴最大坐标(0-32768,0=自动缩放)"
set t(settings,sampleRate)   "采样率（单位：Hz）："
set t(settings,spec)         "<频谱>"
set t(settings,specColor)    "频谱颜色："
set t(settings,maxFreq)      "最高频率（单位：Hz）："
set t(settings,brightness)   "明亮度："
set t(settings,contrast)     "对比度："
set t(settings,fftLength)    "FFT长度（单位：采样）："
set t(settings,fftWinLength) "窗口宽度（单位：采样）："
set t(settings,fftPreemph)   "预加重："
set t(settings,fftWinKind)   "窗口类型"
set t(settings,pow)          "<响度>"
set t(settings,powColor)     "响度曲线颜色："
set t(settings,powLength)    "响度采样单位（单位：秒）："
set t(settings,powPreemph)   "预加重："
set t(settings,winLength)    "窗口宽度（单位：秒）："
set t(settings,powWinKind)   "窗口类型："
set t(settings,f0)           "<F0（音高）>"
set t(settings,f0Color)      "F0曲线颜色："
set t(settings,f0Argo)       "分析算法："
set t(settings,f0Length)     "F0采样率（单位：秒）："
set t(settings,f0WinLength)  "窗口宽度（单位：秒）："
set t(settings,f0Max)        "最大F0（单位：Hz）："
set t(settings,f0Min)        "最小F0（单位：Hz）："
set t(settings,f0Unit)       "显示单位："
set t(settings,f0FixRange)   "聚焦显示区域："
set t(settings,f0FixRange,h) "最大："
set t(settings,f0FixRange,l) "最小："
set t(settings,grid)         "显示钢琴格"
set t(settings,gridColor)    "钢琴格颜色："
set t(settings,target)       "显示目标音高"
set t(settings,targetTone)   "目标音高："
set t(settings,targetColor)  "目标音高颜色："
set t(settings,autoSetting)  "根据目标改变参数："

# 开始录音
set t(recStart,msg) "录音中..."
set t(recStart,errPa)  "开始录音出错。"

# 开始自动录音
set t(aRecStart,errPa)  "开始录音出错。"

# 停止自动录音
set t(aRecStop,errPa)  "停止录音出错。"

# PortAudio录音
set t(paRecRun,errMsg) "无法启动录音功能"
set t(paRecRun,errDev) "没有可用的录音设备"

# PortAudio播放
set t(paPlayRun,errMsg) "无法启动播放功能"
set t(paPlayRun,errDev) "没有可用的播放设备"

# 停止录音
set t(recStop,msg)  "录音停止"
set t(recStop,errPa)  "停止录音出错。"

# 保存文件并退出
set t(Exit,q2) "当前显示的波形尚未保存。要怎么做？"
set t(Exit,a1) "保存并退出"
set t(Exit,a2) "不保存退出"
set t(Exit,a3) "不退出"

# 右键菜单
set t(PopUpMenu,showWave)   "显示波形"
set t(PopUpMenu,showSpec)   "显示频谱"
set t(PopUpMenu,showPow)    "显示响度"
set t(PopUpMenu,showF0)     "显示F0（音高）"
set t(PopUpMenu,pitchGuide) "显示音叉窗口"
set t(PopUpMenu,tempoGuide) "显示节拍器"
set t(PopUpMenu,settings)   "高级设置"
set t(PopUpMenu,zoomTitle)  "横轴放大"
set t(PopUpMenu,zoom100)    "1倍 (显示整个wav)"
set t(PopUpMenu,zoom1000)   "10倍"
set t(PopUpMenu,zoom5000)   "50倍"
set t(PopUpMenu,zoom10000)  "100倍"
set t(PopUpMenu,zoomMax)    "最大放大率"

# 版本信息
set t(Version,msg) "版本信息"

# 初始化ParamU
set t(initParamU,0) "音"
set t(initParamU,1) "左空白"
set t(initParamU,2) "overlap"
set t(initParamU,3) "先行发声"
set t(initParamU,4) "固定范围"
set t(initParamU,5) "右空白"
set t(initParamU,6) "别名"

# 备注搜索窗口
set t(searchComment,title)     "搜索"
set t(searchComment,search)    "搜索"
set t(searchComment,rup)       "向开头搜索"
set t(searchComment,rdown)     "向末尾搜索"
set t(searchComment,doneTitle) "搜索结束"
set t(searchComment,doneMsg)   "未找到。"
set t(searchComment,rMatch1)   "完全匹配"
set t(searchComment,rMatch2)   "部分匹配"

# 按键分配设置窗口
set t(bindWindow,record)      "开始＆停止录音"
set t(bindWindow,recStop)     "停止自动录音"
set t(bindWindow,nextRec)     "下一个录音"
set t(bindWindow,prevRec)     "上一个录音"
set t(bindWindow,nextType)    "下一个录音类型"
set t(bindWindow,prevType)    "上一个录音类型"
set t(bindWindow,nextRec0)    "(不保存录音)下一个录音"
set t(bindWindow,prevRec0)    "(不保存录音)上一个录音"
set t(bindWindow,nextType0)   "(不保存录音)下一个录音类型"
set t(bindWindow,prevType0)   "(不保存录音)上一个录音类型"
set t(bindWindow,togglePlay)  "播放声音"
set t(bindWindow,toggleOnsaPlay)   "播放音叉"
set t(bindWindow,toggleMetroPlay)  "播放节拍器"
set t(bindWindow,searchComment)    "搜索备注"
set t(bindWindow,waveReload)  "重新读取波形"
set t(bindWindow,waveExpand)  "放大"
set t(bindWindow,waveShrink)  "缩小"
set t(bindWindow,ex)          "(例) a, A, Ctrl-a, Alt-a, Ctrl-Alt-a"
set t(bindWindow,ex2)         "(例) space, F1, F2"
set t(bindWindow,ex3)         "※ 即使修改设置，以前分配的快捷键也不会被清除"
set t(bindWindow,errTitle)    "按键设置错误"
set t(bindWindow,errMsg)      "\"无法应用按键设置( \$value )\""

# 字体大小设置窗口
set t(fontWindow,attention)   "重启后生效"
set t(fontWindow,attention2)  "若设置了 autoSaveInitFile=0 则不会生效"
set t(fontWindow,lbfs)        "录音项的字体大小"
set t(fontWindow,lfs)         "录音列表的字体大小"
set t(fontWindow,lcfs)        "备注栏的字体大小"

# 读取setParam格式的备注
set t(isSetparamComment,q) "\"将与 \$iniFile 一起作为setParam格式的备注文件读取。确定吗？\""
