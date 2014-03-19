#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# filechooser.py
#
# Copyright 2013 Lino Alfonso <lino@lt.desoft.cu>

from gi.repository import Gtk

class Filechooser:
	def __init__(self,parent):
		self.parent = parent

	def dialog(self,title,action,select_multiple,folder):
		file_names = []
		dialog = Gtk.FileChooserDialog(title,self.parent,action,(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,Gtk.STOCK_OPEN, Gtk.ResponseType.OK))
		dialog.set_select_multiple(select_multiple)
		dialog.set_current_folder(folder)
		if select_multiple:
			self.add_filters(dialog)
		response = dialog.run()
	 	if response == Gtk.ResponseType.OK:
	 		file_names = dialog.get_filenames()
		dialog.destroy()
		return file_names
		
	def add_filters(self,dialog):
		filter_text = Gtk.FileFilter()
		filter_text.set_name("all videos")
		filter_text.add_mime_type("video/*")
		dialog.add_filter(filter_text)

		filter_text = Gtk.FileFilter()
		filter_text.set_name("avi")
		filter_text.add_mime_type("video/x-msvideo")
		dialog.add_filter(filter_text)		