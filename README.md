### DeployHooks ###

A python package for helping w/ deployments (targeted at PHP apps right now). Super-early stage, mainly for internal use; but if its helpful to you go for it :)

Main feature is the ability to define a `buildfile.json` in your project root, then run your own custom build tasks... by writing them yourself...

#### Install ####

Requires Python 2.7, only tested on Ubuntu 14.

* Clone this mofo
* `$: wget https://bootstrap.pypa.io/ez_setup.py -O - | sudo python`
* `$: cd /wherever/you/put/it/ && python setup.py develop`

Leave off the 'deveop' option if you want to install it permanently. Doing it as 
develop makes it easier to upgrade because python package management is still a black box to me...

#### Sample buildfile.json ####

	{
		"project": {
			"name": "WhatevsBTDubs"
		},
		"storage": {
			"dirs": [
				"rel/path/from/",
				"rel/some/other/path"
			]
		},
		"composer": {
			"workingDir": "web/concrete"
		}
	}

#### Sample post-receive Hook ####

Server-side hook (in remote bare repo). Assumes your remote repository (the directory) ends in `.git`, like "my-repo.git"

	#!/usr/bin/env python
	# -*- coding: utf-8 -*-
	import sys, os
	from deploy_coordinator.hooks import PostReceive

	# Gets the name of current git repository (the working dir), ie. "my-repo.git"
	repositoryFullName	= os.path.basename(os.getcwd())
	# Yank off the .git part -> "my-repo"
	repositoryName 		= os.path.splitext(repositoryFullName)[0]
	# Web root path should be derived from somewhere (env vars?) Your call
	deployToDir			= '/var/www/'

	# Execute
	PostReceive(sys.stdin.read(), {
		'buildDir': os.path.join(deployToDir, repositoryName)
	})

#### Sample pre-receive ####

	#!/usr/bin/env python
	# -*- coding: utf-8 -*-
	import sys
	from deploy_coordinator.hooks import PreReceive

	# Execute
	PreReceive(sys.stdin.read())