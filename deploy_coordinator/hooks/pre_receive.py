#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
from deploy_coordinator.cli import Formatter, Output
from deploy_coordinator.system.file_system import FileSystem
from deploy_coordinator.system.parse_json import ParseJson
from deploy_coordinator.system.execute import Git

# How this works: the corresponding hook file in the git repo
# just instantiates the PreReceive object declared below, and
# the PreReceive init method passes itself to this function to
# perform any logic / tasks
def preReceiveRunner(PreReceiveInstance):
	# If we're not on master branch, skip the rest of the pre-receive
	if PreReceiveInstance.branchIsMaster() != True:
		sys.exit(0)

	# We are on master; try and clone the buildfile.json
	if PreReceiveInstance.cloneBuildFileToTmpDir() != True:
		Output.multiLine([
			'',
			Formatter('Project must contain buildfile.json in the project root!').color('yellow').indent(),
			Formatter('Commit aborted').color('red').style('bold').indent(),
			''
		])
		PreReceiveInstance.cleanupTmpDir()
		sys.exit(1)

	# Attempt to parse the buildfile (which is cached) and see results
	if PreReceiveInstance.parsedBuildFile() == None:
		Output.multiLine([
			'',
			Formatter('Buildfile contains invalid JSON').color('red'),
			'Push aborted',
			''
		])
		PreReceiveInstance.cleanupTmpDir()
		sys.exit(1)

	# Check the buildfile contains a project name
	projectName = PreReceiveInstance.parsedBuildFile().key('project.name')
	if projectName == None:
		Output.multiLine([
			'',
			'Buildfile ' + Formatter('must').color('red').style(['bold','underline']) + ' contain a project value',
			Formatter('eg: {"project":{"name":"MyProject"},...}').color('yellow'),
			Formatter('Push Aborted').color('red'),
			''
		])
		PreReceiveInstance.cleanupTmpDir()
		sys.exit(1)

	# Commit can proceed to next steps
	Output.multiLine([
		'',
		'-------------------------------------------------------',
		" %s " % Formatter(Output.CHECKMARK).color('green') + "Buildfile parsed OK (%s)" % str(projectName),
		'-------------------------------------------------------',
	])


# Exportable class from the package to organize things, but the
# actual checks/runs happen in the runner() function
class PreReceive(object):

	DEPLOYABLE_BRANCH 	= 'master'
	BUILDFILE_NAME		= 'buildfile.json'

	def __init__(self, inputs):
		(
			self.oldCommitID, 
			self.newCommitID, 
			self.commitRef
		) = inputs.split()
		self.branchName = self.commitRef.split('/')[-1]
		self._hookProcess()

	# Since _hookProcess gets called in init, and we want to
	# have this class be extendable (post-receive), but that will
	# call a different function, we make this method overrideable
	# so the extending class can implement a call to its own
	# ...Runner() method.
	def _hookProcess(self):
		preReceiveRunner(self)

	def branchIsMaster(self):
		return self.branchName == self.DEPLOYABLE_BRANCH

	# @todo: error checking if temp dir creation failed...
	def tmpDir(self):
		if hasattr(self,'_tmpDir') == False:
			self._tmpDir = FileSystem.tempDirFor(self.newCommitID)
		return self._tmpDir

	def cloneBuildFileToTmpDir(self):
		execCall = Git(['--work-tree=%s' % self.tmpDir(),
			'checkout', '-f', self.newCommitID, self.BUILDFILE_NAME
		])
		return (execCall.process.returncode == 0)

	def cleanupTmpDir(self):
		FileSystem.removeDir(self.tmpDir())

	# @return instance of ParseJson
	def parsedBuildFile(self):
		if hasattr(self, '_parsedBuildFile') == False:
			try:
				self._parsedBuildFile = ParseJson(self.tmpDir() + self.BUILDFILE_NAME)
			except ValueError, e:
				self._parsedBuildFile = None
		return self._parsedBuildFile