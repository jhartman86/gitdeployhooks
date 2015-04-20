#!/usr/bin/env python
# -*- coding: utf-8 -*-
import subprocess, sys

class Execute(object):

	def __init__(self, args):
		self.exec_args = args
		self.__exec()
		#self.result = self.__exec()

	# @todo: error handling
	def __exec(self):
		self.process = subprocess.Popen(self.exec_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
		self.response, self.error = self.process.communicate()
		#out, err = p.communicate()
		#return out


class Git(Execute):

	def __init__(self, args):
		execPath = str(Execute(['which', 'git']).response.strip())
		super(Git, self).__init__([execPath] + args)


class Composer(Execute):

	def __init__(self, args):
		execPath = str(Execute(['which', 'composer']).response.strip())
		super(Composer, self).__init__([execPath] + args)