#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# filedir.py
#
# Copyright 2013-214 Lino Alfonso <lino@lt.desoft.cu>

import os

def get_extension(direction):
	return os.path.splitext(direction)

def get_name(direction):
	return os.path.basename(direction)

def get_dir_name(direction):
	return os.path.dirname(direction).decode('utf-8')

def home_dir():
	return os.getenv('HOME')

def cfg_file_name():
	return home_dir() +"/.config/stallion/cfg.xml"

def create_dir():	
	dir_file = os.path.dirname(cfg_file_name())
	
	if not os.path.exists(dir_file):
		try:
			os.mkdir(dir_file)
		except IOError,e:
		    print e
