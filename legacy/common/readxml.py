#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# readxm.lpy
#
# Copyright 2013 Lino Alfonso <lino@lt.desoft.cu>

from filedir import home_dir, cfg_file_name
import os
import xml.etree.ElementTree as ET

class Xml:
	def __init__(self):
		self.file_presets = 'presets.xml'
		self.cfg_file_name = cfg_file_name()
	
	# Methods cfg.xml

	def get_version(self):
		tree = ET.parse(self.cfg_file_name)
		root = tree.getroot()
		return root.get('version')

	def save(self,xmlstring):
		file_save = open(self.cfg_file_name, 'w')
		file_save.write(xmlstring)
		file_save.close()

	def xml_exist(self):		
		return os.path.exists(self.cfg_file_name)		

	def create_xml_file(self):
		root = ET.XML('<?xml version=\"1.0\" encoding=\"utf-8\"?>\n <CONFIG version="3.0">\n <unix prst="/opt/stallion/presets.xml" app="/usr/bin/mencoder"/>\n <aplicacion combcat=\"0\" combvar=\"0\"/>\n <option loadsubtitle="1" poweroffinish="0" popups="1" deletedialog="0" outdirsave="0" systray="1"/>\n</CONFIG>')
		config = root.find('option')
		config.set('diropen',home_dir().decode('utf-8'))
		config.set('dirsave',home_dir().decode('utf-8'))
		self.save(ET.tostring(root))

	def set_xml_file(self,head,attribute,value):
		tree = ET.parse(self.cfg_file_name)
		root = tree.getroot()
		config = root.find(head)
		config.set(attribute,str(value).decode('utf-8'))
		self.save(ET.tostring(root))

	def get_xml_file(self,head,attribute):
		tree = ET.parse(self.cfg_file_name)
		root = tree.getroot()
		config = root.find(head)
		return config.get(attribute)

	#Methods for presest.xml file (*******revisar*******)
	def get_xml_tag(self,param = []):
		from xml.dom.minidom import parse

		dmxl = parse(self.file_presets)
		for nparent in dmxl.getElementsByTagName('category'):
			if param[0] == 'category':
				param[1] += [nparent.getAttribute('name')]
			elif param[0] == 'variant':
				if nparent.getAttribute('name') == param[2]:					
						param[1].append([nparent.getElementsByTagName(param[3])[0].childNodes[0].nodeValue])
			elif param[0] == 'attribute':
				if nparent.getAttribute('name') == param[1]:
					return nparent.getAttribute('separator')			
			else: 
			 	for node in nparent.getElementsByTagName('label'):
				 	if node.childNodes[0].nodeValue == param[0]:
				 		return (nparent.getElementsByTagName(param[1])[0].childNodes[0].nodeValue).decode('utf-8')
		return param[1]