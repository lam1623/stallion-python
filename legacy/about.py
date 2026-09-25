#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# about.py
#
# Copyright 2013 Lino Alfonso <lino@lt.desoft.cu>

from gi.repository import Gtk, GdkPixbuf

class AboutDialog():

	def __init__(self):		
		self.about_dialog = Gtk.AboutDialog()
		self.about_dialog.set_destroy_with_parent (True)
		logo = GdkPixbuf.Pixbuf.new_from_file('icons/64x64/stallion.png')
		self.about_dialog.set_logo (logo)
		self.about_dialog.set_program_name ('Stallion')
		self.about_dialog.set_version('3.0.6')
		self.about_dialog.set_comments(('Graphical interface for mencoder'))
		self.about_dialog.set_website('http://stallionv.wordpress.com/')
		self.about_dialog.set_authors(['Lino Alfonso <lleisdier.alfonso@gmail.com>'])
		self.about_dialog.set_copyright('Copyright © 2011-2014 Lino Alfonso')

		license = 'GNU GPL v3'

		self.about_dialog.set_license(license)

	def run(self):
		self.about_dialog.run()

	def destroy(self):
		self.about_dialog.destroy()