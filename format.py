import os
import codecs
import tempfile
import sys

from subprocess import PIPE
from subprocess import Popen

from re import sub

import sublime
import sublime_plugin

# ───────────────────────────────  Constants  ──────────────────────────────────

PLUGIN_PATH = os.path.join(sublime.packages_path(), os.path.dirname(os.path.realpath(__file__)))

PLUGIN_NAME = 'MultiFormat'
PLUGIN_CMD_NAME = 'multi_format'

SETTINGS_FILE = '{0}.sublime-settings'.format(PLUGIN_NAME)
PROJECT_SETTINGS_KEY = 'multiformat'

PACKAGE_JSON = 'package.json'

FIND_UP_LIMIT = 5

# ───────────────────────────  Settings Getters  ───────────────────────────────

def get_setting(view, key, default_value=None):
    settings = view.settings().get(PLUGIN_NAME)
    if settings is None or settings.get(key) is None:
        settings = sublime.load_settings(SETTINGS_FILE)
    value = settings.get(key, default_value)
    # check for project-level overrides:
    project_value = get_project_setting(key)
    if project_value is None:
        return value
    return project_value

def get_project_setting(key):
    project_settings = sublime.active_window().active_view().settings()
    if not project_settings:
        return None
    multi_format_settings = project_settings.get(PROJECT_SETTINGS_KEY)
    if multi_format_settings and key in multi_format_settings:
        return multi_format_settings[key]
    return None

def debug_enabled(view):
    return bool(get_setting(view, 'debug', False))


# ─────────────────────────────────  View  ─────────────────────────────────────

def scroll_view_to(view, row_no, col_no):
    # error positions are offset by -1
    # prettier -> sublime text
    row_no -= 1
    col_no -= 1

    textpoint = view.text_point(row_no, col_no)
    view.sel().clear()
    view.sel().add(sublime.Region(textpoint))
    view.show_at_center(textpoint)

def get_current_view():
    window = sublime.active_window()
    active_view = window.active_view()
    if active_view:
        return active_view
    return False

# ──────────────────────────────  Directories  ─────────────────────────────────

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
        project = find_file_path(current_file, PACKAGE_JSON, FIND_UP_LIMIT)
        if project:
            return project
    return False

def get_user_home_path():
    return os.path.expanduser('~')

# ──────────────────────────────  ENVIROMENT  ──────────────────────────────────
def get_exec_path(base_path):

    paths = []

    if base_path:
        projectPath = os.path.join(base_path,'node_modules', '.bin')
        if path_exists(projectPath):
            paths.append(projectPath)

    # Finally add the current ENV Path
    envPath = os.environ['PATH']
    envPaths = envPath.split(os.pathsep)

    return os.pathsep.join(paths + envPaths)

# ─────────────────────────────  Current File  ─────────────────────────────────

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


# ──────────────────────────  File System Helpers  ─────────────────────────────

def path_exists(path):
    if not path:
        return False
    if os.path.exists(path):
        return True
    return False

def get_file_abs_dir(filepath):
    return os.path.abspath(os.path.dirname(filepath))

# ────────────────────────────────  Logging  ───────────────────────────────────

def log(msg):
    print("{0} | {1}".format(PLUGIN_NAME, msg))

def log_debug(msg):
    if debug_enabled(get_current_view()):
        log(msg)
    return

def add_header(header, msg):
    return "{0}: {1}".format(str(header), str(msg))


def status_message(msg):
    log(msg)
    sublime.set_timeout(lambda: sublime.status_message('{0}: {1}'.format(PLUGIN_NAME, msg)), 0)

def log_lines(data, header='out', log_level=log):
    lines = str(data).splitlines()
    for line in lines:
        log_level(add_header(header,line))



class MultiFormatCommand(sublime_plugin.TextCommand):

    def run(self, edit):
        if sys.platform == 'darwin':
            view = self.view
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
            project = find_file_path(source_file_path, PACKAGE_JSON, FIND_UP_LIMIT)

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

            # Fail if nothing to do
            if str_empty_or_whitespace_only(source):
                return status_message('Nothing to format in file.')

            tmp_file = self.create_tmp(source, source_file_path, project)

            commands = False
            scopename = view.scope_name(view.sel()[0].b)

            if scopename.startswith('source.js'):
                commands = [
                    ['prettier', tmp_file, '--write'],
                    ['standard', tmp_file, '--fix']
                ]

            if scopename.startswith('source.json'):
                commands = [
                    ['prettier', tmp_file, '--write', '--parser', 'json']
                ]

            if commands is False:
                os.remove(tmp_file)
                return status_message('Not a Supported file')

            exec_env = os.environ.copy()
            exec_env['PATH'] = get_exec_path(project)


            for command in commands:
                results = self.format_code(command, exec_env, project)

            if self.erroed is True:
                os.remove(tmp_file)
                return status_message('ERROR Formating the file')

            formated_file = codecs.open(tmp_file, mode='r', encoding='utf-8')
            transformed = formated_file.read()
            formated_file.close()
            os.remove(tmp_file)

            if trim_trailing_ws_and_lines(transformed) == trim_trailing_ws_and_lines(source):
                return status_message('File already formatted.')

            view.replace(edit, region, transformed)
            status_message('File formatted.')

        else:
            log_warn('MultiFormat is OSX exclusive')

    def create_tmp(self, buffer_text, source_file_name, project_path):
        tmp_file_name = os.path.basename(source_file_name)
        temp_file_path = project_path +'/00000.tmp.'+ tmp_file_name
        temp_file = codecs.open(temp_file_path, mode='w', encoding='utf-8')
        temp_file.write(buffer_text)
        temp_file.close()
        return temp_file_path

    def format_code(self, cmd, env, cwd):
        self.erroed = False

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
                # self.erroed = True
                log('ERROR ON COMMAND')
                log_lines(stdout.decode('utf-8'), 'out')
                log_lines(stderr.decode('utf-8'), 'err')
                return False
            if stderr:
                log_lines(stderr.decode('utf-8'), 'err')
            if stdout:
                log_lines(stdout.decode('utf-8'), 'out', log_debug)
            return True

        except OSError as ex:
            sublime.error_message('{0} - {1}'.format(PLUGIN_NAME, ex))
            raise

class MultiFormatEventListeners(sublime_plugin.EventListener):
    @staticmethod
    def on_pre_save(view):
        if PluginUtils.get_pref('format_on_save'):
            view.run_command('multi_format')



# ─────────────────────────────────  Utils  ────────────────────────────────────

def climb_dirs(start_dir, limit=None):

    right = True

    while right and (limit is None or limit > 0):
        yield start_dir
        start_dir, right = os.path.split(start_dir)

        if limit is not None:
            limit -= 1

def find_file_path(start_dir, filename, limit=None):
    for d in _climb_dirs(start_dir, limit=limit):
        target = os.path.join(d, filename)
        if os.path.exists(target):
            return d
    return False

def str_empty_or_whitespace_only(txt):
    if not txt or len(txt) == 0:
        return True
    # strip all whitespace/invisible chars to determine textual content:
    txt = sub(r'\s+', '', txt)
    if not txt or len(txt) == 0:
        return True
    return False

def trim_trailing_ws_and_lines(val):
    if val is None:
        return val
    val = sub(r'\s+\Z', '', val)
    return val


def list_to_str(list_to_convert):
    return ' '.join(str(l) for l in list_to_convert)


