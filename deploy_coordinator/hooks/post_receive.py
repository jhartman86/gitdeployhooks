#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys, os, ConfigParser
from pre_receive import PreReceive
from deploy_coordinator.cli import Formatter, Output
from deploy_coordinator.system.execute import Git, Composer
from deploy_coordinator.system.file_system import FileSystem
from deploy_coordinator.system.parse_json import ParseJson

def abortBuild():
	Output.multiLine([
		'',
		Formatter('Build aborted; nothing changed with current deploy.').color('red').style(['bold']),
		''
	]);
	sys.exit(0)


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
		if not os.path.exists(PostReceiveInstance.locComposerCache):
			os.makedirs(PostReceiveInstance.locComposerCache)
	except:
		Output.line(Formatter('Unable to create bundle directory for project').color('red').indent())

	# Copy to /tmp directory so we can monkey with code there
	try:
		Output.line(Formatter('Cloning code to tmp dir').arrowed())
		# Clone the entire project to a tmp directory and check it worked
		if PostReceiveInstance.cloneProjectToTmpDir() != True:
			raise Exception('Unable to clone to tmp dir')
	except Exception as e:
		Output.line(Formatter(e.args[0]).color('red').indent())
		abortBuild()

	# SUBMODULES
	PostReceiveInstance.inspectSubmodules()


	# Pre-processing (eg. remove data dirs FROM THE CLONED tmp dir - which should
	# not contain anything), then setup symlinks to permanent storage)
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
		abortBuild()

	# Composer, if relevant (note - this is all still happening in the tmp dir)
	# @todo: currently we're setting it such that if no composer settings exist, the
	# build will abort. should be made optional (eg. skip this if not relevant and continue build)
	try:
		Output.multiLine([
			'',
			Formatter('Inspecting composer settings').arrowed()
		])
		composerWD = PostReceiveInstance.parsedBuildFile().key('composer.workingDir')
		if composerWD == None:
			raise Exception('No composer run specified in buildfile')
		
		composerWDPathTmp 	 = os.path.join(PostReceiveInstance.tmpDir(), composerWD)
		composerFilePath  	 = os.path.join(composerWDPathTmp, 'composer.json')
		composerLockFilePath = os.path.join(composerWDPathTmp, 'composer.lock')

		# Ensure composer.json file exists in the target directory
		if not FileSystem.fileExists(composerFilePath):
			raise Exception('Missing composer file (composer.json)')

		# Ensure composer.lock file exists in the target directory
		if not FileSystem.fileExists(composerLockFilePath):
			raise Exception('Missing composer file (composer.lock)')

		# Try to parse the composer lock file (which is JSON)
		try:
			parsedLockFile = ParseJson(composerLockFilePath)
		except ValueError, e:
			raise Exception('Unable to parse the composer.lock file')

		# Get the hash key from the composer lock file to see if we already
		# have a build to check for
		composerHash = parsedLockFile.key('hash')
		# In the tmp directory, what is the full path to the vendor dir (whether it exists or not, yet);
		# this is where we'll generate a symlink to point to the permanent/cached composer builds
		vendorDirInTmp = os.path.join(composerWDPathTmp, 'vendor')
		# Full path to the permanent/cached build (eg. what the vendor directory should symlink to)
		permBuildDir   = os.path.join(PostReceiveInstance.locComposerCache, composerHash)

		# Check the composercache directory (which is always permanent) to see if a build
		# already exists w/ the same value as the hash in the lock file. If not, we'll run a composer
		# install...
		if FileSystem.exists(os.path.join(PostReceiveInstance.locComposerCache, composerHash)):
			Output.line(Formatter(Formatter('Using cached composer dependencies ->').color('green') + ' ' + composerHash).indent())
		else:
			Output.line(Formatter('Installing composer dependencies for path: ' + Formatter(composerWD).style(['underline'])).indent())
			
			# Execute composer (fails silently, thats why we check for existence of vendorDirInTmp)
			composerProc = Composer(['--working-dir=%s' % composerWDPathTmp, 'install'])

			# Ensure the system call itself didn't return any errors
			if not composerProc.process.returncode == 0:
				# @todo: log error output somewhere
				raise Exception('Executing composer failed hard; probably a syntax error...')
			# Did the run work (kind of a double check, but most important b/c the dir needs to exist)
			if FileSystem.exists(vendorDirInTmp):
				# Copy "vendor" dir from location in tmp dir to the permanent _composercache dir,
				# noting that it'll still be named 'vendor' in the permanent dir
				FileSystem.mvFromTo(vendorDirInTmp, PostReceiveInstance.locComposerCache)
				# Rename from "vendor" to the composer.lock file's hash value
				os.rename(
					os.path.join(PostReceiveInstance.locComposerCache, 'vendor'),
					permBuildDir
				)
				# Output
				Output.line(Formatter(Formatter('Using lock file version: ').color('green') + Formatter(composerHash).style(['underline'])).indent())
			else:
				raise Exception('Composer run failed')

		
		# Create a symlink for the vendor dir (which is no longer there after having been
		# moving/renamed above, OR it already existed hence the "cache") pointing at permBuildDir;
		# which is (what was previously) the vendor directory, renamed to the hash from the lockfile.
		# This always happens, as we're symlinking to what we now know to be the cached directory, whether
		# it was freshly created or not from above.
		FileSystem.genSymlink(permBuildDir, vendorDirInTmp)
		
	except Exception as e:
		Output.line(Formatter(e).color('yellow').indent())
		abortBuild()


	# --------------------------------------------------------------------
	# Building things in the /tmp dir done; move and link for final deployment
	try:
		# Move from /tmp directory to final destination (still keeping newCommitID name)
		try:
			Output.multiLine([
				'',
				Formatter('Moving build to release directory').arrowed()
			])
			FileSystem.mvFromTo(PostReceiveInstance.tmpDir(), PostReceiveInstance.locAppBundle)
		except:
			raise Exception('Could not copy from tmp to release directory')

		# Ensure symlink is pointing at the directory
		try:
			# First, delete symlink if it already exists
			if FileSystem.isSymlink(PostReceiveInstance.symlinkPointer):
				FileSystem.remove(PostReceiveInstance.symlinkPointer)
			# Now create the symlink. NOTE: instead of placing PostReceiveInstance.locAppBundle + ...newCommitID,
			# we are just doing _application/ so that the symlink is a RELATIVE path
			FileSystem.genSymlink(('_application/' + PostReceiveInstance.newCommitID), PostReceiveInstance.symlinkPointer)
			# Show output
			Output.line(Formatter('Symlinked to release').indent())
		except:
			raise Exception('Failed creating symlink pointer to latest release')

		# Purge stale (previous) deploys
		try:
			FileSystem.purgeOtherDirectoriesInDirectoryExcept(PostReceiveInstance.locAppBundle, [PostReceiveInstance.newCommitID])
			Output.line(Formatter('Purged old deploys').indent())
		except:
			Output.line(Formatter('Failed purging stale deploys, no biggie').color('yellow'))

		# Notify this first step of stuff above is OK
		Output.line(Formatter('Project build OK').color('green').indent())

	except Exception as e:
		Output.line(Formatter(e).color('yellow').indent())
		Output.line(Formatter('This occurred during final build phase :(').color('red'))

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
		self.locComposerCache	= os.path.join(self.buildDir, '_composercache', '')
		super(PostReceive, self).__init__(inputs)

	def _hookProcess(self):
		postReceiveRunner(self)

	def cloneProjectToTmpDir(self):
		execCall = Git(['--work-tree=%s' % self.tmpDir(),
			'checkout', '-f', self.newCommitID
		])
		return (execCall.process.returncode == 0)

	def inspectSubmodules(self):
		# @todo: this shouldn't even run if .gitmodules doesnt exist
		f = open(self.tmpDir() + '.gitmodules', 'r')
		mylist = []
		for line in f:
			mylist.append(line.strip('\t'))
		untabbed = ''.join(mylist)
		parseableTmpFile = os.path.join(self.tmpDir(), '.parseable')
		f2 = open(parseableTmpFile, 'w')
		f2.write(untabbed)
		f2.close()
		Output.line(Formatter('Inspecting submodules').indent())
		config = ConfigParser.SafeConfigParser(allow_no_value=True)
		config.readfp(open(parseableTmpFile))
		
		# @todo: figure out the exact commit SHA1 to pull!
		for section in config.sections():
			_path = config.get(section, 'path')
			_url = config.get(section, 'url')
			if config.has_option(section, 'branch'):
				_branch = config.get(section, 'branch')
			else:
				_branch = 'master'
			Output.multiLine([
				Formatter('Detected submodule: %s' % _path).color('cyan').style(['bold']).indent(),
				Formatter('Attempting pull from: %s' % _url).indent(),
				Formatter('On branch: %s' % Formatter(_branch).style(['underline'])).indent()
			])
			pathAtTmpDir = os.path.join(self.tmpDir(), _path, '')
			Git(['clone', '-b', _branch, '--single-branch', _url, pathAtTmpDir])
			FileSystem.removeDir(os.path.join(pathAtTmpDir, '.git'))

		FileSystem.remove(parseableTmpFile)



		# wktree2 = Git(['--work-tree %s' % self.tmpDir(),
		# 	'--git-dir /home/jon/Desktop/sf_ubuntu_vm/GitHooksDev/remote_repo.git',
		# 	'submodule', 'status'
		# ])
		# Output.line(wktree.response)
		# Output.line(wktree.error)
		# print self.newCommitID
		# execCall = Git(['--git-dir=/home/jon/Desktop/sf_ubuntu_vm/GitHooksDev/remote_repo.git',
		# 	'--work-tree=%s' % self.tmpDir(),
		# 	'submodule', 'status', '--recursive', self.newCommitID
		# ])
		# print execCall.response
		# print execCall.error