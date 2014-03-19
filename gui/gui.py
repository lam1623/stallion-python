#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# main.py
#
# Copyright 2013-2014 Lino Alfonso <lino@lt.desoft.cu>

from gi.repository import Gtk
from common.i18n import Translate

class Interface():

     def __init__(self):
		self.builder = Gtk.Builder()
		self.builder.add_from_file("gui/ui")
		self.trview()

     def __getattr__(self, name):
         return self.builder.get_object(name)

     def column(self,name,cell,attribute,value):		
		column = Gtk.TreeViewColumn(name)
		column.pack_start(cell, False)
		column.add_attribute(cell, attribute, value)
		return column

     def trview(self):
		trsl = Translate()
		_ = trsl._

		listStore = Gtk.ListStore(str,str,str,int,str,str,str,str)
		self.listStore = listStore
		self.treeview.set_model(listStore)

		self.treeview.append_column(self.column(_('Name'),Gtk.CellRendererText(),"text",0))
		self.treeview.append_column(self.column(_('Profile'),Gtk.CellRendererText(),"text",1))
		self.treeview.append_column(self.column(_('Status'),Gtk.CellRendererText(),"text",2))
		self.treeview.append_column(self.column(_('Progress'),Gtk.CellRendererProgress(),"value",3))
		self.treeview.append_column(self.column(_('Final Size'),Gtk.CellRendererText(),"text",4))
		self.treeview.append_column(self.column(_('Time Left'),Gtk.CellRendererText(),"text",5))
		self.treeview.append_column(self.column(_('Elapsed Time'),Gtk.CellRendererText(),"text",6))