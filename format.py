import os
import codecs
import tempfile
import sys

from subprocess import PIPE
from subprocess import Popen

from re import sub

import sublime
import sublime_plugin

#
# -------------------------------  Constants  ----------------------------------
#

PLUGIN_PATH = os.path.join(sublime.packages_path(), os.path.dirname(os.path.realpath(__file__)))

PLUGIN_NAME = 'MultiFormat'
PLUGIN_CMD_NAME = 'multi_format'

SETTINGS_MAP = 'formatters'
SETTINGS_FILE = '{0}.sublime-settings'.format(PLUGIN_NAME)
PROJECT_SETTINGS_KEY = 'MultiFormat'

PACKAGE_JSON = 'package.json'

FIND_UP_LIMIT = 5

# ---------------------------  Settings Getters  -------------------------------


def get_setting(key, default_value=None):
    value = sublime.load_settings(SETTINGS_FILE).get(key, default_value)
    # check for project-level overrides:
    project_value = get_project_setting(key)
    # log(value, key + ' settings')
    # log(project_value, key + ' project')

    if project_value is None:
        # log('returning settings', key)
        return value

    if isinstance(value, dict):
        # log('merging', key)
        merged = merge_two_dicts(value, project_value)
        # log(merged, key)
        return merged
    # log('returning project', key)
    return project_value

def get_project_setting(key):
    project_settings = sublime.active_window().active_view().settings()
    if not project_settings:
        return None
    multi_format_settings = project_settings.get(PROJECT_SETTINGS_KEY)

    if multi_format_settings and key in multi_format_settings:
        return multi_format_settings[key]
    return None

def set_syntax_command(syntax, value=None):
    command_map = sublime.load_settings(SETTINGS_FILE).get(SETTINGS_MAP, {})

    if syntax in command_map:
        command_arr = command_map[syntax]
    else:
        command_arr = []

    if value != None:
        command_arr.append(value)

    command_map[syntax] = command_arr

    sublime.load_settings(SETTINGS_FILE).set(SETTINGS_MAP, command_map)
    sublime.save_settings(SETTINGS_FILE)

def get_syntax_command(syntax):
    command_map = get_setting(SETTINGS_MAP, {})
    # log(command_map)
    command = command_map.get(syntax, [])
    if len(command) == 0:
        set_syntax_command(syntax)
    return command


def debug_enabled():
    window = sublime.active_window()
    active_view = window.active_view()
    if active_view:
        return get_setting('debug', False)
    return False





# ---------------------------------  View  -------------------------------------

def get_current_view():
    window = sublime.active_window()
    active_view = window.active_view()
    if active_view:
        return active_view
    return False

# ------------------------------  Directories  ---------------------------------

def get_project_path(source_file_path):
    # we will need a CWD for calling the tools.
    # Is the file in a NPM project??
    project = findFilePath(source_file_path, PACKAGE_JSON, FIND_UP_LIMIT)

    # maybe is in a sublime project
    if project is False:
        project = get_sublime_project_path()

    # Default to the dirname
    if project is False:
        project = get_file_abs_dir(source_file_path)

    return project


def get_sublime_project_path():
    window = sublime.active_window()
    folders = window.folders()
    if len(folders) == 1:
        return folders[0]
    else:
        active_file_name = get_current_file_path()
        if active_file_name:
            for folder in folders:
                if active_file_name.startswith(folder):
                    return folder
    return False

def get_npm_project_path():
    current_file = get_current_file_path()
    if current_file:
        project = findFilePath(current_file, PACKAGE_JSON, FIND_UP_LIMIT)
        if project:
            return project
    return False


# ------------------------------  ENVIROMENT  ----------------------------------
def get_exec_path(base_path):

    paths = []

    if base_path:
        project_path = os.path.join(base_path,'node_modules', '.bin')
        if path_exists(project_path):
            paths.append(project_path)

    # Finally add the current ENV Path
    env_path = os.environ['PATH']
    env_paths = env_path.split(os.pathsep)

    return os.pathsep.join(paths + env_paths)

# -----------------------------  Current File  ---------------------------------

def get_current_file_path():
    window = sublime.active_window()
    active_view = window.active_view()
    if active_view:
        active_file_name = active_view.file_name()
    else:
        active_file_name = None
    if active_file_name:
        return get_file_abs_dir(active_file_name)
    return False

def get_current_scope(view):
    return view.scope_name(view.sel()[0].b)

def get_current_syntax(view):
    syntax = view.settings().get('syntax')
    syntax = os.path.basename(syntax)
    syntax = os.path.splitext(syntax)[0]
    syntax = syntax.strip().lower()
    return syntax

# --------------------------  File System Helpers  -----------------------------

def path_exists(path):
    if not path:
        return False
    if os.path.exists(path):
        return True
    return False

def get_file_abs_dir(filepath):
    return os.path.abspath(os.path.dirname(filepath))

# --------------------------------  Logging  -----------------------------------

def log(msg, header=None):
    if header is None:
        print("{0} | {1}".format(PLUGIN_NAME, msg))
    else:
        msg = add_header(header, msg)
        print("{0} | {1}".format(PLUGIN_NAME, msg))

def log_debug(msg):
    if debug_enabled():
        log(msg)

def add_header(header, msg):
    return "{0}: {1}".format(str(header), str(msg))


def status_message(msg):
    log(msg)
    sublime.set_timeout(lambda: sublime.status_message('{0}: {1}'.format(PLUGIN_NAME, msg)), 0)

def log_lines(data, header='out', log_level=log):
    lines = str(data).splitlines()
    for line in lines:
        log_level(add_header(header,line))

# ---------------------------------  Main  -------------------------------------

class MultiFormatCommand(sublime_plugin.TextCommand):


    def run(self, edit):
        if sys.platform != 'darwin':
            return status_message('You need MacOs to run this plugin')


        source_file_path = self.view.file_name()


        # We need a saved file to do this.
        if source_file_path is None:

            result = sublime.yes_no_cancel_dialog(
                '{0}\n\n'
                'File must first be Saved.'.format(PLUGIN_NAME),
                'Save...', "Don't Save")
            if result == sublime.DIALOG_YES:
                self.view.run_command('save')

        # Re-check if file was saved, in case user canceled or closed the save dialog:
        if source_file_path is None:
            return status_message('Save canceled.')

        # we will need a CWD for calling the tools.
        # Is the file in a NPM project??
        project = findFilePath(source_file_path, PACKAGE_JSON, FIND_UP_LIMIT)

        # maybe is in a sublime project
        if project is False:
            project = get_sublime_project_path()

        # Default to the dirname
        if project is False:
            project = get_file_abs_dir(source_file_path)


        print('----------------------------------------------------')

        log_debug(add_header('file', source_file_path))
        log_debug(add_header('cwd', project))

        # Get the current view code
        region = sublime.Region(0, self.view.size())
        source = self.view.substr(region)
        position = self.view.viewport_position()


        # Fail if nothing to do
        if isEmpty(source):
            return status_message('Nothing to format in file.')

        syntax = get_current_syntax(self.view)
        commands = get_syntax_command(syntax)

        log_debug(add_header('syntax', syntax))

        if not commands:
            return status_message('Not a Supported file')

        log_debug(add_header('commands', commands))

        tmp_file = self.create_tmp(source, source_file_path, project)

        exec_env = os.environ.copy()
        exec_env['PATH'] = get_exec_path(project)

        erroed = False

        for command in commands:
            command = command.split(' ')
            final_command = []

            for part in command:
                if part == '%file':
                    final_command.append(tmp_file)
                else:
                    final_command.append(part)

            erroed = self.format_code(final_command, exec_env, project)

        if erroed is True:
            status_message('One of the tools returned an ERROR')

        transformed = self.read_tmp(tmp_file)

        if trimWhiteSpace(transformed) == trimWhiteSpace(source):
            return status_message('File already formatted.')

        self.view.replace(edit, region, transformed)
        self.view.set_viewport_position(position, False)


        return status_message('File formatted.')



    def create_tmp(self, data, source, project):
        tmp_file_name = os.path.basename(source)
        tmp_file_path = project +'/00000.tmp.'+ tmp_file_name
        tmp_file = codecs.open(tmp_file_path, mode='w', encoding='utf-8')
        tmp_file.write(data)
        tmp_file.close()
        return tmp_file_path


    def read_tmp(self, tmp_file_path):
        tmp_file = codecs.open(tmp_file_path, mode='r', encoding='utf-8')
        data = tmp_file.read()
        tmp_file.close()
        os.remove(tmp_file_path)
        return data

    def format_code(self, cmd, env, cwd):
        try:

            log_debug(add_header('Command',list_to_str(cmd)))

            proc = Popen(
                cmd,
                stderr=PIPE,
                stdout=PIPE,
                stdin=None,
                cwd=cwd,
                env=env,
                shell=False
                )

            stdout, stderr = proc.communicate()

            if proc.returncode != 0:
                log('ERROR ON COMMAND')
                log_lines(stdout.decode('utf-8'), 'out')
                log_lines(stderr.decode('utf-8'), 'err')
                return True

            if stderr:
                log_lines(stderr.decode('utf-8'), 'err')

            if stdout:
                log_lines(stdout.decode('utf-8'), 'out', log_debug)

            return False

        except OSError as ex:
            sublime.error_message('{0} - {1}'.format(PLUGIN_NAME, ex))
            raise

class MultiFormatEventListeners(sublime_plugin.EventListener):
    @staticmethod
    def on_pre_save(view):
        if get_setting('format_on_save', False):
            view.run_command('multi_format')



# ---------------------------------  Utils  ------------------------------------

def climb_dirs(start_dir, limit=None):

    right = True

    while right and (limit is None or limit > 0):
        yield start_dir
        start_dir, right = os.path.split(start_dir)

        if limit is not None:
            limit -= 1

def findFilePath(start_dir, filename, limit=None):
    for d in climb_dirs(start_dir, limit=limit):
        target = os.path.join(d, filename)
        if os.path.exists(target):
            return d
    return False

def isEmpty(txt):
    if not txt or len(txt) == 0:
        return True
    # strip all whitespace/invisible chars to determine textual content:
    txt = sub(r'\s+', '', txt)
    if not txt or len(txt) == 0:
        return True
    return False

def trimWhiteSpace(val):
    if val is None:
        return val
    val = sub(r'\s+\Z', '', val)
    return val


def list_to_str(list_to_convert):
    return ' '.join(str(l) for l in list_to_convert)

def merge_two_dicts(x, y):
    z = x.copy()
    z.update(y)
    return z

def protectString(data):
    return '"'+data+'"'
