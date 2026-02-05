#!/usr/bin/env python3
# simple-apt-update - A GUI for basic tasks of package management using apt
# Copyright (C) 2023  Tilman Kranz <t.kranz@tk-sls.de>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

##
# Imports

import gi
import html
import logging
import os
import queue
import re
import selectors
import signal
import subprocess
import sys
import threading

gi.require_version('Gdk', '3.0')
gi.require_version('Gtk', '3.0')

try:
    from gi.repository import Gio
except ImportError:
    logging.error("Could not import Gio")
    sys.exit(1)

try:
    from gi.repository import GLib
except ImportError:
    logging.error("Could not import Gio")
    sys.exit(1)

try:
    from gi.repository import Gtk
except ImportError:
    logging.error("Could not import Gtk")
    sys.exit(1)


##
# Classes

class UpdateWindow(Gtk.ApplicationWindow):
    def clear(self):
        self.buffer.set_text("")

    def scroll_to_bottom(self):
        adj = self.scrolledwindow.get_vadjustment()
        adj.set_value(adj.get_upper())
        self.scrolledwindow.set_vadjustment(adj)

    def level_to_color(self, level):
        if level == "INFO":
            return "green"
        elif level == "ERROR":
            return "red"
        else:
            return "grey"

    def prepend_mesg(self, level, text):
        self.prepend(text)
        self.prepend_color(level + ": ", self.level_to_color(level))

    def append_mesg(self, level, text):
        self.append_color(level + ": ", self.level_to_color(level))
        self.append(text)

    def prepend_markup(self, markup):
        self.insert_markup(markup, self.buffer.get_start_iter())

    def append_markup(self, markup):
        self.insert_markup(markup, self.buffer.get_end_iter())

    def insert_markup(self, markup, iter):
        self.buffer.insert_markup(iter, markup, -1)

    def prepend_color(self, text, color):
        self.insert_color(text, color, self.buffer.get_start_iter())

    def append_color(self, text, color):
        self.insert_color(text, color, self.buffer.get_end_iter())

    def insert_color(self, text, color, iter):
        self.buffer.insert_markup(
            iter,
            "<span color=\"%s\">%s</span>" % (color, html.escape(text)),
            -1)

    def prepend(self, text):
        self.insert(text, self.buffer.get_start_iter())

    def append(self, text):
        self.insert(text, self.buffer.get_end_iter())
        self.scroll_to_bottom()

    def insert(self, text, iter):
        self.buffer.insert(iter, text + "\n")

    def execute(self, args, ignore_stderr=False, output_msg=None,
                empty_msg=None, env={}, clear=True):
        self.lock()

        if clear:
            self.clear()

        self.output_msg = output_msg
        self.empty_msg = empty_msg
        self.ignore_stderr = ignore_stderr
        self.stdout = ''
        self.stderr = ''
        self.prepend_mesg(
            "INFO",
            "Running command \"%s\" ..." % " ".join(args))
        thread = threading.Thread(target=self.run, args=(args, env,))
        thread.start()

    def run(self, args, env={}):
        p = subprocess.Popen(
            args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False,
            env=dict(os.environ, **env))

        sel = selectors.DefaultSelector()
        sel.register(p.stdout, selectors.EVENT_READ)
        sel.register(p.stderr, selectors.EVENT_READ)
        done = False

        while not done:
            for key, _ in sel.select():
                data = key.fileobj.read1().decode().rstrip()

                if data:
                    if key.fileobj is p.stdout:
                        self.stdout_queue.put(data)
                    else:
                        self.stderr_queue.put(data)

                exit_code = p.poll()

                if exit_code is not None:
                    self.stdout_queue.put("EXIT %d" % exit_code)
                    done = True
                    break

    def lock(self):
        self.update_button.set_sensitive(False)
        self.upgrade_button.set_sensitive(False)
        self.list_button.set_sensitive(False)
        self.spinner.start()

    def unlock(self):
        self.update_button.set_sensitive(True)
        self.upgrade_button.set_sensitive(True)
        self.list_button.set_sensitive(True)
        self.spinner.stop()

    def upgrade(self):
        args = ['/usr/bin/apt', '-yqq', 'full-upgrade']
        env = {'DEBIAN_FRONTEND': 'noninteractive'}
        self.execute(
            args,
            env=env,
            empty_msg="No package upgrades were performed.")

    def on_upgrade(self, *args):
        self.upgrade()

    def update(self, clear=True):
        args = ['/usr/bin/apt', '-y', 'update']
        env = {'DEBIAN_FRONTEND': 'noninteractive'}
        self.execute(args, env=env, clear=clear)

    def on_update(self, *args):
        self.update()

    def list(self, clear=True):
        args = ['/usr/bin/apt', '-qq', 'list', '--upgradable']
        self.execute(
            args,
            ignore_stderr=True,
            clear=clear,
            output_msg="Found the following package upgrades:",
            empty_msg="Comando executado!")

    def on_list(self, *args):
        self.list()

    def on_quit(self, *args):
        self.application.quit()

    def update_buffer(self):
        try:
            text = self.stdout_queue.get(block=False)
            match = re.fullmatch(r'EXIT (\d+)', text)

            if match is None:
                self.stdout += text
                self.append_mesg("STDOUT", text)
            else:
                exit_code = int(match.group(1))

                if exit_code != 0:
                    self.append_mesg(
                        "ERROR",
                        "Command exited with code %d" % exit_code)
                elif self.stdout == '' and self.empty_msg is not None:
                    self.append_mesg("INFO", self.empty_msg)
                elif self.stdout != '' and self.output_msg is not None:
                    self.append_mesg("INFO", self.empty_msg)

                self.unlock()

        except queue.Empty:
            pass

        try:
            text = self.stderr_queue.get(block=False)

            self.stderr += text

            if not self.ignore_stderr:
                self.append_mesg("STDERR", text)
        except queue.Empty:
            pass

        return True

    def __init__(self, application):
        super(UpdateWindow, self).__init__(
            application=application,
            title="Atualizar Softwares e Drivers")
        self.application = application
        self.stdout_queue = queue.Queue()
        self.stderr_queue = queue.Queue()
        GLib.timeout_add(100, self.update_buffer)
        self.init_ui()

    def init_ui(self):
        self.set_border_width(10)
        self.set_default_size(630, 390)

        hbox = Gtk.Box(spacing=6, orientation=Gtk.Orientation.VERTICAL)
        self.add(hbox)

        grid = Gtk.Grid()
        grid.set_row_spacing(5)
        grid.set_column_spacing(5)
        hbox.add(grid)

        self.update_button = Gtk.Button.new_with_label(
            "Atualizar o Cache")
        self.update_button.connect("clicked", self.on_update)
        grid.attach(self.update_button, 0, 0, 1, 1)

        self.list_button = Gtk.Button.new_with_label(
            "Listar Atualizações")
        self.list_button.connect("clicked", self.on_list)
        grid.attach(self.list_button, 1, 0, 1, 1)

        self.upgrade_button = Gtk.Button.new_from_icon_name(
            "gtk-apply", Gtk.IconSize.BUTTON)
        self.upgrade_button.set_tooltip_text(
            "Baixar e instalar todas as atualizações disponíveis")
        self.upgrade_button.connect("clicked", self.on_upgrade)
        grid.attach(self.upgrade_button, 2, 0, 1, 1)

        self.spinner = Gtk.Spinner()
        self.spinner.set_hexpand(True)
        grid.attach(self.spinner, 3, 0, 1, 1)

        self.quit_button = Gtk.Button.new_from_icon_name(
            "exit", Gtk.IconSize.BUTTON)
        self.quit_button.set_tooltip_text("Sair do programa")
        self.quit_button.set_halign(Gtk.Align.END)
        self.quit_button.connect("clicked", self.on_quit)
        grid.attach(self.quit_button, 4, 0, 1, 1)

        self.scrolledwindow = Gtk.ScrolledWindow()
        self.scrolledwindow.set_hexpand(True)
        self.scrolledwindow.set_vexpand(True)
        self.scrolledwindow.set_min_content_height(300)
        self.scrolledwindow.set_max_content_height(300)
        self.buffer = Gtk.TextBuffer()

        text_view = Gtk.TextView(buffer=self.buffer)
        text_view.set_editable(False)
        text_view.set_monospace(True)
        text_view.set_cursor_visible(False)

        self.scrolledwindow.add(text_view)
        hbox.pack_start(self.scrolledwindow, True, True, 0)


class SimpleAptUpdate(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='de.linuxfoo.SimpleAptUpdate',
                         flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.connect('activate', self.on_activate)
        signal.signal(signal.SIGINT, signal.SIG_DFL)

    def do_command_line(self, cmdline):
        pass

    def on_activate(self, application):
        self.window = UpdateWindow(application)

        action = Gio.SimpleAction.new("quit", None)
        action.connect("activate", self.window.on_quit)
        self.add_action(action)
        self.set_accels_for_action('app.quit', ['<Primary>q', '<Primary>w'])

        action = Gio.SimpleAction.new("update", None)
        action.connect("activate", self.window.on_update)
        self.add_action(action)
        self.set_accels_for_action('app.update', ['<Primary>u'])

        action = Gio.SimpleAction.new("upgrade", None)
        action.connect("activate", self.window.on_upgrade)
        self.add_action(action)
        self.set_accels_for_action('app.upgrade', ['<Primary>g'])

        action = Gio.SimpleAction.new("list", None)
        action.connect("activate", self.window.on_list)
        self.add_action(action)
        self.set_accels_for_action('app.list', ['<Primary>l'])

        self.window.present()
        self.window.show_all()
        self.window.update()
        self.window.list(clear=False)


##
# Main Program

def main():
    application = SimpleAptUpdate()
    exit_status = application.run()
    sys.exit(exit_status)


if __name__ == '__main__':
    main()
