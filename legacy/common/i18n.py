#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# i18n.py
#
# Copyright 2013-214 Lino Alfonso <lino@lt.desoft.cu>

import os
import locale
import gettext

class Translate():

	def __init__(self):		
		APP_NAME='i8n1'
		LOCALE_DIR = os.path.join('../','locale')
		LANG = locale.getlocale()[0]
		self.traslate = gettext.translation(APP_NAME,LOCALE_DIR,languages=['es'],fallback=True)

	def _(self,name):
		return self.traslate.gettext(name)