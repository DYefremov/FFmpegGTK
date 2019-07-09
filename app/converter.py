import locale
import mimetypes
import os
import re
import subprocess
from enum import IntEnum
from functools import wraps
from pathlib import Path
from threading import Thread

import gi

from app.commons import get_default_presets

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gio, GLib, Gdk

UI_RESOURCES_PATH = "app/" if os.path.exists("app/") else "/usr/share/ffmpeggtk/app/ui/"

IS_GNOME_SESSION = int(bool(os.environ.get("GNOME_DESKTOP_SESSION_ID")))

DURATION_PATTERN = re.compile(r"(.*Duration:)?.*(\d{2}):(\d{2}):(\d{2}.\d{2}).*")

# translation
TEXT_DOMAIN = "ffmpeg-gtk"
if UI_RESOURCES_PATH == "":
    LANG_DIR = UI_RESOURCES_PATH + "lang"
    locale.bindtextdomain(TEXT_DOMAIN, UI_RESOURCES_PATH + "lang")


class Column(IntEnum):
    """ Column nums in the view """
    ICON = 0
    FILE = 1
    PROGRESS = 2
    SELECTED = 3
    IN_PROGRESS = 4


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


def init_logger():
    print("init log test")


class Application(Gtk.Application):

    def __init__(self, **kwargs):
        super().__init__(flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE, **kwargs)
        # Adding command line options
        self.add_main_option("log", ord("l"), GLib.OptionFlags.NONE, GLib.OptionArg.NONE, "", None)

        handlers = {"on_add_files": self.on_add_files,
                    "on_remove": self.on_remove,
                    "on_convert_to_changed": self.on_convert_to_changed,
                    "on_source_state_set": self.on_source_state_set,
                    "on_options_apply": self.on_options_apply,
                    "on_selected_toggled": self.on_selected_toggled,
                    "on_select_all": self.on_select_all,
                    "on_unselect": self.on_unselect,
                    "on_popup_menu": self.on_popup_menu,
                    "on_key_press": self.on_key_press,
                    "on_info_bar_close": self.on_info_bar_close,
                    "on_file_model_changed": self.on_file_model_changed,
                    "on_show_output_switch": self.on_show_output_switch,
                    "on_about": self.on_about,
                    "on_exit": self.on_exit,
                    "on_convert": self.on_convert,
                    "on_cancel": self.on_cancel}

        self._presets = None
        self._current_process = None
        self._in_progress = False
        self._duration = 0
        self._current_itr = None

        builder = Gtk.Builder()
        builder.set_translation_domain(TEXT_DOMAIN)
        builder.add_from_file(UI_RESOURCES_PATH + "converter.glade")
        builder.connect_signals(handlers)
        self._main_window = builder.get_object("main_window")
        self._file_tree_view = builder.get_object("file_tree_view")
        self._files_model = builder.get_object("files_list_store")
        self._details_text_view = builder.get_object("details_text_view")
        self._convert_to_combo_box = builder.get_object("convert_to_combo_box")
        self._convert_options_combo_box = builder.get_object("convert_options_combo_box")
        self._output_folder_chooser = builder.get_object("output_folder_chooser")
        self._overwrite_if_exists_switch = builder.get_object("overwrite_if_exists_switch")
        self._convert_button = builder.get_object("convert_button")
        self._cancel_button = builder.get_object("cancel_button")
        self._count_label = builder.get_object("count_label")
        self._info_bar = builder.get_object("info_bar")
        self._info_bar_message_label = builder.get_object("info_bar_message_label")
        self._output_box = builder.get_object("output_box")
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
        self._presets = get_default_presets(UI_RESOURCES_PATH + "presets.json")
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
                    icon = self._mime_icon_video if is_video else self._mime_icon_audio
                    self._files_model.append((icon, p, None, True, False))

        dialog.destroy()

    def on_remove(self, item=None):
        model, paths = self._file_tree_view.get_selection().get_selected_rows()
        for itr in [model.get_iter(p) for p in paths]:
            del model[itr]

    def on_convert_to_changed(self, box):
        options = self._presets.get(box.get_active_text())
        self._convert_options_combo_box.get_model().clear()
        list(map(self._convert_options_combo_box.append_text, options.keys()))

    def on_source_state_set(self, switch, state):
        self._output_folder_chooser.set_sensitive(not state)

    def on_options_apply(self, button):
        pass

    def on_selected_toggled(self, toggle, path):
        self._files_model.set_value(self._files_model.get_iter(path), Column.SELECTED, not toggle.get_active())

    def on_select_all(self, view):
        self._files_model.foreach(lambda md, path, itr: md.set_value(itr, Column.SELECTED, True))

    def on_unselect(self, item):
        model, paths = self._file_tree_view.get_selection().get_selected_rows()
        list(map(lambda path: model.set_value(model.get_iter(path), Column.SELECTED, False), paths))

    def on_popup_menu(self, menu, event):
        if event.get_event_type() == Gdk.EventType.BUTTON_PRESS and event.button == Gdk.BUTTON_SECONDARY:
            menu.popup(None, None, None, None, event.button, event.time)
            return True

    def on_key_press(self, view, event_key):
        """  Handling  keystrokes  """
        key_value = event_key.keyval

        if key_value in (Gdk.KEY_space, Gdk.KEY_KP_Space):
            path, column = view.get_cursor()
            itr = self._files_model.get_iter(path)
            selected = self._files_model.get_value(itr, Column.SELECTED)
            self._files_model.set_value(itr, Column.SELECTED, not selected)
        elif key_value in (Gdk.KEY_Delete, Gdk.KEY_KP_Delete):
            self.on_remove()

    def on_info_bar_close(self, bar, resp):
        bar.hide()

    def on_file_model_changed(self, model, path, iter=None):
        size = len(model)
        self._convert_button.set_sensitive(size)
        self._count_label.set_text(str(size))

    def on_show_output_switch(self, switch, state):
        self._output_box.set_visible(state)

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

    def on_convert(self, item):
        self._info_bar.hide()
        fmt = self._convert_to_combo_box.get_active_text()
        option = self._convert_options_combo_box.get_active_text()
        if not fmt and not option:
            self.show_info_message("Error. Check the settings!", Gtk.MessageType.ERROR)
            return

        use_source_folder = not self._output_folder_chooser.get_sensitive()
        base_path = self._output_folder_chooser.get_filename()
        if not use_source_folder and not base_path:
            self.show_info_message("Error. Output folder is not set!", Gtk.MessageType.ERROR)
            return

        GLib.idle_add(self._details_text_view.get_buffer().set_text, "")

        prm = self._presets.get(fmt).get(option)
        opts = prm.get("params").split(" ")
        extension = prm["extension"]
        commands = []
        # option to overwrite output file if exists
        overwrite = "-y" if self._overwrite_if_exists_switch.get_state() else "-n"

        for row in filter(lambda r: r[Column.SELECTED], self._files_model):
            in_file = row[Column.FILE]
            in_path = Path(in_file)
            out_path = str(in_path.parent) + os.sep if use_source_folder else base_path + os.sep
            out_file = "{}{}.{}".format(out_path, in_path.stem, extension)

            if in_file == out_file:
                out_file = "{}CONVERTED!_{}.{}".format(out_path, in_path.stem, extension)

            commands.append((["ffmpeg", "-i", in_file, *opts, overwrite, out_file], row.iter))

        self.convert(commands)

    @run_task
    def convert(self, commands):
        try:
            self.update_active_buttons(False)
            self._in_progress = True

            for command, itr in commands:
                if not self._in_progress:
                    break

                self._current_process = subprocess.Popen(command,
                                                         stdout=subprocess.PIPE,
                                                         stderr=subprocess.PIPE,
                                                         universal_newlines=True)
                if self._current_itr:
                    GLib.idle_add(self._files_model.set_value, self._current_itr, Column.PROGRESS, 100)

                self._current_itr = itr
                GLib.idle_add(self._files_model.set_value, itr, Column.IN_PROGRESS, True)
                GLib.io_add_watch(self._current_process.stderr, GLib.IO_IN, self.write_to_buffer)
                self._current_process.wait()
                self._files_model.set_value(itr, Column.SELECTED, False)
        finally:
            self.update_active_buttons(True)
            if self._in_progress:
                self._in_progress = False
                self.show_info_message("Done!", Gtk.MessageType.INFO)
                GLib.idle_add(self._files_model.set_value, self._current_itr, Column.PROGRESS, 100)

    def on_cancel(self, item):
        dialog = Gtk.MessageDialog(self._main_window, True, Gtk.MessageType.QUESTION,
                                   (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OK, Gtk.ResponseType.OK),
                                   "Are you sure?", use_header_bar=IS_GNOME_SESSION)
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            self._in_progress = False
            if self._current_process:
                self._current_process.terminate()
            self.show_info_message("Task canceled.", Gtk.MessageType.WARNING)
        dialog.destroy()

    def write_to_buffer(self, fd, condition):
        if condition == GLib.IO_IN:
            line = fd.readline()
            d_res = re.match(DURATION_PATTERN, line)
            if d_res:
                duration = d_res.group(1)
                d_time = sum((int(d_res.group(2)) * 3600, int(d_res.group(3)) * 60, float(d_res.group(4))))
                if duration:
                    self._duration = d_time
                elif self._duration > 0:
                    d_time = sum((int(d_res.group(2)) * 3600, int(d_res.group(3)) * 60, float(d_res.group(4))))
                    done = d_time * 100 / self._duration
                    self._files_model.set_value(self._current_itr, Column.PROGRESS, done)
                else:
                    pass  # (NOP) May be error in the duration detection. TODO: Think about processing

            self.append_output(line)
            return True
        return False

    @run_idle
    def append_output(self, char):
        """ Appending text and scrolling  to a given line in the text view. """
        buf = self._details_text_view.get_buffer()
        buf.insert_at_cursor(char)
        insert = buf.get_insert()
        self._details_text_view.scroll_to_mark(insert, 0.0, True, 0.0, 1.0)

    @run_idle
    def show_info_message(self, text, message_type):
        self._info_bar.set_visible(True)
        self._info_bar.set_message_type(message_type)
        self._info_bar_message_label.set_text(text)

    @run_idle
    def update_active_buttons(self, active):
        self._convert_button.set_visible(active)
        self._cancel_button.set_visible(not active)


if __name__ == "__main__":
    pass
