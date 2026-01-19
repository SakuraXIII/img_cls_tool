@echo off
:: 支持中文字符
chcp 65001 >nul
echo "删除已有程序"
del ImgCls.exe
echo "开始编译打包"
D:\miniforge\envs\common\Scripts\pyinstaller.exe --icon=assets/256xicon.ico --windowed --onefile --collect-all customtkinter --name ImgCls main.py
echo "编译完成"
move dist\ImgCls.exe .
rd /s /q build
rd /s /q dist
del ImgCls.spec
pause