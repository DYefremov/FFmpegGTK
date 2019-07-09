import json
from collections import defaultdict
from xml.dom.minidom import parse, Node


def get_default_presets(json_path):
    """ Getting default presets from json file.

        The default presets was taken from WinFF project: https://github.com/WinFF/winff
    """
    with open(json_path, "r") as presets_file:
        return json.load(presets_file)


def convert_presets_xml_to_json(xml_path, json_path):
    """ Helper method for converting WinFF presets from xml to json. """
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
        list(
            map(lambda p: out[p["category"]].update({p["label"]: {"params": p["params"], "extension": p["extension"]}}),
                presets))

        with open(json_path, "w") as config_file:
            json.dump(out, config_file, indent=2)


if __name__ == "__main__":
    pass
