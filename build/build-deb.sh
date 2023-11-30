#!/bin/bash
VER="0.1.2_Alpha"
B_PATH="dist/FFmpegGTK"
DEB_PATH="$B_PATH/usr/share/ffmpeg-gtk"

mkdir -p $B_PATH
cp -TRv deb $B_PATH
rsync -arv ../app/lang/* "$B_PATH/usr/share/locale"
rsync --exclude=app/img --exclude=app/lang --exclude=__pycache__ -arv ../app $DEB_PATH

cd dist
fakeroot dpkg-deb -Zxz --build FFmpegGTK
mv FFmpegGTK.deb FFmpegGTK_$VER.deb

rm -R FFmpegGTK
