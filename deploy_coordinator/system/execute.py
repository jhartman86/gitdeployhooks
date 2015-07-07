#!/usr/bin/env python
# -*- coding: utf-8 -*-
import subprocess, sys

class Execute(object):

	options = {
		'streamResponse': False
	}

	def __init__(self, args, options={}):
		self.exec_args = args
		self.options.update(options)
		self.__exec()

	# @todo: error handling
	def __exec(self):
		self.process = subprocess.Popen(self.exec_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
		
		if self.options['streamResponse'] is not True:
			self.response, self.error = self.process.communicate()
			return
		
		else:
			for line in iter(self.process.stdout.readline, ''):
				self.options['receiveStdOut'](line)
			for line in iter(self.process.stderr.readline, ''):
				self.options['receiveStdErr'](line)
			self.process.communicate()[0]


class Git(Execute):

	def __init__(self, args, options={}):
		execPath = str(Execute(['which', 'git'], {'streamResponse': False}).response.strip())
		super(Git, self).__init__([execPath] + args, options)


class Composer(Execute):

	def __init__(self, args, options={}):
		execPath = str(Execute(['which', 'composer'], {'streamResponse': False}).response.strip())
		super(Composer, self).__init__([execPath] + args, options)