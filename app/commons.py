# -*- coding: utf-8 -*-
#
# Copyright (C) 2019-2023 Dmitriy Yefremov
#
# This file is part of FFmpegGTK.
#
# FFmpegGTK is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# FFmpegGTK is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with FFmpegGTK.  If not, see <http://www.gnu.org/licenses/>.
#
# Author: Dmitriy Yefremov
#


import json
import logging
import os
import pathlib
import subprocess
from collections import defaultdict
from functools import lru_cache, wraps
from pathlib import Path
from threading import Thread

from xml.dom.minidom import parse, Node

from gi.repository import GLib

_LOG_FILE = "FFmpegGTK.log"
LOG_DATE_FORMAT = "%d-%m-%y %H:%M:%S"
LOGGER_NAME = "main_logger"
LOG_FORMAT = "%(asctime)s %(message)s"


def init_logger():
    logging.Logger(LOGGER_NAME)
    handlers = [logging.FileHandler(_LOG_FILE), logging.StreamHandler()]
    logging.basicConfig(level=logging.INFO,
                        format=LOG_FORMAT,
                        datefmt=LOG_DATE_FORMAT,
                        handlers=handlers)
    log("Logging enabled.", level=logging.INFO)


def log(message, level=logging.ERROR):
    """ The main logging function. """
    logger = logging.getLogger(LOGGER_NAME)
    logger.log(level, message)


def run_task(func):
    """ Runs function in separate thread """

    @wraps(func)
    def wrapper(*args, **kwargs):
        task = Thread(target=func, args=args, kwargs=kwargs, daemon=True)
        task.start()

    return wrapper


def run_idle(func):
    """ Runs a function with a lower priority """

    @wraps(func)
    def wrapper(*args, **kwargs):
        GLib.idle_add(func, *args, **kwargs)

    return wrapper


class AppConfig(dict):
    """ Helper class for working with app config. """
    CONFIG_PATH = f"{Path.home()}/.config/ffmpeg-gtk/"
    CONFIG_FILE = f"{CONFIG_PATH}config.json"
    pathlib.Path(CONFIG_PATH).mkdir(parents=True, exist_ok=True)
    pathlib.Path(CONFIG_FILE).touch(exist_ok=True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if os.path.isfile(AppConfig.CONFIG_FILE) and os.stat(AppConfig.CONFIG_FILE).st_size > 0:
            with open(AppConfig.CONFIG_FILE, "r") as config_file:
                self.update(json.load(config_file))

    def save(self):
        with open(AppConfig.CONFIG_FILE, "w") as config_file:
            json.dump(self, config_file)

    @property
    def main_window_size(self):
        return self.get("main_window_size", (560, 320))

    @main_window_size.setter
    def main_window_size(self, value):
        self["main_window_size"] = value

    @property
    def category(self):
        return self.get("category", -1)

    @category.setter
    def category(self, value):
        self["category"] = value

    @property
    def profile(self):
        return self.get("profile", -1)

    @profile.setter
    def profile(self, value):
        self["profile"] = value

    @property
    def output_folder(self):
        return self.get("output_folder", "")

    @output_folder.setter
    def output_folder(self, value):
        self["output_folder"] = value

    @property
    def use_source_folder(self):
        return self.get("use_source_folder", False)

    @use_source_folder.setter
    def use_source_folder(self, value):
        self["use_source_folder"] = value

    @property
    def overwrite_existing(self):
        return self.get("overwrite_existing", False)

    @overwrite_existing.setter
    def overwrite_existing(self, value):
        self["overwrite_existing"] = value


class Presets:
    """ Helper class for working with presets. """

    @staticmethod
    def get_presets():
        presets_file = AppConfig.CONFIG_PATH + "presets.json"
        if os.path.isfile(presets_file) and os.stat(presets_file).st_size > 0:
            return Presets.get_default_presets(presets_file)

    @staticmethod
    def get_default_presets(json_path):
        """ Getting default presets from json file.

            The default presets was taken from WinFF project: https://github.com/WinFF/winff
        """
        with open(json_path, "r") as presets_file:
            return json.load(presets_file)

    @staticmethod
    def save(presets: dict):
        presets_file = AppConfig.CONFIG_PATH + "presets.json"
        with open(presets_file, "w") as presets_file:
            return json.dump(presets, presets_file, indent=2)

    @staticmethod
    def convert_presets_xml_to_json(xml_path, json_path):
        """ Converts WinFF presets from xml to json. """
        dom = parse(xml_path)
        for elem in dom.getElementsByTagName("presets"):
            presets = []
            if elem.hasChildNodes():
                for n in elem.childNodes:
                    if n.nodeType == Node.ELEMENT_NODE:
                        preset = {}
                        for ch in n.childNodes:
                            if ch.nodeType == Node.ELEMENT_NODE:
                                if ch.hasChildNodes():
                                    preset[ch.nodeName] = ch.childNodes[0].data
                        presets.append(preset)

            out = defaultdict(dict)
            list(map(lambda p: out[p["category"]].update(
                {p["label"]: {"params": p["params"], "extension": p["extension"]}}), presets))

            with open(json_path, "w") as config_file:
                json.dump(out, config_file, indent=2)


class FFmpeg:

    @staticmethod
    @lru_cache(maxsize=10)
    def get_metadata(path):
        """ Returns metadata from the file. """
        try:
            md = subprocess.check_output(
                ["ffprobe", "-i", path, "-v", "quiet", "-print_format", "json", "-show_format"])
        except subprocess.CalledProcessError as e:
            log(e)
        else:
            return json.loads(str(md, errors="replace")).get("format", {})
        return {}

    @staticmethod
    def get_image_data(path, pos):
        try:
            md = subprocess.check_output(["ffmpeg", "-ss", pos, "-i", path, "-v", "quiet", "-frames:v", "1",
                                          "-s", "360x240", "-f", "image2", "pipe: | cat"])
        except subprocess.CalledProcessError as e:
            log(e)
        else:
            return md


if __name__ == "__main__":
    pass
