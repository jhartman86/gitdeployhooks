#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys

class Output:

	CHECKMARK = u'\u2713'.encode('utf-8')

	@staticmethod
	def line(_str, _indented=False):
		space = ''
		if _indented == True:
			space = '        '
		sys.stdout.write('\033[0G' + space + str(_str) + '\n\033[0G\r')
		sys.stdout.flush()

	@classmethod
	def multiLine(cls, _strings, _indented=False):
		for line in _strings:
			cls.line(line, _indented)

	@staticmethod
	def rewrite(_str):
		sys.stdout.write('\033[0G%s\r' % str(_str))
		sys.stdout.flush()