#!/usr/bin/env python3
import os
import sys

from app.converter import Application


def update_icon():
    need_update = False

    with open("FFmpegGTK.desktop", "r") as f:
        lines = f.readlines()

        for i, line in enumerate(lines):
            if line.startswith("Icon="):
                icon_path = line.lstrip("Icon=")
                current_path = "{}/app/img/logo.png".format(os.getcwd())
                if icon_path != current_path:
                    need_update = True
                    lines[i] = "Icon={}\n".format(current_path)
                break

    if need_update:
        with open("FFmpegGTK.desktop", "w") as f:
            f.writelines(lines)


update_icon()
app = Application()
app.run(sys.argv)

