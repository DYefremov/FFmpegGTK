import locale
import mimetypes
import os
import re
import subprocess
from datetime import timedelta
from enum import IntEnum
from functools import wraps
from pathlib import Path
from threading import Thread

import gi

from app.commons import Presets, AppConfig, FFmpeg

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gio, GLib, Gdk

UI_RESOURCES_PATH = "app/" if os.path.exists("app/") else "/usr/share/ffmpeggtk/app/"

IS_GNOME_SESSION = int(bool(os.environ.get("GNOME_DESKTOP_SESSION_ID")))

DURATION_PATTERN = re.compile(r"(.*Duration:)?.*(\d{2}):(\d{2}):(\d{2}.\d{2}).*")

# translation
TEXT_DOMAIN = "ffmpeg-gtk"
if UI_RESOURCES_PATH == "app/":
    LANG_DIR = UI_RESOURCES_PATH + "lang"
    locale.bindtextdomain(TEXT_DOMAIN, UI_RESOURCES_PATH + "lang")


def get_localized_message(message):
    return locale.dgettext(TEXT_DOMAIN, message)


class Column(IntEnum):
    """ Column nums in the view """
    ICON = 0
    FILE = 1
    DURATION = 2
    PROGRESS = 3
    SELECTED = 4
    IN_PROGRESS = 5


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
                    "on_category_changed": self.on_category_changed,
                    "on_source_state_set": self.on_source_state_set,
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
                    "on_resize": self.on_resize,
                    "on_convert": self.on_convert,
                    "on_cancel": self.on_cancel,
                    "on_query_tooltip": self.on_query_tooltip,
                    "on_category_add": self.on_category_add,
                    "on_category_edit": self.on_category_edit,
                    "on_category_remove": self.on_category_remove,
                    "on_category_restore_defaults": self.on_category_restore_defaults,
                    "on_profile_add": self.on_profile_add,
                    "on_profile_edit": self.on_profile_edit,
                    "on_profile_remove": self.on_profile_remove,
                    "on_options_add": self.on_options_add,
                    "on_options_apply": self.on_options_apply,
                    "on_options_cancel": self.on_options_cancel}

        self._config = AppConfig()
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
        self._main_window.resize(*self._config.main_window_size)
        self._file_tree_view = builder.get_object("file_tree_view")
        self._files_model = builder.get_object("files_list_store")
        self._details_text_view = builder.get_object("details_text_view")
        self._category_combo_box = builder.get_object("category_combo_box")
        self._category_name_entry = builder.get_object("category_name_entry")
        self._profile_combo_box = builder.get_object("profile_combo_box")
        self._profile_box = builder.get_object("profile_box")
        self._output_main_box = builder.get_object("output_main_box")
        self._options_ok_button = builder.get_object("options_ok_button")
        self._options_add_button = builder.get_object("options_add_button")
        self._options_apply_button = builder.get_object("options_apply_button")
        self._options_cancel_button = builder.get_object("options_cancel_button")
        self._profile_name_entry = builder.get_object("profile_name_entry")
        self._profile_params_entry = builder.get_object("profile_params_entry")
        self._profile_extension_entry = builder.get_object("profile_extension_entry")
        self._output_folder_chooser = builder.get_object("output_folder_chooser")
        self._overwrite_if_exists_switch = builder.get_object("overwrite_if_exists_switch")
        self._convert_button = builder.get_object("convert_button")
        self._add_files_button = builder.get_object("add_files_button")
        self._add_files_main_menu_button = builder.get_object("add_files_main_menu_button")
        self._count_label = builder.get_object("count_label")
        self._info_bar = builder.get_object("info_bar")
        self._info_bar_message_label = builder.get_object("info_bar_message_label")
        self._output_box = builder.get_object("output_box")
        # File filter with specified MIME types
        self._file_filter = builder.get_object("file_filter")
        self._mime_types = mimetypes.MimeTypes()
        self._mime_icon_video = Gtk.IconTheme.get_default().load_icon("video-x-generic", 24, 0)
        self._mime_icon_audio = Gtk.IconTheme.get_default().load_icon("audio-x-generic", 24, 0)
        # Tooltip
        self._file_tree_view.set_has_tooltip(True)
        # Category (4 = G_BINDING_INVERT_BOOLEAN)
        profile_label = builder.get_object("profile_label")
        category_menu_button = builder.get_object("category_menu_button")
        self._category_name_entry.bind_property("visible", self._options_cancel_button, "visible")
        self._category_name_entry.bind_property("visible", self._options_ok_button, "visible", 4)
        self._category_name_entry.bind_property("visible", self._output_main_box, "sensitive", 4)
        self._category_name_entry.bind_property("visible", profile_label, "sensitive", 4)
        self._category_name_entry.bind_property("visible", category_menu_button, "sensitive", 4)
        self._category_name_entry.bind_property("visible", self._category_combo_box, "visible", 4)
        self._category_name_entry.bind_property("visible", builder.get_object("profile_main_box"), "sensitive", 4)
        # Profile
        self._profile_box.bind_property("visible", self._options_cancel_button, "visible")
        self._options_cancel_button.bind_property("visible", self._options_apply_button, "visible")
        self._options_cancel_button.bind_property("visible", self._options_add_button, "visible")
        self._profile_combo_box.bind_property("visible", self._category_combo_box, "sensitive")
        self._profile_combo_box.bind_property("visible", self._output_main_box, "visible")
        self._profile_combo_box.bind_property("visible", self._options_ok_button, "visible")
        self._profile_combo_box.bind_property("visible", profile_label, "visible")
        self._profile_combo_box.bind_property("visible", category_menu_button, "visible")
        self._profile_combo_box.bind_property("visible", builder.get_object("profile_menu_button"), "visible")
        # Header bar
        self._convert_button.bind_property("visible", builder.get_object("cancel_button"), "visible", 4)
        self._convert_button.bind_property("visible", builder.get_object("options_menu_button"), "sensitive")
        self._convert_button.bind_property("visible", builder.get_object("add_files_button"), "sensitive")
        self._convert_button.bind_property("visible", builder.get_object("add_files_main_menu_button"), "sensitive")
        self._convert_button.bind_property("visible", builder.get_object("remove_popup_item"), "sensitive")

    def do_startup(self):
        Gtk.Application.do_startup(self)
        self.init_convert_elements()
        try:
            subprocess.check_output(["ffprobe", "-help"], stderr=subprocess.STDOUT)
        except FileNotFoundError as e:
            msg = get_localized_message("Check if FFmpeg is installed!")
            self.show_info_message("Error. {} {}".format(e, msg), Gtk.MessageType.ERROR)
            self._add_files_button.set_sensitive(False)
            self._add_files_main_menu_button.set_sensitive(False)

    def do_activate(self):
        self._main_window.set_application(self)
        self._main_window.set_wmclass("FFmpegGTK", "FFmpegGTK")
        self._main_window.present()

    def do_shutdown(self):
        """  Performs shutdown tasks """
        self._config.save()
        Presets.save(self._presets)
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
        self._presets = Presets.get_presets()
        if not self._presets:
            self._presets = Presets.get_default_presets(UI_RESOURCES_PATH + "presets.json")
        list(map(self._category_combo_box.append_text, sorted(self._presets)))

    def on_add_files(self, button):
        dialog = Gtk.FileChooserDialog("", self._main_window, Gtk.FileChooserAction.OPEN,
                                       (Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE, Gtk.STOCK_ADD, Gtk.ResponseType.NO),
                                       use_header_bar=IS_GNOME_SESSION, select_multiple=True, modal=True)
        dialog.set_filter(self._file_filter)
        dialog.connect("response", self.add_files_callback)
        dialog.show()

    def add_files_callback(self, dialog, response):
        if response == Gtk.ResponseType.NO:
            gen = self.append_files(dialog.get_filenames())
            GLib.idle_add(lambda: next(gen, False))
        else:
            dialog.destroy()

    def append_files(self, files):
        for f in files:
            mime = self._mime_types.guess_type(f)[0]
            if mime:
                is_video = "video" in mime
                icon = self._mime_icon_video if is_video else self._mime_icon_audio
                yield self._files_model.append((icon, f, self.get_duration(f), None, True, False))

    def on_remove(self, item=None):
        model, paths = self._file_tree_view.get_selection().get_selected_rows()
        for itr in [model.get_iter(p) for p in paths]:
            del model[itr]

    def on_category_changed(self, box):
        options = self._presets.get(box.get_active_text())
        self._profile_combo_box.get_model().clear()
        if options:
            list(map(self._profile_combo_box.append_text, options.keys()))

    def on_source_state_set(self, switch, state):
        self._output_folder_chooser.set_sensitive(not state)

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
            if self._in_progress:
                msg = "This operation is not allowed during the conversion process!"
                self.show_info_message(msg, Gtk.MessageType.ERROR)
                return

            self.on_remove()

    def on_info_bar_close(self, bar, resp=None):
        bar.hide()

    def on_file_model_changed(self, model, path, iter=None):
        size = len(model)
        self._convert_button.set_sensitive(size)
        self._count_label.set_text(str(size))

    def on_show_output_switch(self, switch, state):
        self._output_box.set_visible(state)

    def on_about(self, button):
        builder = Gtk.Builder()
        builder.set_translation_domain(TEXT_DOMAIN)
        builder.add_objects_from_file(UI_RESOURCES_PATH + "converter.glade", ("about_dialog",))
        dialog = builder.get_object("about_dialog")
        dialog.set_transient_for(self._main_window)
        dialog.run()
        dialog.destroy()

    def on_exit(self, window=None, event=None):
        if self._in_progress and not self.on_cancel():
            return True

        self._main_window.destroy()

    def on_resize(self, window):
        """ Stores new size properties for app window after resize """
        self._config.main_window_size = window.get_size()

    def on_convert(self, item):
        self._info_bar.hide()
        fmt = self._category_combo_box.get_active_text()
        option = self._profile_combo_box.get_active_text()
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

        for index, row in enumerate(self._files_model):
            in_file = row[Column.FILE]
            in_path = Path(in_file)
            out_path = str(in_path.parent) + os.sep if use_source_folder else base_path + os.sep
            out_file = "{}{}.{}".format(out_path, in_path.stem, extension)

            if in_file == out_file:
                out_file = "{}CONVERTED!_{}.{}".format(out_path, in_path.stem, extension)

            commands.append((["ffmpeg", "-i", in_file, *opts, overwrite, out_file], index))

        self.convert(commands)

    @run_task
    def convert(self, commands):
        try:
            self.update_active_buttons(False)
            self._in_progress = True

            for command, path in commands:
                if not self._in_progress:
                    break

                try:
                    itr = self._files_model.get_iter(path)
                except ValueError:
                    continue

                if not self._files_model.get_value(itr, Column.SELECTED):
                    continue

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

    def on_cancel(self, item=None):
        dialog = Gtk.MessageDialog(self._main_window, True, Gtk.MessageType.QUESTION,
                                   (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OK, Gtk.ResponseType.OK),
                                   get_localized_message("Are you sure?"))
        is_ok = dialog.run() == Gtk.ResponseType.OK
        if is_ok:
            self._in_progress = False
            if self._current_process:
                self._current_process.terminate()
            self.show_info_message("Task canceled.", Gtk.MessageType.WARNING)
        dialog.destroy()

        return is_ok

    def on_query_tooltip(self, view: Gtk.TreeView, x, y, keyboard_mode, tooltip: Gtk.Tooltip):
        """  Sets extended info about file in the tooltip. """
        result = view.get_path_at_pos(x, y)
        if result is None:
            return False

        path, column, _x, _y = result
        tooltip.set_icon(self._files_model[path][Column.ICON])
        tooltip.set_text(self.get_file_info(self._files_model[path][Column.FILE]))
        view.set_tooltip_row(tooltip, path)

        return True

    # ********** Options ***********

    def on_category_add(self, item):
        self._category_name_entry.set_text("")
        self._category_name_entry.set_visible(True)
        self._options_apply_button.set_visible(False)

    def on_category_edit(self, item):
        category = self._category_combo_box.get_active_text()
        if not category:
            self.show_info_message("No category selected!", Gtk.MessageType.ERROR)
            return

        self._category_name_entry.set_visible(True)
        self._options_add_button.set_visible(False)
        self._category_name_entry.set_text(category)

    def on_category_remove(self, item):
        category = self._category_combo_box.get_active_text()
        if not category:
            self.show_info_message("No category selected!", Gtk.MessageType.ERROR)
            return

        self._presets.pop(category, None)
        self._category_combo_box.remove(self._category_combo_box.get_active())

    def on_category_restore_defaults(self, item):
        self._presets = Presets.get_default_presets(UI_RESOURCES_PATH + "presets.json")
        self._category_combo_box.remove_all()
        list(map(self._category_combo_box.append_text, sorted(self._presets)))
        self.show_info_message("Done!", Gtk.MessageType.INFO)

    def on_profile_add(self, item):
        category = self._category_combo_box.get_active_text()
        if not category:
            self.show_info_message("No category selected!", Gtk.MessageType.ERROR)
            return

        self.update_active_option_elements(True)
        self._options_apply_button.set_visible(False)
        self.update_profile_entries()

    def on_profile_edit(self, item):
        category = self._category_combo_box.get_active_text()
        if not category:
            self.show_info_message("No category selected!", Gtk.MessageType.ERROR)
            return

        profile = self._profile_combo_box.get_active_text()
        if not profile:
            self.show_info_message("No profile selected!", Gtk.MessageType.ERROR)
            return

        self.update_active_option_elements(True)
        self._options_add_button.set_visible(False)
        p_data = self._presets.get(category).get(profile)
        self.update_profile_entries(profile, p_data.get("params"), p_data.get("extension"))

    def on_profile_remove(self, item):
        profile = self._profile_combo_box.get_active_text()
        if not profile:
            self.show_info_message("No profile selected!", Gtk.MessageType.ERROR)
            return

        category = self._presets.get(self._category_combo_box.get_active_text())
        category.pop(profile, None)
        self.on_category_changed(self._category_combo_box)

    def on_options_add(self, button, event):
        return self.category_add() if self._category_name_entry.get_visible() else self.profile_add()

    def category_add(self):
        category_name = self._category_name_entry.get_text()
        if category_name in self._presets:
            self.show_info_message("Category with this name already exists!", Gtk.MessageType.ERROR)
            return True

        self._category_name_entry.set_visible(False)
        self._presets[category_name] = {}
        self.update_categories(category_name)

        return True

    def update_categories(self, active_category):
        self._category_combo_box.remove_all()
        cat_index = 0
        for index, c in enumerate(sorted(self._presets)):
            if c == active_category:
                cat_index = index
            self._category_combo_box.append_text(c)
        self._category_combo_box.set_active(cat_index)
        self.on_category_changed(self._category_combo_box)

    def profile_add(self):
        category = self._presets.get(self._category_combo_box.get_active_text())
        profile_name = self._profile_name_entry.get_text()
        if profile_name in category:
            self.show_info_message("Profile with this name already exists!", Gtk.MessageType.ERROR)
            return True

        prf = {"params": self._profile_params_entry.get_text(), "extension": self._profile_extension_entry.get_text()}
        category[profile_name] = prf
        self.on_category_changed(self._category_combo_box)
        self._profile_combo_box.set_active_id(profile_name)
        self.show_info_message("Profile successfully added!", Gtk.MessageType.INFO)

        return True

    def on_options_apply(self, button, event):
        self.category_options_apply() if self._category_name_entry.get_visible() else self.profile_options_apply()

        return self.on_options_cancel()

    def category_options_apply(self):
        category_name = self._category_combo_box.get_active_text()
        new_name = self._category_name_entry.get_text()
        if category_name != new_name:
            self._presets[new_name] = self._presets.pop(category_name, {})
            self.update_categories(new_name)

    def profile_options_apply(self):
        category_name = self._category_combo_box.get_active_text()
        category = self._presets.get(category_name)
        current_name = self._profile_combo_box.get_active_text()
        new_name = self._profile_name_entry.get_text()
        profile = category.pop(current_name) if current_name != new_name else category.get(current_name)
        profile["params"] = self._profile_params_entry.get_text()
        profile["extension"] = self._profile_extension_entry.get_text()
        category[new_name] = profile
        self.on_category_changed(self._category_combo_box)
        self._profile_combo_box.set_active_id(new_name)

    def on_options_cancel(self, button=None, event=None):
        """"  Returns True to prevent the popover menu from closing. """
        if self._category_name_entry.get_visible():
            self._category_name_entry.set_visible(False)
            return True

        self.update_active_option_elements(False)
        self._category_combo_box.set_sensitive(True)

        return True

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
        self._info_bar_message_label.set_text(get_localized_message(text))

    @run_idle
    def update_active_buttons(self, active):
        self._convert_button.set_visible(active)

    def update_active_option_elements(self, active):
        self._profile_box.set_visible(active)
        if active:
            self._profile_box.set_size_request(self._output_main_box.get_allocated_width(), 0)
        self._profile_combo_box.set_visible(not active)

    def update_profile_entries(self, name="", params="", extension=""):
        self._profile_name_entry.set_text(name)
        self._profile_params_entry.set_text(params)
        self._profile_extension_entry.set_text(extension)

    @staticmethod
    def get_duration(path):
        metadata = FFmpeg.get_metadata(path)
        return str(timedelta(seconds=int(float(metadata.get("duration", 0)))))

    @staticmethod
    def get_file_info(path):
        """ Returns file info from the metadata. """
        md = FFmpeg.get_metadata(path)
        info = ["{}: {}".format(k.replace("_", " ").capitalize(), v) for k, v in md.items() if type(v) is str]

        return "\n".join(info)


if __name__ == "__main__":
    pass
