#!/usr/bin/env python3
import os
import sys

from app.converter import Application


def update_icon():
    need_update = False

    with open("ffmpeg-gtk.desktop", "r", encoding="utf-8") as f:
        lines = f.readlines()

        for i, line in enumerate(lines):
            if line.startswith("Icon="):
                icon_path = line.lstrip("Icon=")
                current_path = f"{os.getcwd()}/app/img/logo.png"
                if icon_path != current_path:
                    need_update = True
                    lines[i] = f"Icon={current_path}\n"
                break

    if need_update:
        with open("ffmpeg-gtk.desktop", "w", encoding="utf-8") as f:
            f.writelines(lines)


update_icon()
app = Application()
app.run(sys.argv)

