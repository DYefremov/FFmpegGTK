import locale
import mimetypes
import os
import sys
from enum import IntEnum

import gi

from app.commons import get_default_presets

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gio, GLib, Gdk

UI_RESOURCES_PATH = "./"

IS_GNOME_SESSION = int(bool(os.environ.get("GNOME_DESKTOP_SESSION_ID")))

# translation
TEXT_DOMAIN = "svf-converter"
if UI_RESOURCES_PATH == "":
    LANG_DIR = UI_RESOURCES_PATH + "lang"
    locale.bindtextdomain(TEXT_DOMAIN, UI_RESOURCES_PATH + "lang")


class Column(IntEnum):
    """ Column nums in the view """
    ICON = 0
    FILE = 1
    SELECTED = 2


def init_logger():
    print("init log test")


class Application(Gtk.Application):

    def __init__(self, **kwargs):
        super().__init__(flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE, **kwargs)
        # Adding command line options
        self.add_main_option("log", ord("l"), GLib.OptionFlags.NONE, GLib.OptionArg.NONE, "", None)

        handlers = {"on_add_files": self.on_add_files,
                    "on_convert_to_changed": self.on_convert_to_changed,
                    "on_source_state_set": self.on_source_state_set,
                    "on_options_apply": self.on_options_apply,
                    "on_selected_toggled": self.on_selected_toggled,
                    "on_popup_menu": self.on_popup_menu,
                    "on_about": self.on_about,
                    "on_exit": self.on_exit}

        self._presets = None

        builder = Gtk.Builder()
        builder.set_translation_domain("vsf-converter")
        builder.add_from_file(UI_RESOURCES_PATH + "converter.glade")
        builder.connect_signals(handlers)
        self._main_window = builder.get_object("main_window")
        self._files_model = builder.get_object("files_list_store")
        self._convert_to_combo_box = builder.get_object("convert_to_combo_box")
        self._convert_options_combo_box = builder.get_object("convert_options_combo_box")
        self._output_folder_chooser = builder.get_object("output_folder_chooser")
        # File filter with specified MIME types
        self._file_filter = builder.get_object("file_filter")
        self._mime_types = mimetypes.MimeTypes()
        self._mime_icon_video = Gtk.IconTheme.get_default().load_icon("video-x-generic", 24, 0)
        self._mime_icon_audio = Gtk.IconTheme.get_default().load_icon("audio-x-generic", 24, 0)

    def do_startup(self):
        Gtk.Application.do_startup(self)
        self.init_convert_elements()

    def do_activate(self):
        self._main_window.set_application(self)
        self._main_window.set_wmclass("FFmpegGTK", "FFmpegGTK")
        self._main_window.present()

    def do_shutdown(self):
        """  Performs shutdown tasks """
        Gtk.Application.do_shutdown(self)

    def do_command_line(self, command_line):
        """ Processing command line parameters. """
        options = command_line.get_options_dict()
        options = options.end().unpack()
        if "log" in options:
            init_logger()

        self.activate()
        return 0

    def init_convert_elements(self):
        self._presets = get_default_presets("presets.json")
        list(map(self._convert_to_combo_box.append_text, sorted(self._presets)))

    def on_add_files(self, button):
        dialog = Gtk.FileChooserDialog("", self._main_window, Gtk.FileChooserAction.OPEN,
                                       (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK),
                                       use_header_bar=IS_GNOME_SESSION, select_multiple=True)
        dialog.set_filter(self._file_filter)

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            for p in dialog.get_filenames():
                mime = self._mime_types.guess_type(p)[0]
                if mime:
                    is_video = "video" in mime
                    self._files_model.append((self._mime_icon_video if is_video else self._mime_icon_audio, p, True))

        dialog.destroy()

    def on_convert_to_changed(self, box: Gtk.ComboBoxText):
        options = self._presets.get(box.get_active_text())
        self._convert_options_combo_box.get_model().clear()
        list(map(lambda op: self._convert_options_combo_box.append_text(op["label"]), options))

    def on_source_state_set(self, switch, state):
        self._output_folder_chooser.set_sensitive(not state)

    def on_options_apply(self, button):
        print("Apply settings.")

    def on_selected_toggled(self, toggle, path):
        self._files_model.set_value(self._files_model.get_iter(path), Column.SELECTED, not toggle.get_active())

    def on_popup_menu(self, menu, event):
        if event.get_event_type() == Gdk.EventType.BUTTON_PRESS and event.button == Gdk.BUTTON_SECONDARY:
            menu.popup(None, None, None, None, event.button, event.time)
            return True

    def on_about(self, button):
        builder = Gtk.Builder()
        builder.set_translation_domain("vsf-converter")
        builder.add_objects_from_file(UI_RESOURCES_PATH + "converter.glade", ("about_dialog",))
        dialog = builder.get_object("about_dialog")
        dialog.set_transient_for(self._main_window)
        dialog.run()
        dialog.destroy()

    def on_exit(self, item):
        self._main_window.destroy()


if __name__ == "__main__":
    app = Application()
    app.run(sys.argv)
