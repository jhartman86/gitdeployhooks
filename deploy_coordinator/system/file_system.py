#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys, os, shutil, tempfile

class FileSystem:

	@classmethod
	def tempDirFor(cls, name):
		fullPath = tempfile.gettempdir() + '/deploy_coord/%s' % name + '/'
		if not os.path.exists(fullPath):
			os.makedirs(fullPath)
		return fullPath

	@staticmethod
	def removeDir(name):
		shutil.rmtree(name)

	@staticmethod
	def mvFromTo(src,dst):
		shutil.move(src,dst)

	@staticmethod
	def isSymlink(what):
		return os.path.islink(what)

	@staticmethod
	def genSymlink(target, linkName):
		os.symlink(target, linkName)

	# File or symlink
	@staticmethod
	def remove(target):
		os.remove(target)

	# Purges only directories
	@classmethod
	def purgeOtherDirectoriesInDirectoryExcept(cls, _dir, exceptedItems=[]):
		dirItems = os.listdir(_dir)
		for item in dirItems:
			fullPath = os.path.abspath(os.path.join(_dir, item))
			if cls.isSymlink(fullPath) == True:
				continue
			if item in exceptedItems:
				continue
			if os.path.isdir(fullPath) == False:
				continue
			# If we get here, it can be deleted
			cls.removeDir(fullPath)

	# Does a file (specifically... it must be a file) exist
	@staticmethod
	def fileExists(path):
		return os.path.isfile(path)

	# Does the thing at the path exist? (path or directory)
	@staticmethod
	def exists(path):
		return os.path.exists(path)