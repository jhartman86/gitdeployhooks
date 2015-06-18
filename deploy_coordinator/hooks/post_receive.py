#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys, os, subprocess, tempfile, ConfigParser
from pre_receive import PreReceive
from deploy_coordinator.cli import Formatter, Output
from deploy_coordinator.system.execute import Execute, Git, Composer
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
		Output.line(Formatter('Applying buildfile rules').arrowed())
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

		# If composer key not defined, don't do anything
		if PostReceiveInstance.parsedBuildFile().key('composer') == None:
			Output.line(Formatter('No composer run specified; moving on....').indent())

		# Composer is defined; look at the composer.workingDir key and run
		else:
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
			raise Exception('EMERGENCY: Failed creating symlink pointer to latest release')

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

	try:
		Output.multiLine([
			'',
			Formatter('Rebooting web server').style(['bold']).arrowed()
		])
		# Note, this depends on a) the shell script is executable, and b) more importantly,
		# that the user (probably git) executing this script has been given PASSWORDLESS
		# sudo access to run the commands contained w/in restartapache.sh.
		# So: $: touch /etc/sudoers.d/gitdeploys
		# $: sudo visudo /etc/sudoers.d/gitdeploys
		# and add this line:
		# {user}	ALL=NOPASSWD:/etc/init.d/apache2 stop, /etc/init.d/apache2 start
		# whereas user probably = git
		# Also, to eliminate the could not reliably determine hostname, setup
		# servername.conf in /etc/apache2/conf-available with
		# ServerName localhost
		# then sudo a2enconf servername
		restartApacheShellScript = os.path.join(PostReceiveInstance.repoHooksPath, 'restartapache.sh')
		subproc = subprocess.Popen(restartApacheShellScript, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
		for line in iter(subproc.stdout.readline, ''):
			Output.line(Formatter(line.rstrip()).indent())
		for line in iter(subproc.stderr.readline, ''):
			Output.line(Formatter(line.rstrip()).color('red').indent())
		subproc.communicate()[0]
		if subproc.returncode != 0:
			Output.line(Formatter('Apache failed to restart!').color('red').style(['bold', 'underline']).indent())
		else:
			Output.line(Formatter('Apache restarted').color('green').indent())

	except Exception as e:
		Output.line(Formatter(e).color('red').indent())

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
		self.repoHooksPath		= settings['repoHooksPath']
		self.bareRepoPath		= settings['bareRepoPath']
		super(PostReceive, self).__init__(inputs)

	def _hookProcess(self):
		postReceiveRunner(self)

	def cloneProjectToTmpDir(self):
		execCall = Git(['--work-tree=%s' % self.tmpDir(),
			'checkout', '-f', self.newCommitID
		])
		return (execCall.process.returncode == 0)

	def inspectSubmodules(self):
		# if repo has submodules; it HAS to have .gitmodules in the root
		gitmodulefile = self.tmpDir() + '.gitmodules'

		# if .gitmodules doesn't exist, skip this whole kit and kaboodle
		if not os.path.isfile(gitmodulefile):
			return

		# gitmodules file exists; lets do work
		f = open(gitmodulefile, 'r')
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

		submodTempPaths = []
		
		# @todo: figure out the exact commit SHA1 to pull!
		# http://stackoverflow.com/questions/16574625/how-do-i-add-files-in-git-to-the-path-of-a-former-submodule/16581096#16581096
		for section in config.sections():
			# Parsed path to submodule RELATIVE to repo root
			_path 		= config.get(section, 'path')
			
			# Remote repo URL
			_url 		= config.get(section, 'url')
			
			# Returns message w/ the status of the file target (in
			# this case, its the path to the submodule) in format
			# like "160000 commit {SHA} {path}"
			_treeSpec	= Git([
				'--git-dir', 
				self.bareRepoPath,
				'ls-tree',
				'HEAD',
				_path
			])
			
			# Parse the response of the above system call and
			# take the 3rd element in the array
			_shaCommitID = _treeSpec.response.split()[2]
			
			# Show whass going down...
			Output.multiLine([
				'',
				Formatter('Detected submodule at path: %s' % _path).color('cyan').style(['bold']).indent(),
				Formatter('Pulling from: %s' % _url).indent(),
				Formatter('Using commit @ SHA: %s' % Formatter(_shaCommitID).style(['underline'])).indent()
			])
			
			# Full path where the submodule should exist, but in the tmp dir
			# where the full repo has been cloned
			fullProjectTmpBuildPath = os.path.join(self.tmpDir(), _path, '')
			
			# Temporary path where we clone the submodule repo
			# so we can work on it
			submodRepoCloneTmpPath = os.path.join(os.path.abspath(tempfile.gettempdir() + '/deploy_coord/submodules/%s' % _shaCommitID), '')
			submodTempPaths.append(submodRepoCloneTmpPath)
			
			# If it already exists, nuke it so we're doing a fresh checkout...
			if FileSystem.exists(submodRepoCloneTmpPath):
				FileSystem.removeDir(submodRepoCloneTmpPath)

			# Handlers for streaming output from stdOut/stdErr
			def cbStdOut(line):
				Output.line(Formatter(line.rstrip()).indent())
			def cbStdErr(line):
				Output.line(Formatter(line.rstrip()).indent())
			processOptions = {
				'streamResponse':True, 'receiveStdOut': cbStdOut, 'receiveStdErr': cbStdErr
			}

			# Actually clone the remote repo
			cloneProc = Git([
				'clone', 
				_url, 
				submodRepoCloneTmpPath
			], processOptions)
			if cloneProc.process.returncode != 0:
				Output.line(Formatter('Clone failed!').color('red').style(['bold', 'underline']).indent())
				abortBuild()
			else:
				Output.line(Formatter(Formatter(Output.CHECKMARK).color('green') + ' Cloned OK').indent())

			# Check the repo out to specified commit ID
			pullProc = Git([
				'--git-dir=%s.git' % submodRepoCloneTmpPath,
				'--work-tree=%s' % submodRepoCloneTmpPath, 
				'checkout',
				'-b',
				_shaCommitID,
				_shaCommitID
			], processOptions)
			if pullProc.process.returncode != 0:
				Output.line(Formatter('Unable to checkout commit @ %s' % _shaCommitID).color('red').style(['bold', 'underline']).indent())
				abortBuild()
			else:
				Output.line(Formatter(Formatter(Output.CHECKMARK).color('green') + ' Pulled target SHA OK').indent())

			# Now run checkout-index (which works on the current head, ie. the
			# the currently checked out branch); and copy everything to the destination
			# of the full project build location
			checkoutProc = Git([
				'--git-dir=%s.git' % submodRepoCloneTmpPath,
				'checkout-index',
				'-a',
				'-f',
				'--prefix=%s' % fullProjectTmpBuildPath
			], processOptions)
			if checkoutProc.process.returncode != 0:
				Output.line(Formatter('Unable to checkout index...').color('red').style(['bold', 'underline']).indent())
				abortBuild()
			else:
				Output.line(Formatter(Formatter(Output.CHECKMARK).color('green') + ' Index Checked Out OK (Files Copied)').indent())

			Output.line(Formatter('Submodule OK :)').color('green').indent())

		Output.multiLine([
			'',
			Formatter('Cleaning up temp files').color('yellow').indent(),
			''
		])

		# Remove temp directories
		for tmpPath in submodTempPaths:
			FileSystem.removeDir(tmpPath)

		# Remove the temporarily created parseableTmpFile
		FileSystem.remove(parseableTmpFile)