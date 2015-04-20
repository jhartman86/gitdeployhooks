#!/usr/bin/env python
# -*- coding: utf-8 -*-
import setuptools

######################################################
# 1) download ez-install for python
# 2) in this dir, $: python setup.py develop
#    (to be able to mod in place)
######################################################
setuptools.setup(
	name='deploy_coordinator',
	version='0.1',
	description='Deployment tools',
	url='',
	author='',
	author_email='',
	license='MIT',
	packages=['deploy_coordinator'],
	zip_safe=False
)