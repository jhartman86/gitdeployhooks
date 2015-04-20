#!/usr/bin/env python
# -*- coding: utf-8 -*-

class Formatter:

	STYLES = {
		'bold':'1m',
		'underline':'4m'
	}

	COLORS = {
		'green':'92m',
		'red':'91m',
		'yellow':'33m',
		'cyan':'36m'		
	}

	def __init__(self, _str):
		self.string = _str

	def __str__(self):
		return self.string

	def __add__(self, other):
		return str(self) + str(other)

	def __radd__(self, other):
		return str(other) + str(self)

	def style(self, style):
		if isinstance(style, list):
			for _style in style:
				self.string = '\033[%s%s\033[0m' % (self.STYLES[_style], self.string)
		else:
			self.string = '\033[%s%s\033[0m' % (self.STYLES[style], self.string)
		return self

	def color(self, color):
		self.string = '\033[%s%s\033[0m' % (self.COLORS[color], self.string)
		return self

	def indent(self):
		self.string = '\033[\010m        %s\033[0m' % self.string
		return self

	def arrowed(self):
		self.string = '\033[\010m------> %s\033[0m' % self.string
		return self

	# @classmethod
	# def _bold(cls, _str):
	# 	return '\033[%s%s\033[0m' % (cls.FORMAT_BOLD, _str)

	# @classmethod
	# def _underline(cls, _str):
	# 	return '\033[%s%s\033[0m' % (cls.FORMAT_UNDERLINE, _str)

	# @classmethod
	# def _red(cls, _str):
	# 	return '\033[%s%s\033[0m' % (cls.COLOR_RED, _str)

	# @classmethod
	# def _yellow(cls, _str):
	# 	return '\033[%s%s\033[0m' % (cls.COLOR_YELLOW, _str)

	# @classmethod
	# def _cyan(cls, _str):
	# 	return '\033[%s%s\033[0m' % (cls.COLOR_CYAN, _str)

	# @classmethod
	# def _green(cls, _str):
	# 	return '\033[%s%s\033[0m' % (cls.COLOR_GREEN, _str)