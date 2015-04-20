#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys, os
from pre_receive import PreReceive
from deploy_coordinator.cli import Formatter, Output
from deploy_coordinator.system.execute import Git, Composer
from deploy_coordinator.system.file_system import FileSystem

# These should be parsed/determined from somewhere...
# bundleDir	= '/home/jon/Desktop/sandbox/'
# vhostTarget	= bundleDir + 'ln-release'
# permDir 	= bundleDir + '_permanent/'
# webDir 		= bundleDir + '_application/'

# How this works: the corresponding hook file in the git repo
# just instantiates the PreReceive object declared below, and
# the PreReceive init method passes itself to this function to
# perform any logic / tasks
def postReceiveRunner(PostReceiveInstance):
	# Check branch name
	if PostReceiveInstance.branchIsMaster() != True:
		Output.multiLine([
			'',
			Formatter('Only master branches are deployed; but your branch push was recieved.').color('yellow'),
			Formatter('Push completed').color('cyan'),
			''
		])
		sys.exit(0)
	else:
		Output.multiLine([
			Formatter(
				"Commit Accepted, branch: " + 
				Formatter(PostReceiveInstance.branchName).style('underline') + 
				Formatter(" [%s...]" % PostReceiveInstance.newCommitID[0:10]).color('cyan')
			).arrowed(),
			''
		])

	# Ensure directory structure is in place (os.makedirS creates all directories
	# leading up to the leaf)
	try:
		if not os.path.exists(PostReceiveInstance.buildDir):
			os.makedirs(PostReceiveInstance.buildDir)
		if not os.path.exists(PostReceiveInstance.locPermanentDirs):
			os.makedirs(PostReceiveInstance.locPermanentDirs)
		if not os.path.exists(PostReceiveInstance.locAppBundle):
			os.makedirs(PostReceiveInstance.locAppBundle)
	except:
		Output.line(Formatter('Unable to create bundle directory for project').color('red').indent())

	# Copy to /tmp directory so we can monkey with code there
	try:
		Output.line(Formatter('Cloning code to tmp dir').arrowed())
		# Clone the entire project to a tmp directory and check it worked
		if PostReceiveInstance.cloneProjectToTmpDir() != True:
			raise Exception('FAILED')
	except Exception as e:
		Output.line(Formatter(e.args[0]).color('red').indent())
		sys.exit(0)

	# Pre-processing (eg. remove data dirs, setup symlinks to permanent storage)
	try:
		Output.line(Formatter('Applying buildfile rules').indent())
		# Work on permanent storage dirs
		permStorageDirs = PostReceiveInstance.parsedBuildFile().key('storage.dirs')
		if permStorageDirs == None:
			Output.line(Formatter('Warning: no permanent storage dirs defined').color('yellow').indent())
		else:
			if isinstance(permStorageDirs,list) == False:
				raise Exception('Permanent storage directories in buildfile must be an array')

			# If we get here (still in the tmp dir), loop through and a) remove dirs that
			# exist but are going to be replaced with symlinks, b) ensure permanent storage
			# directory exists OUTSIDE of the cloned codebase (somewhere... permanent), and
			# c) create symlinks
			for relativePath in permStorageDirs:
				fullPath = os.path.abspath(os.path.join(PostReceiveInstance.tmpDir(), relativePath))

				# delete IN THE TMP FOLDER if exists (was dumped by git during export)
				if os.path.exists(fullPath) == True:
					if os.path.isdir(fullPath) == True:
						FileSystem.removeDir(fullPath)
					else:
						os.remove(fullPath)

				# ensure permanent directory is created, now in the BUNDLE path
				generatedPermanentPath = os.path.join(PostReceiveInstance.locPermanentDirs, relativePath)
				if not os.path.exists(generatedPermanentPath):
					os.makedirs(generatedPermanentPath)
					Output.line(Formatter('Added permanent storage for: ' + Formatter(relativePath).style(['underline'])).indent())

				# now, we can symlink in place of directories we know are not 
				# there in the tmp directory BACK to the permanent storage location
				FileSystem.genSymlink(generatedPermanentPath, fullPath)

	except Exception as e:
		Output.line(Formatter(e).color('red').indent())
		sys.exit(0)


	# Move from /tmp directory to final destination (still keeping newCommitID name)
	try:
		FileSystem.mvFromTo(PostReceiveInstance.tmpDir(), PostReceiveInstance.locAppBundle)
		Output.line(Formatter('Moved to release directory').indent())
	except:
		Output.line(Formatter('Could not move from temp dir').color('red'))

	# Ensure symlink is pointing at the directory
	try:
		# First, delete symlink if it already exists
		if FileSystem.isSymlink(PostReceiveInstance.symlinkPointer):
			FileSystem.remove(PostReceiveInstance.symlinkPointer)
		# Now create the symlink. NOTE: instead of placing PostReceiveInstance.locAppBundle + ...newCommitID,
		# we are just doing _application/ so that the symlink is a RELATIVE path
		FileSystem.genSymlink(('_application/' + PostReceiveInstance.newCommitID), PostReceiveInstance.symlinkPointer)
	except:
		Output.line(Formatter('Symlinking failed').color('red'))

	# Purge stale (previous) deploys
	try:
		FileSystem.purgeOtherDirectoriesInDirectoryExcept(PostReceiveInstance.locAppBundle, [PostReceiveInstance.newCommitID])
		Output.line(Formatter('Purged old deploys').indent())
	except:
		Output.line(Formatter('Failed purging stale deploys, no biggie').color('yellow'))

	# Notify this first step of stuff above is OK
	Output.multiLine([
		Formatter('Project structure OK').color('green').indent(),
		''
	])

	# Composer, if relevant
	try:
		Output.line(Formatter('Inspecting composer settings').arrowed())
		composerWD = PostReceiveInstance.parsedBuildFile().key('composer.workingDir')
		if composerWD == None:
			raise Exception('No composer run specified in buildfile')
		Output.line(Formatter('Executing composer install for: ' + Formatter(composerWD).style(['underline'])).indent())
		# Find out the realpath, now that we're in the relase dir
		realPath = os.path.join(PostReceiveInstance.locAppBundle, PostReceiveInstance.newCommitID, composerWD)
		Composer([
			'--working-dir=%s' % realPath,
			'install'
		])
	except Exception as e:
		Output.line(Formatter(e).color('yellow').indent())

	# NOTICE, this is the LAST thing in the function
	Output.line('')
	sys.exit(0)

# NOTE: since PreReceive gets the same arguments passed by stdin, in the
# same order form Git, its OK to extend the PreReceive class. THAT IS NOW ALWAYS 
# THE CASE with other Git hooks regarding whats passed to stdin.
class PostReceive(PreReceive):

	def __init__(self, inputs, settings={}):
		# ensure trailing slash with '' at the end
		self.buildDir 			= os.path.join(settings['buildDir'], '')
		self.symlinkPointer		= os.path.join(self.buildDir, 'ln-release')
		self.locPermanentDirs	= os.path.join(self.buildDir, '_permanent', '')
		self.locAppBundle		= os.path.join(self.buildDir, '_application', '')
		super(PostReceive, self).__init__(inputs)

	def _hookProcess(self):
		postReceiveRunner(self)

	def cloneProjectToTmpDir(self):
		execCall = Git(['--work-tree=%s' % self.tmpDir(),
			'checkout', '-f', self.newCommitID
		])
		return (execCall.process.returncode == 0)