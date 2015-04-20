#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys, os, json

class ParseJson:

	def __init__(self, jsonFilePath):
		fileHandle = open(jsonFilePath)
		self.data = json.load(fileHandle)
		fileHandle.close()

	# Pass in a string to get it from the JSON file
	# eg: ParseJson().key('nested.params.infinite')
	def key(self, key):
		value = None
		_dict = self.data
		_keys = key.split('.')

		if len(_keys) == 1:
			return _dict.get(_keys[0], None)

		_last = None
		for index, item in enumerate(_keys):
			if isinstance(_dict.get(item,None), dict):
				_dict = _dict.get(item)
			_last = item
		return _dict.get(_last, None)