import os
import subprocess
import codecs
import tempfile
import sys
import re

import sublime
import sublime_plugin

SETTINGS_FILE = 'MultiFormat.sublime-settings'
FORMATTER = 'multiformat'




class PluginUtils:
	def get_pref(key, default=None):
		return sublime.load_settings(SETTINGS_FILE).get(key, default)
	def set_pref(key,value):
		sublime.load_settings(SETTINGS_FILE).set(key, value)
		sublime.save_settings(SETTINGS_FILE)
	def log_lines(data):
		lines = data.splitlines();
		for line in lines:
			PluginUtils.log(line)
	def debug(data):
		if PluginUtils.get_pref('debug'):
			PluginUtils.log(data)
	def log(data):
			print('MultiFormatter: '+ str(data))
	def protectString(data):
		return '"'+data+'"'
	def ensure_defaults():
		defaults = {
			'debug':False,
			'format_on_save': False,
			'bash': '/bin/bash',
			'paths': [],
			'command_map':{},
			'json_max_line': 70,
			'json_sort_options': []
		}
		for key, value in defaults.items():
			if PluginUtils.get_pref(key) == None:
				PluginUtils.set_pref(key,value)

class MultiFormatCommand(sublime_plugin.TextCommand):

	def run(self, edit):
		PluginUtils.ensure_defaults()
		if sys.platform == 'darwin':
			# Store the PATH
			old_path = os.environ['PATH']
			# Store the View Position
			view_position = self.view.viewport_position()
			# Get the contents of the current File
			view_data = sublime.Region(0, self.view.size())
			# Make a Temporal copy of the file:
			# Reason: 'hnp-format' does not support reading from the stdin
			temp_file = self.create_tmp(view_data)
			# Check if the Syntax of the file has a command mapping
			command = self.get_tool_command()
			if command:
				# Syncronically execute 'hnp-format'
				# TODO: execute Asyncronically
				formatter = self.exec(command,temp_file)
				# Check if 'hnp-format' returned as 0(success)
				if formatter == 0:
					# if returned as 0 read the Temporal copy
					formated_RawData = codecs.open(temp_file, mode='r', encoding='utf-8')
					formated_data = formated_RawData.read()
					formated_RawData.close()
					# TODO: See if the Temporal copy is empty, which meant an uncaught erroneous execution of the 'hnp-format' tool.
					# Compare if the contents of the Temporal copy differ from the ones in the current View.
					if formated_data != view_data:
						self.view.replace(edit, view_data, formated_data)
						self.view.set_viewport_position(view_position, False)
						PluginUtils.log('Formatted ' + os.path.basename(temp_file) + ' as ' + command)
					else:
						PluginUtils.log(os.path.basename(temp_file) + ' as ' + command + 'did not required formatting')
				else:
					PluginUtils.log('ERROR ' + os.path.basename(temp_file) + ' as ' + command)
			# Delete the Temporal File
			os.remove(temp_file)
			# Restore the PATH
			os.environ['PATH'] = old_path
		else:
			PluginUtils.log('MultiFormat is OSX exclusive')

	def create_tmp(self, region):
		buffer_text = self.view.substr(region)
		temp_file_name = self.get_file_name()
		if not temp_file_name:
			temp_file_name = 'formatter.tmp'
		temp_file_path = tempfile.gettempdir() +'/'+ temp_file_name
		temp_file = codecs.open(temp_file_path, mode='w', encoding='utf-8')
		temp_file.write(buffer_text)
		temp_file.close()
		return temp_file_path

	def get_tool_command(self):
		syntax = self.view.settings().get('syntax')
		syntax = os.path.basename(syntax)
		syntax = os.path.splitext(syntax)[0]
		syntax = syntax.strip().lower()
		command_map = PluginUtils.get_pref('command_map', {})
		command = command_map.get(syntax)
		if not command:
			command = 'null'
			command_map[syntax] = command
			PluginUtils.set_pref('command_map', command_map)
			PluginUtils.debug('Added \''+syntax+'\' as \'null\' to the command mappings for convinience')
		if command == 'null':
			PluginUtils.debug(self.get_file_name() + ' (as '+syntax+') has not a valid '+FORMATTER+' <command> mapping')
			return False
		if command:
			PluginUtils.debug(self.get_file_name() + ' (as '+syntax+') -> '+ FORMATTER +' <'+command+'>')
			return command
		return False

	def get_file_name(self):
		file_name = self.view.file_name()
		if file_name:
			file_name = os.path.basename(file_name)
			return file_name
		return False

	def get_project_path(self):
		project_path = self.view.window().project_file_name()
		if project_path:
			project_path = os.path.dirname(project_path)
		return project_path

	def get_exec_path(self):
		paths = PluginUtils.get_pref('paths', [])
		if self.get_project_path():
			paths.append(os.path.join(self.get_project_path(),'node_modules', '.bin'))
		paths.append(os.path.join('/usr/local', 'bin'))
		return os.pathsep.join(paths)

	def get_json_options(self):
		# Get the filename
		file_name = self.get_file_name()
		# Get the test options
		tests = PluginUtils.get_pref('json_sort_options')
		# Create an empty dictionary
		order = {}
		# Check if we have a filename
		# Reason: The tests use the filename for matching
		if file_name:
			for test in tests:
				# Get the regExp string
				match = test.get('match', False)
				# if no regExp string, Break
				if not match:
					break
				# if the regExp string is not of type 'str', Break
				if type(match) is not str:
					break
				# Escape the special characters in the regExp string
				# EX: .json -> \.json
				match = re.escape(match)
				# Set the regExp string to anchor at the end
				# EX: \.json -> \.json$
				match = match+'$'
				# Compile the test as a regExp
				test_pattern = re.compile(match)
				# Will break at first match.
				# TODO: Find a way to match the closest value instead of the first match.
				# TODO: Research on 'Leven' implementations on python
				if test_pattern.match(os.path.basename(file_name)):
					PluginUtils.debug('[Match] filename: \''+file_name+'\' against RegEx: \''+match+'\'')
					order['sort'] = test.get('sort')
					order['max_line'] = test.get('max_line')
					break
				else:
					PluginUtils.debug('[Fail] filename: \''+file_name+'\' against RegEx: \''+match+'\'')

		# Coerce the values before returning the dictionary

		# order['sort']
		# if order['sort'] is not in the dictionary set is as False
		if not order.get('sort', False):
			order['sort'] = False
		# if order['sort'] is a list, make it a str
		if type(order['sort']) is list:
			order['sort'] = ','.join(order['sort'])
		# if order['sort'] is not a str or a bool make it false and log an error
		if (type(order['sort']) is not str) and (type(order['sort']) is not bool):
			PluginUtils.log('order[\'sort\'] can only be a string, an array or a boolean, got: '+str(type(order['sort'])))
			order['sort'] = False

		# order['max_line']
		# if order['sort'] is not in the dictionary set as the json_max_line preference value
		if not order.get('max_line', False):
			order['max_line'] = PluginUtils.get_pref('json_max_line')
		# if order['sort'] is not an int set as the json_max_line preference value
		if type(order['max_line']) is not int:
			order['max_line'] = PluginUtils.get_pref('json_max_line')
		# coerce as str before returning
		order['max_line'] = str(order['max_line'])

		return order

	def exec(self, command, file_path):
		# Build the ENV of the sub-shell
		# Copy the ENV from the current executing context
		exec_env = os.environ.copy()
		# Extend the PATH with common used PATHS
		# See: #get_exec_path()
		exec_env['PATH'] = self.get_exec_path()
		# Add DEBUG accordingly to the plug-in preferences
		if PluginUtils.get_pref('debug'):
			# hnp-format uses the prefix 'Autoformat'
			# NOTE: The * enables the whole namespace
			# EX: Autoformat:javascript will be active too
			exec_env['DEBUG'] = 'MultiFormat*'

		# Get the sub-shell
		# TODO: learn to trust my own pref checker and stop providing a default value to the getter.
		exec_shell = PluginUtils.get_pref('bash','/bin/bash')

		# Set up the shell command
		# EX: hnp-format <command> [options] <filepath>
		# create an empty array
		cmd = []
		# append the hnp-format executable
		cmd.append(FORMATTER)
		# append the <command>
		cmd.append(command)
		# append the [options]

		# option --chdir <path>
		# Used by hnp-format to locate the rc-files from the internal tools
		# EX: esformatter.js looks for a .esformatter file in the CWD
		project_path = self.get_project_path()
		if project_path:
			cmd.append('--chdir')
			cmd.append(PluginUtils.protectString(project_path))

		# if the command is 'json' look for syntax specific options
		if command == 'json':
			# Get the options
			# See: #get_json_options()
			options = self.get_json_options()

			# option --sort <sortOrder>
			# If present hnp-format will sort the keys of the object
			# NOTE: The sorting has a recursion of 3 levels
			if options['sort']:
				cmd.append('--sort')
				cmd.append(PluginUtils.protectString(options['sort']))

			# option --max-line <int>
			# If present hnp-format will use the value to set the maximum fixed character width.
			# See: https://github.com/gre/json-beautify#with-80-fixed-spaces
			cmd.append('--max-line')
			cmd.append(options['max_line'])
		# option --silent
		# Avoid excessive logging
		cmd.append('--silent')
		# append the <filepath>
		cmd.append(PluginUtils.protectString(file_path))

		# cast the array as a command string
		cmd = ' '.join(cmd)
		PluginUtils.debug(cmd)

		# Execute
		# if success return 0
		try:
			output = subprocess.check_output(
				[exec_shell, '-l', '-c', cmd],
				stderr=subprocess.STDOUT,
				stdin=None,
				startupinfo=None,
				env=exec_env,
				shell=False
				)
			PluginUtils.log_lines(output.decode('utf-8'))
			return 0
		# if error return 1
		except subprocess.CalledProcessError as err:
		 	PluginUtils.log_lines(err.output.decode('utf-8'))
		 	return 1

class MultiFormatEventListeners(sublime_plugin.EventListener):
	@staticmethod
	def on_pre_save(view):
		if PluginUtils.get_pref('format_on_save'):
			view.run_command('multi_format')







