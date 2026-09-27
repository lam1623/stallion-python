#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# main.py
#
# Copyright 2013-2014 Lino Alfonso <lino@lt.desoft.cu>

from gi.repository import Gtk , Gdk , GObject, Notify, AppIndicator3, Unity, GObject, Dbusmenu
from common.i18n import Translate
from common.readxml import Xml
from common.filechooser import Filechooser
from common.process import Convert
from common.video import Video
from common.filedir import get_dir_name, get_name , cfg_file_name, create_dir
from gui.gui import Interface as ui
import gettext ,locale, os, time, sys


class Handler():

 	def onDeleteWindow(self, *args): 		
 		respt,isquit = True,True

 		if str(type(args[0])) == "<class 'gi.repository.Gtk.ImageMenuItem'>":
 			isquit = not(args[0].get_label() == 'gtk-quit')

 		if int(main._xml.get_xml_file('option','systray')) and isquit:
 			main.ui.window.set_visible(False)
 			return True
 			
 		if main.not_close_window:
	 		dialogWindow = Gtk.MessageDialog(main.ui.window,Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,Gtk.MessageType.QUESTION,Gtk.ButtonsType.YES_NO,main.close_message)			
			response = dialogWindow.run()				
			dialogWindow.hide()

			respt = (response == Gtk.ResponseType.YES)

		if not(respt):
			main.ui.window.set_visible(not(isquit))
 		else:
 			Gtk.main_quit(*args)			

	def on_combobox1_changed(self, data):
		activo = main.ui.cmbobox_convert_to.get_active()
		cmbobox_variant_listStore= main._xml.get_xml_tag(['variant',Gtk.ListStore(str),main.ui.cmbobox_convert_to.get_model()[activo][0],'label'])
		main.ui.cmbobox_variant.set_model(cmbobox_variant_listStore)
		main._xml.set_xml_file('aplicacion','combcat',str(activo))

	def on_combobox2_changed(self, data):
		if main.changed:
			convert_in_progress = False

			cmbobox_convert_to_active = main.ui.cmbobox_convert_to.get_active()
			cmbobox_variant_active = main.ui.cmbobox_variant.get_active()
			main._xml.set_xml_file('aplicacion','combvar',str(cmbobox_variant_active))

			for i in main.get_selected_indexs():

				if main.videos[i].status != 2:
					main.videos[i].category = cmbobox_convert_to_active
					main.videos[i].variant = cmbobox_variant_active

					main.get_parms_of_convert(main.videos[i])
					main.videos[i].get_param_options()
					main.ui.treeview.get_model().set_value(main.videos[i].iter, 1, main.ui.cmbobox_variant.get_model()[cmbobox_variant_active][0])

				elif main.videos[i].status == 2:
					convert_in_progress = True

			if convert_in_progress:
				main.ui.treeview.changed = False
			 	main.ui.cmbobox_convert_to.set_active(main.videos[i].category) 
				main.ui.cmbobox_variant.set_active(main.videos[i].variant)

				dialogWindow = Gtk.MessageDialog(main.ui.window,Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,Gtk.MessageType.ERROR,Gtk.ButtonsType.OK,main.select_message)
				dialogWindow.run()
				dialogWindow.destroy();

			main.refresh()

	def on_treeview_selection_changed(self,data):
		main.ui.treeview.changed = False
		main.refresh()

	def on_toolbutton_open_clicked(self, button):
		file_names = main._filechooser.dialog(main.title_select_file,Gtk.FileChooserAction.OPEN,True,main._xml.get_xml_file('option','diropen'))
		cmbobox_convert_to_active = main.ui.cmbobox_convert_to.get_active()
		cmbobox_variant_active = main.ui.cmbobox_variant.get_active()
		loadsubtitle = main._xml.get_xml_file('option','loadsubtitle')

		if file_names :
			main.ui.toolbutton_startpause.set_sensitive(True)			
			main.ui.toolbutton_clear.set_sensitive(True)
			main._xml.set_xml_file('option','diropen',get_dir_name(file_names[0]))

			for file_name in file_names:
				video = Video(file_name,cmbobox_convert_to_active,cmbobox_variant_active)
				main.get_parms_of_convert(video)			

				video.get_infomedia()
				video.get_param_options()
				video.properties.outdir = main.ui.entr_svto.get_text()
				video.fps_total = (float(video.fps) * float(video.duration))
				main.frames_total += video.fps_total

				if loadsubtitle:
					subtitle = '%s/%s%s' % (get_dir_name(file_names[0]),os.path.splitext(get_name(file_name))[0].decode('utf-8'),'.srt')

					if os.path.exists(subtitle.encode('utf-8')):
						video.subfilename = subtitle				

				main.videos.append(video)
				main.addtreeview(file_name,main.ui.cmbobox_variant.get_model()[cmbobox_variant_active][0])

			###REVISAR####
			treeiter = main.ui.treeview.get_model().get_iter_first()
			for i in range(len(main.ui.treeview.get_model())):
				main.videos[i].iter = treeiter
				treeiter = main.ui.treeview.get_model().iter_next(treeiter)

	def on_menuitem_selectfolder_activate(self,data):
		file_names = main._filechooser.dialog(title_select_folder,Gtk.FileChooserAction.SELECT_FOLDER,False)

	def on_bttn_selectsaveto_clicked(self,button):
		folder = main._filechooser.dialog(main.title_select_folder,Gtk.FileChooserAction.SELECT_FOLDER,False,main.ui.entr_svto.get_text())
		
		if folder:
			main.ui.entr_svto.set_text(folder[0])
			main._xml.set_xml_file('option','dirsave',folder[0])

			if int(main._xml.get_xml_file('option','outdirsave')):
				indexs = main.get_selected_indexs()
				for i in indexs:
					main.videos[i].properties.outdir = folder[0]
			else:
				for video in main.videos:
					video.properties.outdir = folder[0]
	
	def on_button2_clicked(self,button):
		import webbrowser
		webbrowser.open(main.ui.entr_svto.get_text())

	def on_toolbutton_stop_clicked(self,button):
		video = main.videos[main.get_selected_indexs()[0]]
		video.process.stop()		
		
		video.porcent = 0
		video.finalsize = '-'
		video.lefttime = '-'
		video.status = 3
		main.refresh()

	def on_toolbutton_startpause_clicked(self,button):

		indexs = main.get_selected_indexs()

		if len(indexs) == 0:
			video = main.videos[0]
		else:
			video = main.videos[indexs[0]]

		if  video.status == 2:
			video.status = 1
			video.process.pause()
		else:			
			if video.status != 1:
				main.convertion_start(video)
				main.launcher.set_property("progress_visible", True)
				main.launcher.set_property("urgent", False)
			else:	
				video.status = 2
				video.process.resume()

			GObject.idle_add(main.updatetreeview, 0.1)
			self.convert_in_progress = True

	 	main.refresh()

	def on_toolbutton_remove_clicked(self, data):

		if int(main._xml.get_xml_file('option','deletedialog')):
			checkbttn.set_active(0)

			reponse = messagedialog.run()
			if reponse == Gtk.ResponseType.YES:
				main._xml.set_xml_file('option','deletedialog',int(main.ui.checkbttn.get_active()))
				main.deletetreeview()

			messagedialog.hide()		
		else:
			main.deletetreeview()

	def on_toolbutton_clear_clicked(self, data):

		if main.not_close_window:
			dialogWindow = Gtk.MessageDialog(main.ui.window,Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,Gtk.MessageType.ERROR,Gtk.ButtonsType.OK,main.clear_message)
			dialogWindow.run()
			dialogWindow.destroy();
		else:
			main.ui.treeview.get_model().clear()				
			main.ui.toolbutton_startpause.set_sensitive(False)			
			main.ui.toolbutton_clear.set_sensitive(False)
			main.ui.toolbutton_remove.set_sensitive(False)
			self.frames_total = 0.0
			main.videos = []

	def on_bttn_loadsubtitle_clicked(self, data):
		indexs =  main.get_selected_indexs()

		if len(indexs) == 1:
			files = main._filechooser.dialog(main.title_select_file,Gtk.FileChooserAction.OPEN,False, main._xml.get_xml_file('option','diropen'))
			if files:
				main.videos[indexs[0]].subfilename = files[0]	
				main.ui.entr_subtitle.set_text(files[0])

				main.ui.entr_subtitle.set_sensitive(True)
				main.ui.bttn_properties.set_sensitive(True)
				main.ui.bttn_remove.set_sensitive(True)
		else:
			dialogWindow = Gtk.MessageDialog(main.ui.window,Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,Gtk.MessageType.QUESTION,Gtk.ButtonsType.OK,main.subtitle_message)
			dialogWindow.run()
			dialogWindow.destroy();

	def on_spinbutton_width_value_changed(self, data):
		for i in  main.get_selected_indexs():
			main.videos[i].properties.width = str(main.ui.spinbutton_width.get_value()).split('.')[0]

	def on_spinbutton_heigth_value_changed(self, data):		
		for i in  main.get_selected_indexs():
			main.videos[i].properties.heigth = str(main.ui.spinbutton_heigth.get_value()).split('.')[0]	

	def on_spinbutton_vbitrate_value_changed(self,data):
		for i in main.get_selected_indexs():
			main.videos[i].properties.vbitrate =  str(main.ui.spinbutton_vbitrate.get_value()).split('.')[0]

	def on_spinbutton_abitrate_value_changed(self,data):
		for i in main.get_selected_indexs():
			main.videos[i].properties.abitrate =  str(main.ui.spinbutton_abitrate.get_value()).split('.')[0]

	def on_scale1_value_changed(self,data):
		for i in  main.get_selected_indexs():
			main.videos[i].properties.increseVol = int( main.ui.scale1.get_value())	

	def on_bttn_remove_clicked(self,data):
		indexs = main.get_selected_indexs()
		main.ui.entr_subtitle.set_text('')
		main.ui.entr_subtitle.set_sensitive(False)
		main.ui.bttn_properties.set_sensitive(False)
		main.ui.bttn_remove.set_sensitive(False)
		main.videos[indexs[0]].subfilename = ''

	def on_imagemenuitem10_activate(self,data):
		from about import AboutDialog
		main.aboutdialog = AboutDialog()
		main.aboutdialog.run()
		main.aboutdialog.destroy()

	def on_bttn_ok_clicked(self,data):
		main._xml.set_xml_file('option','loadsubtitle',int(main.ui.checkbutton1.get_active()))		
		main._xml.set_xml_file('option','popups',int(main.ui.checkbutton2.get_active()))
		main._xml.set_xml_file('option','deletedialog',int(main.ui.checkbutton4.get_active()))
		main._xml.set_xml_file('option','outdirsave',int(main.ui.checkbutton5.get_active()))
		main._xml.set_xml_file('option','systray',int(main.ui.checkbutton6.get_active()))
		main.ui.preference.hide()

	def on_imagemenuitem6_activate(self,data):
		main.ui.entr_preset_file.set_text(main._xml.get_xml_file('unix','prst'))

		main.ui.checkbutton1.set_active(int(main._xml.get_xml_file('option','loadsubtitle')))		
		main.ui.checkbutton2.set_active(int(main._xml.get_xml_file('option','popups')))		
		main.ui.checkbutton4.set_active(int(main._xml.get_xml_file('option','deletedialog')))
		main.ui.checkbutton5.set_active(int(main._xml.get_xml_file('option','outdirsave')))
		main.ui.checkbutton6.set_active(int(main._xml.get_xml_file('option','systray')))

		main.ui.preference.set_visible(True)

	def on_bttn_properties_clicked(self,data):	
		indexs = main.get_selected_indexs()	
		main.ui.sub_preference.set_visible(True)

		rgba = Gdk.RGBA()

		rgba.parse('#%s' % main.videos[indexs[0]].properties.color[:6])
		main.ui.colorbutton.set_rgba(rgba)
		main.ui.scale2.set_value(int(main.videos[indexs[0]].properties.color[6:],16))

		rgba.parse('#%s' % main.videos[indexs[0]].properties.bordercolor[:6])
		main.ui.colorbutton1.set_rgba(rgba)
		main.ui.scale3.set_value(int(main.videos[indexs[0]].properties.bordercolor[6:],16))

		main.ui.fontbutton.set_font_name(' '.join(main.videos[indexs[0]].properties.fontname))

	def on_bttn_subt_apply_clicked(self,data):
		indexs = main.get_selected_indexs()

		color =  '%.2X%.2X%.2X%.2X' % (main.ui.colorbutton.get_color().red/256.0, main.ui.colorbutton.get_color().green/256.0, main.ui.colorbutton.get_color().blue/256.0, main.ui.scale2.get_value())
		borde_color =  '%.2X%.2X%.2X%.2X' % (main.ui.colorbutton1.get_color().red/256.0, main.ui.colorbutton1.get_color().green/256.0, main.ui.colorbutton1.get_color().blue/256.0,  main.ui.scale3.get_value())
		
		for i in indexs:
			main.videos[i].properties.color = color
			main.videos[i].properties.bordercolor = borde_color			
			main.videos[i].properties.fontname = [f for f in main.ui.fontbutton.get_font_name().split(' ')]

		main.ui.sub_preference.set_visible(False)		

	def on_bttn_subt_cancel_clicked(self,data):
		main.ui.sub_preference.set_visible(False)

	def on_toolbutton_properties_clicked(self,data):
		main.ui.expander.set_expanded( not(main.ui.expander.get_expanded()))

	def on_combobox3_changed(self,data):
		indexs = main.get_selected_indexs()
		main.videos[indexs[0]].properties.aud = main.ui.cmbobox_sound.get_active()

	def on_combobox4_changed(self,data):
		indexs = main.get_selected_indexs()

		if main.ui.cmbobox_subtitle.get_model()[main.ui.cmbobox_subtitle.get_active()][0] != 'None':
			main.ui.bttn_loadsubtitle.set_sensitive(False)
			main.ui.bttn_remove.set_sensitive(False)
			main.videos[indexs[0]].properties.sub = main.ui.cmbobox_subtitle.get_active()
		else:
			main.ui.bttn_loadsubtitle.set_sensitive(True)
			main.ui.bttn_remove.set_sensitive(True)

	def on_checkbttn_poweroff_toggled(self,data):
		main._xml.set_xml_file('option','poweroffinish',int(main.ui.checkbttn_poweroff.get_active()))

class Main():

	def __init__(self):	

		self.ui = ui()

		trsl = Translate()
		self._ = trsl._

		# labels text
		self.dimens_text = self._('dimensions: ')
		self.duration_text = self._('duration: ')
		self.bitrate_text = self._('bitrate: ')
		self.codec_text = self._('code:')
		self.fps_text = self._('fps: ')

		self.title_select_folder = self._('Select folder')
		self.title_select_file = self._('Select files')
		self.message_select_video = self._('Select video')

		#status
		self.status = {	0:self._('waiting'),
						   1:self._('pause'),
						   2:self._('in progress'),
						   3:self._('stoped'),
						   4:self._('complete'),
						   5:self._('error')
						
						}
		#message
		self.remove_message = self._('Some files are still in conversion. Stop started conversions and try again')
		self.subtitle_message = self._('It only applies to a file')
		self.clear_message = self._('Can not delete some items, stop started conversions and try again')
		self.close_message = self._('There are videos on conversion, are sure you want to quit')
		self.select_message = self._('There are videos on conversion, some profiles will not be changed.')

		# labels text
		self.ui.lbl_variant.set_text(self._('Variant:'))
		self.ui.lbl_convertto.set_text(self._('Convert to:'))
		self.ui.lbl_saveto.set_text(self._('Save to:'))
		self.ui.lbl_details.set_text(self._('Details'))
		self.ui.lbl_info.set_text(self._('Info media'))
		self.ui.lbl_properties.set_text(self._('Basic properties'))
		self.ui.lbl_video.set_text(self._('Video'))
		self.ui.lbl_sound.set_text(self._('Sound'))
		self.ui.lbl_vbitrate.set_text(self.bitrate_text)
		self.ui.lbl_abitrate.set_text(self.bitrate_text)
		self.ui.lbl_dimensions.set_text(self.dimens_text)
		self.ui.lbl_duration.set_text(self.duration_text)

		self._xml = Xml()
		self._filechooser = Filechooser(self.ui.window)
		self.videos = []
		self.not_close_window = False
		self.changed = False
		self.remove = False
		self.frames_total = 0.0
		self.frames_convert = 0.0

		self.ui.builder.connect_signals(Handler())		

	def show(self):
		self.ui.window.set_title('Stallion')
		create_dir()

		if not self._xml.xml_exist(): 
			self._xml.create_xml_file()

		if not self._xml.get_version():
			self._xml.create_xml_file()		

		self.ui.entr_svto.set_text(self._xml.get_xml_file('option','dirsave'))

		self.comboRender(self.ui.cmbobox_convert_to)
		self.comboRender(self.ui.cmbobox_variant)
		self.comboRender(self.ui.cmbobox_sound)
		self.comboRender(self.ui.cmbobox_subtitle)

		cmbobox_convert_to_activo = int(self._xml.get_xml_file('aplicacion','combcat'))
		lst = self._xml.get_xml_tag( ['category',[]] )
		
		self.addCombobox(self.ui.cmbobox_convert_to,set(lst))
		self.ui.cmbobox_variant.set_model(self._xml.get_xml_tag( ['variant',Gtk.ListStore(str),self.ui.cmbobox_convert_to.get_model()[cmbobox_convert_to_activo][0],'label']))
		self.addCombobox(self.ui.cmbobox_sound)
		self.addCombobox(self.ui.cmbobox_subtitle)
		
		self.ui.cmbobox_convert_to.set_active(cmbobox_convert_to_activo)
		self.ui.cmbobox_variant.set_active(int(self._xml.get_xml_file('aplicacion','combvar')))

		self.all_sensitive_False()
		self.ui.window.show_all()

		self.ui.checkbttn_poweroff.set_active(int(main._xml.get_xml_file('option','poweroffinish')))

		def showWindows(self):
			main.ui.window.set_visible(True)

		def makemenu():
			menu = Gtk.Menu()
			check_item = Gtk.MenuItem('Show stallion')
			exit_item = Gtk.MenuItem('Quit')
			check_item.connect('activate', showWindows)
			check_item.show()
			exit_item.connect('activate', Gtk.main_quit)
			exit_item.show()
			menu.append(check_item)
			menu.append(exit_item)
			menu.show()
			return menu
			
		APPNAME = "Stallion"
		ICON = os.path.join(os.path.dirname(sys.argv[0]),'icons/32x32/stallion.png')

		ai = AppIndicator3.Indicator.new(APPNAME, ICON, AppIndicator3.IndicatorCategory.HARDWARE)
		ai.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
		ai.set_menu(makemenu())

		# button_push = Gtk.Button("Push Message")
		# self.ui.statusbar1.pack_start(button_push, False, False, 0)

		#self.ui.statusbar1.add_attribute(render, 'text', 0)

		# self.context_id = self.ui.statusbar1.get_context_id("example")
		# self.ui.statusbar1.push(self.context_id, self.ui.button2)

		self.launcher = Unity.LauncherEntry.get_for_desktop_id ("Stallion.desktop")

		Gtk.main()

	def convertion_start(self,video):
		model, selected = self.ui.treeview.get_selection().get_selected_rows()		
		model.set_value(video.iter,3,int(video.porcent))
		video.process.start()

		video.status = 2
		model.set_value(video.iter,2,self.status[video.status])
		self.ui.textview.get_buffer().insert(self.ui.textview.get_buffer().get_end_iter(),'%s%s%s' % ('\n','Begining convert to: ',video.direction))

	def deletetreeview(self):

		self.remove = True

		convert_in_progress_selected = False
		model, selected = self.ui.treeview.get_selection().get_selected_rows()
		iters = []
		rvideo = []

		for path in selected:
			iters.append(model.get_iter(path))

		for i in self.get_selected_indexs():
			rvideo.append(main.videos[i])
		
		for video in rvideo:			
			if video.status != 2:
				self.frames_total -= video.fps_total
				model.remove(video.iter)
				main.videos.remove(video)			
			elif video.status == 2:
				convert_in_progress_selected = True

		if convert_in_progress_selected:
			dialogWindow = Gtk.MessageDialog(main.ui.window,Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,Gtk.MessageType.ERROR,Gtk.ButtonsType.OK,main.remove_message)
			dialogWindow.run()
			dialogWindow.destroy();

		self.remove = False

		main.refresh()

	def updatetreeview(self,data):
		model, selected = self.ui.treeview.get_selection().get_selected_rows()

		def notify_popups(title,body):
			Notify.init('Notify Popup')
			notification = Notify.Notification.new(title,body,'dialog-information')
			notification.show()

		def update(video):			
			iter = video.iter
			self.launcher.set_property("progress", self.frames_convert*100.0/main.frames_total/100)
			model.set_value(iter,3,int(video.porcent))
			model.set_value(iter,4,str(video.finalsize))
			model.set_value(iter,5,str(video.lefttime))			
			model.set_value(iter,6,'%s' % time.strftime('%H:%M:%S', time.gmtime( int(str(time.time() -  video.process.start_time).split('.')[0]) ) ))

		result = False		
		self.frames_convert = 0.0

		for video in self.videos:	
			self.frames_convert += video.fps_convert

			if  video.porcent <= 102:

				if video.status == 2:					
					update(video)
					result = True

				if video.status == 4 or video.status == 5 or video.status == 3:
					update(video)
					model.set_value(video.iter,2,str(self.status[video.status]))

					video.porcent = 103

					if video.status == 4:
						msg = self._('was completed sucessfully.')
					elif video.status == 5:						
						msg = self._('was completed  with errors.')
					elif video.status == 3:
						msg = self._('was stoped.')

					self.ui.textview.get_buffer().insert(self.ui.textview.get_buffer().get_end_iter(),video.process.errors)

					if int(self._xml.get_xml_file('option','popups')):
						notify_popups(self._('Conversion completed'),'%s \n%s %s' %(self._('The conversion of the video'),video.direction,msg))

					if video.status == 4:					
						for i in range(len(self.videos)):
							if self.videos[i].status == 0 and not result:
								self.convertion_start(self.videos[i])
								result = True				
					
					if not result:
						self.launcher.set_property("urgent", True)
						if int(self._xml.get_xml_file('option','poweroffinish')):
							os.system('/usr/bin/dbus-send --system --print-reply --dest="org.freedesktop.ConsoleKit" /org/freedesktop/ConsoleKit/Manager org.freedesktop.ConsoleKit.Manager.Stop')
					self.refresh()

		self.not_close_window = result
		return result

	def set_panel_options(self,values):

		if 	values[0] == '':
			self.ui.lbl_dimensions.set_text('%s' % (self.dimens_text))
			self.ui.lbl_duration.set_text('%s' % (self.duration_text))
		else:
			self.ui.lbl_dimensions.set_text('%s %sx%s' % (self.dimens_text,values[0],values[1]) )
			self.ui.lbl_duration.set_text('%s %s' % ( self.duration_text,time.strftime('%H:%M:%S', time.gmtime(float(values[2])) ) ) )

		self.ui.lbl_vbitrate.set_text('%s %s' % (self.bitrate_text,values[3]) )
		self.ui.lbl_vcode.set_text('%s %s' % (self.codec_text,values[4]))
		self.ui.lbl_acode.set_text('%s %s' % (self.codec_text,values[5]))
		self.ui.lbl_abitrate.set_text('%s %s' % (self.bitrate_text,values[6]))
		self.ui.lbl_fps.set_text('%s %s' % (self.fps_text,values[7]))

		self.ui.spinbutton_heigth.set_value(int(values[8]))
		self.ui.spinbutton_width.set_value(int(values[9]))
		self.ui.spinbutton_vbitrate.set_value(int(values[10]))
		self.ui.spinbutton_abitrate.set_value(int(values[11]))

	def refresh(self):
		if not self.remove:
			indexs = self.get_selected_indexs()

			if len(indexs) != 0:
				video = self.videos[indexs[0]]

				# change variant and category
				self.ui.cmbobox_convert_to.set_active(video.category)
				self.ui.cmbobox_variant.set_active(video.variant)

				# change video info and basic properties
				model, selected = self.ui.treeview.get_selection().get_selected_rows()
				model.set_value(video.iter,2,self.status[video.status])

				self.addCombobox(self.ui.cmbobox_sound)
				self.addCombobox(self.ui.cmbobox_subtitle)

				list = ('%s %s %s %s %s %s %s %s' %(video.heigth_info,video.width_info,video.duration,video.bitrate_video,video.codec_video,video.codec_audio,video.bitrate_audio,video.fps))
				list += (' %s %s %s %s' %(video.properties.heigth,video.properties.width,video.properties.vbitrate,video.properties.abitrate))		
				self.set_panel_options(list.split(' '))

				self.ui.spinbutton_width.set_sensitive(int(video.properties.width) != 0)
				self.ui.spinbutton_heigth.set_sensitive(int(video.properties.heigth) != 0)
				self.ui.spinbutton_abitrate.set_sensitive(int(video.properties.abitrate) != 0)
				self.ui.spinbutton_vbitrate.set_sensitive(int(video.properties.vbitrate) != 0)
				self.ui.cmbobox_sound.set_sensitive(video.aud_intern != ['None'])
				self.ui.cmbobox_subtitle.set_sensitive(video.sub_intern != ['None'])

				self.ui.scale1.set_sensitive(self.ui.cmbobox_convert_to.get_model()[video.category][0] == 'AVI')	
				self.ui.scale1_value = 0 if not self.ui.scale1.get_sensitive() else video.properties.increseVol
				self.ui.scale1.set_value(self.ui.scale1_value)
				
				self.ui.entr_svto.set_text(video.properties.outdir)		
				self.ui.entr_subtitle.set_sensitive(True if video.subfilename else False)				
				self.ui.bttn_properties.set_sensitive(self.ui.entr_subtitle.get_sensitive())
				self.ui.entr_subtitle.set_text(video.subfilename)

				if video.aud_intern:				
					self.addCombobox(self.ui.cmbobox_sound,video.aud_intern)
					self.ui.cmbobox_sound.set_active(video.properties.aud)

				if video.sub_intern:
					self.addCombobox(self.ui.cmbobox_subtitle,video.sub_intern)
					self.ui.cmbobox_subtitle.set_active(video.properties.sub)

				# status process
				if video.status != 2 :			
					self.ui.toolbutton_startpause.set_stock_id("gtk-media-play")
					self.ui.toolbutton_remove.set_sensitive(True)
					self.ui.toolbutton_stop.set_sensitive(False)
				elif video.status == 2:
					self.ui.toolbutton_startpause.set_stock_id("gtk-media-pause")		
					self.ui.toolbutton_stop.set_sensitive(True)
					self.all_sensitive_False()

				self.changed = True
				
			else:
				val = '%s %s %s %s %s %s %s %s %s %s %s' %('','','','','','','','',0,0,0,0)
				self.set_panel_options([ i for i in val.split(' ')])		
				self.ui.toolbutton_startpause.set_sensitive(False)
				self.ui.toolbutton_remove.set_sensitive(False)
				self.all_sensitive_False()
				
	def all_sensitive_False(self):
		self.ui.spinbutton_vbitrate.set_sensitive(False)
		self.ui.spinbutton_abitrate.set_sensitive(False)
		self.ui.entr_subtitle.set_sensitive(False)
		self.ui.spinbutton_width.set_sensitive(False)
		self.ui.spinbutton_heigth.set_sensitive(False)
		self.ui.scale1.set_sensitive(False)	
		self.ui.bttn_loadsubtitle.set_sensitive(False)
		self.ui.bttn_properties.set_sensitive(False)
		self.ui.bttn_remove.set_sensitive(False)
		self.ui.cmbobox_sound.set_sensitive(False)
		self.ui.cmbobox_subtitle.set_sensitive(False)

	def get_convert_options(self,option,params,separator):
	        return option.split(params)[1].split(separator)[0]

	def get_parms_of_convert(self,video):
		video.param = main._xml.get_xml_tag([main.ui.cmbobox_variant.get_model()[video.variant][0],'params'])
		video.extension = main._xml.get_xml_tag([main.ui.cmbobox_variant.get_model()[video.variant][0],'extension'])
		video.separator = main._xml.get_xml_tag(['attribute',main.ui.cmbobox_convert_to.get_model()[video.category][0]])

	def comboRender(self,combo):
		render = Gtk.CellRendererText()
		combo.pack_start(render, True)
		combo.add_attribute(render, 'text', 0)

	def addCombobox(self,combo,data = ['']):
		listStore = Gtk.ListStore(str)
		for i in data:
			listStore.append([i])
		combo.set_model(listStore)

	def get_selected_indexs(self):
		indexs = []
		for i in range(len(main.videos)):
			if self.ui.treeview.get_selection().iter_is_selected(main.videos[i].iter):
				indexs.append(i)
		return indexs

	def addtreeview(self,direction,profile):
		self.ui.treeview.get_model().append([get_name(direction),profile,main.status[0],0,'-','-','-',direction])

if __name__ == '__main__': 
	main = Main()
	main.show()