echo "安装包到iquant目录，注意，必须使用single-version-externally-managed，而且，必须要使用--root + --prefix方式，否则，只会安装一个egg文件，不知为何，iquant/QMT是不认的；并且必须要设置一个PYTHONPATH环境变量。总之，很垃圾，QMT！"
set PYTHONPATH=c:\iquant\bin.x64\lib\site-packages\
python setup.py install --single-version-externally-managed --root=\ --prefix=c:\iquant\bin.x64