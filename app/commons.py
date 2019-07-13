import json
import os
import pathlib
import subprocess
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from xml.dom.minidom import parse, Node


class AppConfig(dict):
    """ Helper class for working with app config. """
    CONFIG_PATH = str(Path.home()) + "/.config/ffmpeg-gtk/"
    CONFIG_FILE = CONFIG_PATH + "config.json"
    pathlib.Path(CONFIG_PATH).mkdir(parents=True, exist_ok=True)
    pathlib.Path(CONFIG_FILE).touch(exist_ok=True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if os.path.isfile(AppConfig.CONFIG_FILE) and os.stat(AppConfig.CONFIG_FILE).st_size > 0:
            with open(AppConfig.CONFIG_PATH + "config.json", "r") as config_file:
                self.update(json.load(config_file))

    def save(self):
        with open(AppConfig.CONFIG_FILE, "w") as config_file:
            json.dump(self, config_file)

    @property
    def main_window_size(self):
        if "main_window_size" in self:
            return self["main_window_size"]
        return 560, 320

    @main_window_size.setter
    def main_window_size(self, value):
        self["main_window_size"] = value


class Presets:
    """ Helper class for working with presets. """

    @staticmethod
    def get_default_presets(json_path):
        """ Getting default presets from json file.

            The default presets was taken from WinFF project: https://github.com/WinFF/winff
        """
        with open(json_path, "r") as presets_file:
            return json.load(presets_file)

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
            print(e)
        else:
            return json.loads(str(md, errors="replace")).get("format", {})
        return {}


if __name__ == "__main__":
    pass
