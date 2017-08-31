import gi
import os
import re
import tempfile

gi.require_version('Gtk', '3.0')
gi.require_version('GtkSource', '3.0')
gi.require_version('GIRepository', '2.0')
gi.require_version('Ide', '1.0')
gi.require_version('WebKit2', '4.0')

from gi.repository import GIRepository
from gi.repository import Gio
from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import GtkSource
from gi.repository import Peas
from gi.repository import Ide
from gi.repository import Dazzle
from gi.repository import WebKit2

_IconNames = {  "Module":       Gio.ThemedIcon.new('lang-define-symbolic'),
                "Struct":       Gio.ThemedIcon.new('lang-struct-symbolic'),
                "StructField":  Gio.ThemedIcon.new('lang-enum-value-symbolic'),
                "Trait":        Gio.ThemedIcon.new('lang-class-symbolic'),
                "Function":     Gio.ThemedIcon.new('lang-function-symbolic'),
                "Let":          Gio.ThemedIcon.new('lang-variable-symbolic'),
                "Type":         Gio.ThemedIcon.new('lang-typedef-symbolic'),
                "Enum":         Gio.ThemedIcon.new('lang-enum-symbolic'),
                "Union":        Gio.ThemedIcon.new('lang-union-symbolic'),
                "Crate":        Gio.ThemedIcon.new('lang-include-symbolic')  }
                
class Bracer():
    _VERSION = '1.70'
    _TMP_DIR = None
    _MARKDOWN_CSS = None
    _MARKED_JS = None
    _MARKDOWN_VIEW_JS = None
    
    enabled = False
    racer = None
    setting = None
    dock_text_widget = None
    dock_widget = None
    dock_webview = None
    
    def get_home():
        peas = Peas.Engine.get_default()
        plugin = peas.get_plugin_info('bracer')
        home = plugin.get_data_dir()
        return home
        
    def get_tmp_dir():
        if Bracer._TMP_DIR is not None:
            if os.path.exists(Bracer._TMP_DIR):
                return Bracer._TMP_DIR
            
        settings = Gio.Settings.new('org.gnome.builder')
        path = os.path.realpath(settings.get_string('projects-directory'))
        tmp = os.path.join(path, '.bracer')

        if not os.path.exists(tmp):
            try:
                os.mkdir(tmp)
            except OSError:
                print('Fail to create the temporary directory for bracer')
                pass
                
        Bracer._TMP_DIR = tmp  
        return Bracer._TMP_DIR
    
    def get_data(name):
        path = os.path.join(Bracer.get_home(), name)
        return open(path, 'r').read()
        
    def get_markdown(text):
        text = text.replace("\"", "\\\"").replace("\n", "\\n")

        return ('<html>'
                '<head>'
                '<style>'+Bracer._MARKDOWN_CSS+'</style>'
                '<script>var str="'+text+'";</script>'
                '<script>'+Bracer._MARKED_JS+'</script>'
                '<script>'+Bracer._MARKDOWN_VIEW_JS+'</script>'
                '</head>'
                '<body onload="preview()">'
                '<div class="markdown-body" id="preview">'
                '</div>'
                '</body>'
                '</html>')

class Racer:
    def __init__(self):
        self.racer_path = None
        self.tmp_path = None
        # This Regex copied from https://github.com/qzed/autocomplete-racer
        self.regex = r'^MATCH\s+([^;]+);([^;]+);(\d+);(\d+);((?:[^;]|\\;)+);([^;]+);((?:[^;]|\\;)+)?;\"([\S\s]+)?\"'

    def get_racer_path(self):
        if self.racer_path is not None:
            return self.racer_path

        possible_racer_paths = ("/usr/bin/racer",
                                "/usr/local/bin/racer",
                                os.path.expanduser("~/.cargo/bin/racer"))
                                
        for path in possible_racer_paths:
            if os.path.exists(path):
                self.racer_path = path

        return self.racer_path
    
    def search(self, iterc, mode):
        project_dir = Bracer.get_tmp_dir()
        temp_file = tempfile.NamedTemporaryFile(dir=project_dir)
        
        sbuffer = iterc.get_buffer()
        begin = iterc.copy()
        begin.set_line_offset(0)
        begin, end = sbuffer.get_bounds()
        doc_text = sbuffer.get_text(begin, end, True)
        temp_file.write(doc_text.encode('utf-8'))
        temp_file.seek(0)
        
        line = iterc.get_line() + 1
        column = iterc.get_line_offset()

        result = None
        try:
            launcher = Ide.SubprocessLauncher.new(Gio.SubprocessFlags.STDOUT_PIPE)
            launcher.push_argv(self.get_racer_path())
            launcher.push_argv(mode)
            launcher.push_argv(str(line))
            launcher.push_argv(str(column))
            launcher.push_argv(temp_file.name)
            launcher.set_run_on_host(True)
            sub_process = launcher.spawn()
            success, stdout, stderr = sub_process.communicate_utf8(None, None)
            
            if stdout:
                result = stdout
                      
        except GLib.Error as e:
            pass
        
        temp_file.close()
        return result

    def get_matches(self, iterc):
        proc_result = self.search(iterc, "complete-with-snippet")
        if proc_result == "" or proc_result is None:
            return []

        completion = []
        
        for line in proc_result.split('\n'):
            if line.startswith("MATCH "):
                line_items = re.split(self.regex, line)

                _text = line_items[1]
                #_snippet = line_items[2]
                #_pos = line_items[3] line_item[4]
                #_path = line_items[5]
                _type = line_items[6]
                _cxt = line_items[7]
                
                _doc = None
                if line_items[8]:
                    _doc = line_items[8]
                    _doc = _doc.replace('\\;', ';')
                    _doc = _doc.replace('\\n', '\n')
                    _doc = _doc.replace('\\"', '"')
                    _doc = _doc.replace('\\\\', '\\')
                 
                completion.append((_text,_type,_doc,_cxt))
                
        return completion
    
    def version(self):
        result = None
        try:
            launcher = Ide.SubprocessLauncher.new(Gio.SubprocessFlags.STDOUT_PIPE)
            launcher.push_argv(self.get_racer_path())
            launcher.push_argv('-V') 
            launcher.set_run_on_host(True)
            sub_process = launcher.spawn()
            success, stdout, stderr = sub_process.communicate_utf8(None, None) 
        
            if stdout:
                result = stdout.replace('racer','').strip()
        except GLib.Error as e:
            pass
        return result

class BracerCompletionProvider(Ide.Object, GtkSource.CompletionProvider, Ide.CompletionProvider):   
    def do_get_name(self):
        return _("Bracer Rust Code Completion")

    def do_populate(self, context):
        _, iter = context.get_iter()
        iterc = iter.copy()
        if Bracer.enabled:
            proposals = []
            for _text, _type, _doc, _cxt in Bracer.racer.get_matches(iterc):
                if _text is not None:
                    proposal = CompletionProposal(self, context, _text, _type, _doc, _cxt)
                    proposals.append(proposal)
            
            context.add_proposals(self, proposals, True)
            
    def do_match(self, context):
        _, iter = context.get_iter()
        copy = iter.copy()
        copy.set_line_offset(0)
        ch = copy.get_char()
        if not (ch in (':', '.', '&') or ch.isalnum()):
            return False
        if Ide.CompletionProvider.context_in_comment_or_string(context):
            return False
        return True
        
    def do_activate_proposal(self, provider, proposal):
        return False, None
    
    def do_activate_proposal(self, provider, proposal):
        return False, None
    
    def do_get_interactive_delay(self):
        return -1
    
    def do_get_priority(self):
        return 201  
            
class CompletionProposal(GObject.Object, GtkSource.CompletionProposal):
    def __init__(self, provider, context, _completion, _type, _doc, _cxt, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.provider = provider
        self.context = context
        self.completion = _completion
        self.type = _type
        self.info = _doc
        self.cxt = _cxt

    def do_get_label(self):
        return completion

    def do_get_markup(self):
        typ = ""
        cxt = ""
        if self.type:
            typ = self.type
        if self.cxt:
            cxt = self.cxt
            cxt = cxt.replace("&", "&amp;")
            cxt = cxt.replace("<", "&lt;")
            cxt = cxt.replace(">", "&gt;")
            cxt = cxt.replace('\\;', '')
            cxt = " : <sup>"+cxt+"</sup>"
            
        compl = self.completion
        return "<sup>"+typ+"</sup> <big>"+compl+"</big>"+cxt

    def do_get_text(self):
        return self.completion
        
    def do_get_info(self):
        info = 'No documentation'
        if self.info is not None:
            info = self.info
        if Bracer.settings.get_boolean('prefs-documentation'):
            if Bracer.settings.get_boolean('prefs-markdown'):
                Bracer.dock_webview.load_html(Bracer.get_markdown(info), None)
            else:
                text = Bracer.dock_text_widget.get_buffer()
                text.set_text(info)
                
        return None

    def do_get_gicon(self):
        if self.type in _IconNames:
            return _IconNames[self.type]
        return None

    def do_changed(self):
        pass
    
class BracerWorkbenchAddin(GObject.Object, Ide.WorkbenchAddin):
    def do_load(self, workbench):
        print('Builder Workbench Addin: Load Bracer plugin workbench')

        editor = workbench.get_perspective_by_name('editor')
        dock_pane = Ide.EditorPerspective.get_utilities(editor)

        dock_widget = Dazzle.DockWidget(title=_('Rust Docs'),
                                        icon_name='accessories-dictionary-symbolic',
                                        visible=True,
                                        expand=False)

        Bracer.dock_widget = dock_widget
        
        if Bracer.settings.get_boolean('prefs-documentation'):
            if Bracer.settings.get_boolean('prefs-markdown'):
                Bracer._MARKDOWN_CSS = Bracer.get_data('resources/markdown.css')
                Bracer._MARKED_JS = Bracer.get_data('resources/marked.js')
                Bracer._MARKDOWN_VIEW_JS = Bracer.get_data('resources/markdown-view.js')

                webview = WebKit2.WebView(visible=True, expand=True)
                Bracer.dock_webview = webview
                settings = webview.get_settings()
                settings.enable_html5_local_storage = False
                Bracer.dock_widget.add(Bracer.dock_webview)
                Ide.LayoutPane.add(dock_pane, Bracer.dock_widget)
            else:
                dock_text_widget = Gtk.TextView(visible=True, expand=True)
                Bracer.dock_text_widget = dock_text_widget
                scrolled = Gtk.ScrolledWindow(visible=True)
                scrolled.add(Bracer.dock_text_widget)
                Bracer.dock_widget.add(scrolled)
                Ide.LayoutPane.add(dock_pane, Bracer.dock_widget)

    def do_unload(self, workbench):
        print('Builder Workbench Addin: Unload Bracer plugin workbench')
        Bracer.dock_widget.destroy()
        Bracer.dock_widget = None
        Bracer.dock_text_widget = None
        Bracer.dock_webview = None 
        Bracer._MARKDOWN_CSS = None
        Bracer._MARKED_JS = None
        Bracer._MARKDOWN_VIEW_JS = None       

class BracerApplicationAddin(GObject.Object, Ide.ApplicationAddin):        
    def do_load(self, application):
        print('Builder Application Addin: Load Bracer plugin')
        Bracer.enabled = True
        # Set racer
        Bracer.racer = Racer()
        
    def do_unload(self, application):
        print('Builder Application Addin: Unload Bracer plugin')
        Bracer.enabled = False
        Bracer.racer = None
            
class BracerPreferencesAddin(GObject.Object, Ide.PreferencesAddin):
    ids = []
    def do_load(self, prefs):
        print('Builder Preferences Addin: Load Bracer plugin preferences')
        self.prefs = prefs
        home = os.path.join(Bracer.get_home(), 'schema')
        settings = Gio.SettingsSchemaSource.get_default()
        settings = Gio.SettingsSchemaSource.new_from_directory(home, None, False)
        settings = settings.lookup('org.gnome.builder.plugins.bracer', True)
        settings = Gio.Settings.new_full(settings, None, None)
        Bracer.settings = settings

        # Create a new page for bracer
        self.prefs.add_page('bracer', _('Bracer Preferences'), 100)
        # Show Bracer & Racer versions
        self.show_version()
        # Show Bracer preferences
        self.show_preferences()
        
    def do_unload(self, prefs):
        print('Builder Preferences Addin: Unload Bracer plugin preferences')
        if self.ids:
            for id in self.ids:
                prefs.remove_id(id)
        self.prefs = None
        Bracer.settings = None
    
    def show_preferences(self):
        self.prefs.add_list_group('bracer',
                                  'preferences',
                                  _('Preferences'),
                                  Gtk.SelectionMode.NONE, 100)
                                          
        self.create_switch('bracer',
                           'preferences',
                           'Documentation',
                           'prefs-documentation',
                           'The documentation should be shown on the dock\n'
                           'inside Rust Documentation tab')
                           
        self.create_switch('bracer',
                           'preferences',
                           'Markdown',
                           'prefs-markdown',
                           'Show the documentation as Markdown')
                           
    def create_switch(self, p, g, l, b, d='Default'):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,
                      spacing=12,
                      expand=True,
                      visible=True)
                      
        title = Gtk.Label(halign='start',
                          expand=True,
                          visible=True,
                          label=l)
                          
        subtitle = Gtk.Label(halign='start', expand=True, visible=True)
        subtitle.get_style_context().add_class('dim-label')
        subtitle.set_markup('<small>'+str(d)+'</small>')
        
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                       expand=True,
                       visible=True)
                       
        vbox.pack_start(title, True, True, 0)
        vbox.pack_start(subtitle, True, True, 0)
        box.pack_start(vbox, True, True, 0)
        
        switch = Gtk.Switch(visible=True, expand=False)
        Bracer.settings.bind(b, switch, "active", Gio.SettingsBindFlags.DEFAULT)
        
        switch_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                       spacing=6,
                       expand=False,
                       visible=True)
                       
        switch_box.pack_start(switch, True, False, 0)
        pack = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,
                       spacing=6,
                       expand=True,
                       visible=True)
                       
        pack.pack_start(box, True, True, 0)
        pack.pack_end(switch_box, False, False, 0)
        ready = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                        spacing=6,
                        expand=True,
                        visible=True)
        
        ready.pack_start(pack, True, True, 0)
        self.ids.append(self.prefs.add_custom(p, g, ready, None, 1000))
    
    def show_version(self):
        self.prefs.add_list_group('bracer', 'version', _('Versions'), Gtk.SelectionMode.NONE, 100)
        
        # Bracer
        bracerv = Bracer._VERSION
        bracer = self.create_version_view('Bracer', bracerv)
        # Racer
        racerv = Bracer.racer.version()
        racer = self.create_version_view('Racer', racerv)
        racerv2 = Bracer.racer.version()
        
        bracer_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                             spacing=6, expand=True,
                             visible=True)
                             
        bracer_box.pack_start(bracer, True, True, 0)
        racer_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                            spacing=6,
                            expand=True,
                            visible=True)
                            
        racer_box.pack_start(racer, True, True, 0)
        
        self.ids.append(self.prefs.add_custom('bracer', 'version', bracer_box, None, 1000))
        self.ids.append(self.prefs.add_custom('bracer', 'version', racer_box, None, 1000))
        
    def create_version_view(self, label, version):
        custom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,
                         spacing=12,
                         expand=True,
                         visible=True)
        
        title = Gtk.Label(halign='start', expand=True, visible=True, label=label)
        subtitle = Gtk.Label(halign='start', expand=True, visible=True)
        subtitle.get_style_context().add_class('dim-label')
        subtitle.set_markup(version)
        
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, expand=True, visible=True)
        vbox.pack_start(title, True, True, 0)
        vbox.pack_start(subtitle, True, True, 0)
        
        custom.pack_start(vbox, True, True, 0)
        
        pack = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                       spacing=6,
                       expand=True,
                       visible=True)
                       
        pack.pack_start(custom, True, True, 0)
        
        return pack

