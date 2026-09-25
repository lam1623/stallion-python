#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# process.py
#
# Copyright 2013-2014 Lino Alfonso <lino@lt.desoft.cu>

import fcntl, os , time , subprocess, signal
from threading import Thread

from gi.repository import GObject
from filedir import get_name


class  Convert:

	def __init__(self,video):
		self.video = video
		self.process = None
		self.errors = ''
		self.start_time = 0

	def get_pid(self):
		return self.process.pid

	def stop(self):
		os.kill(self.get_pid(),signal.SIGKILL)
		
	def pause(self):
		os.kill(self.get_pid(),signal.SIGSTOP)

	def resume(self):
		os.kill(self.get_pid(), signal.SIGCONT)

	def readoutline(self,process):

		def out_process(line,paramt1,paramt2):
			return line.split(paramt1)[1].split(paramt2)[0]		

		if self.video.status == 2:
			while True:
				output = ''
				try:
					output = process.stdout.read()					
					break
				except Exception, e:
					pass

			if output[0:3] == "Pos" :
				line = [ln for ln in output.split(' ') if ln !='' and ln !='\r']
				self.video.fps_convert = float(line[2][:-1])

				self.video.porcent = int(out_process(output,'(','%'))
				self.video.finalsize = out_process(output,'n','A').strip(' ')
				self.video.lefttime = output.split(':')[2].split('n')[0].strip(' ')+'n'
				

		if process.poll() != None:

			retcode = process.poll()			

			if retcode != 0:
				msg = '\nERROR: %s' % process.stderr.read()

				self.video.status = 3
				self.video.porcent = 0

				if retcode < 0:
					msg += '\nKilled by signal %s' % -retcode
				else:
					self.video.status = 5
					msg += '\nCommand failed with return code %s' % retcode

				self.errors = msg
			else:
				self.video.status = 4
				self.video.porcent = 100				
				self.video.finalsize = '-'
				self.video.lefttime = '-'

			return False
		return True

	def start(self):

		param = self.video.param
		param = param.replace(self.video.get_heigth(),self.video.properties.heigth)
		param = param.replace(self.video.get_width(self.video.get_heigth()),self.video.properties.width)
		param = param.replace(self.video.get_vbitrate(),self.video.properties.vbitrate)
		self.video.param = param.replace(self.video.get_abitrate(),self.video.properties.abitrate)

		dir_file = self.video.direction
		out_file = '%s%s%s%s' %(self.video.properties.outdir,'/',os.path.splitext(get_name(dir_file))[0].decode('utf-8'),self.video.extension)

		cmd = ['/usr/bin/mencoder']
		cmd.extend(self.video.param.split(' '))
		cmd.append(dir_file)

		if self.video.aud_intern != ['None']:	
			cmd.append('-aid')
			cmd.append(str(self.video.properties.aud))

		if self.video.sub_intern != ['None']:
			cmd.append('-sid')
			cmd.append(str(self.video.properties.sub))

		if self.video.subfilename:
			fontname = self.video.properties.fontname
			fontOptions = '%s %s%s %s %s' % ('-font',fontname[0],':style=','-subfont-text-scale',' '.join(fontname[-1:]))
			subString = '%s %s %s %s %s %s %s %s %s %s' % ('-sub','-','-subfont-autoscale',0,'-ass','-ass-color',self.video.properties.color,'-ass-border-color',self.video.properties.bordercolor,fontOptions)

			sub = subString.split(' ')
			sub[1] = self.video.subfilename
			sub[10] += ' '.join(fontname[1:-1])
			cmd.extend(sub)		

		if self.video.properties.increseVol != 0:
			cmd.append('-lameopts')
			cmd.append('abr:vol=' + str(self.video.properties.increseVol))

		cmd.append('-o')
		cmd.append(out_file)

		self.video.porcent = 0
		self.process = subprocess.Popen(cmd, bufsize=-1, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

		fcntl.fcntl(self.process.stdout.fileno(), fcntl.F_SETFL, os.O_NONBLOCK)
		self.start_time = time.time()

		GObject.idle_add(self.readoutline, self.process)


