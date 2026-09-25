#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# video.py
#
# Copyright 2013-2014 Lino Alfonso <lino@lt.desoft.cu>

from filedir import get_extension
from readxml import Xml
import subprocess, os
from common.process import Convert

class Properties:

	def __init__(self):

		self.fontname = ['Arial','6']
		self.color = "FFFFFF00"
		self.bordercolor = "00000000"

		self.vbitrate = '0'
		self.abitrate = '0'
		self.width = '0'
		self.heigth = '0'
		self.increseVol = 0
		self.outdir = None
		self.aud = 0
		self.sub = 0

class Video():

	# basic properties
	direction, category, variant, subfilename = '','','',''

	# information of video
	width_info, heigth_info, fps, duration, codec_video, codec_audio, bitrate_video, bitrate_audio = '','','','','','','',''

	def __init__(self,direction,category,variant):

		self.direction = direction
		self.variant = variant
		self.category = category
		self.iter = None
		self.param = None		
		self.extension = None
		self.aud_intern = []
		self.sub_intern = []

		self.porcent = '0'
		self.finalsize = 'calculating'
		self.lefttime = 'calculating'
		self.status = 0
		self.fps_convert = 0.0
		self.fps_total = 0.0

		self.properties = Properties()
		self.process = Convert(self)


	def get_infomedia(self):

		def split1(data,begin,end):
		    return data[begin:end][0].split("=")[1]

		mplayer = "/usr/bin/mplayer -vo null -ao null -frames 0 -identify -really-quiet"

		cmd = [ i for i in mplayer.split(' ')]
		cmd.append(self.direction)

		popen = subprocess.Popen(cmd,stdout=subprocess.PIPE, stderr=subprocess.PIPE)

		output = popen.stdout.read().split('\n')
		data = output[-23:]

		if get_extension(self.direction)[1].find('mkv') != -1:
			for i in range(len(output[:-24])):

				if output[i].find('ID_AUDIO_ID') == 0:
					ID_AUD = output[i].split('=')[1]

					if output[i+1].find('ID_AID_'+ID_AUD+'_LANG') != -1:
						self.aud_intern.append(output[i+1].split('=')[1])
					else:
						self.aud_intern.append(ID_AUD)

				if output[i].find('ID_SUBTITLE_ID') == 0:
					ID_SUD = output[i].split('=')[1]

					if output[i+1].find('ID_SID_'+ID_SUD+'_LANG') != -1:
						self.sub_intern.append(output[i+1].split('=')[1])
					else:
						self.sub_intern.append(ID_SUD)

		self.sub_intern.append('None')
		self.aud_intern.append('None')

		self.bitrate_video = split1(data,3,4)
		self.width_info = split1(data,4,5)
		self.heigth_info = split1(data,5,6)
		self.fps = split1(data,6,7)
		self.duration = split1(data,13,14)
		self.codec_video = split1(data,16,17).replace('ff','')
		self.bitrate_audio = split1(data,17,18)
		self.codec_audio = split1(data,20,21).replace('ff','')

		if len(self.bitrate_video) > 5 : 
		    self.bitrate_video = self.bitrate_video[0:-2]

		if len(self.bitrate_audio) >= 5 :
		     self.bitrate_audio = self.bitrate_audio[0:-3]

	def split1(self,param,option,separator = None):
		result = ''

		if separator != None:
			result = param.split(option)[1].split(separator)[0]
		else:
			try:
				result =  int(param.split(option)[1].split(':')[0])
			except Exception, e:
				result = int(param.split(option)[1].split(' ')[0])

		return str(result)

	def get_vbitrate(self):		
		if self.param.find("vbitrate") >= 0:
			return self.split1(self.param,'vbitrate=')
		elif self.param.find("bitrate") >= 0 :
			return self.split1(self.param,'bitrate=')
		return '0'

	def get_abitrate(self):
		if self.param.find("cbr:br") >= 0:
			return self.split1(self.param,'cbr:br=')
		elif self.param.find("cbr") >= 0:
			return self.split1(self.param,'cbr=')
		elif self.param.find("br") >= 0:
			return self.split1(self.param,'br=')
		elif self.param.find("abitrate") >= 0:
			return self.split1(self.param,'abitrate=')
		return '0'

	def get_heigth(self):
	 	if self.param.find("scale") >= 0:	 		
			return self.split1(self.param,'scale=',':')
		return '0'

	def get_width(self,heigth):
	 	if self.param.find("scale") >= 0:
			return self.split1(self.param,'scale='+heigth+':',' ').split(',')[0]
		return '0'

	def get_param_options(self):	
		self.properties.vbitrate = self.get_vbitrate()
		self.properties.abitrate = self.get_abitrate()
		self.properties.heigth = self.get_heigth()
		self.properties.width = self.get_width(self.properties.heigth)