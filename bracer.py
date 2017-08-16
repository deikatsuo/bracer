import gi
import os
import re
import tempfile

gi.require_version('Gtk', '3.0')
gi.require_version('GtkSource', '3.0')
gi.require_version('GIRepository', '2.0')
gi.require_version('Ide', '1.0')

from gi.repository import GIRepository
from gi.repository import Gio
from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import GtkSource
from gi.repository import Ide
from gi.repository import Dazzle

class Bracer():
    version = '1.0'
    racer = None
    dock_text_widget = None
    dock_widget = None

class Racer:
    def __init__(self):
        self.RACER_PATH = None
        
        # This Regex copied from https://github.com/qzed/autocomplete-racer
        self.regex = '^MATCH\s+([^;]+);([^;]+);(\d+);(\d+);((?:[^;]|\\;)+);([^;]+);((?:[^;]|\\;)+)?;\"([\S\s]+)?\"'

    def get_racer_path(self):
        if self.RACER_PATH is not None:
            return self.RACER_PATH

        default_value = ""
        possible_racer_paths = ("/usr/bin/racer", "/usr/local/bin/racer", os.path.expanduser("~/.cargo/bin/racer"))
        for path in possible_racer_paths:
            if os.path.exists(path):
                default_value = path

        self.RACER_PATH = default_value
        return self.RACER_PATH
    
    def init_racer(self, context, subcommand):
        _, iter = context.get_iter()
        current_dir = os.path.dirname(iter.get_buffer()
                        .get_file()
                        .get_path())
        
        temp_file = tempfile.NamedTemporaryFile(dir=current_dir)
        
        buffer = iter.get_buffer()
        begin, end = buffer.get_bounds()
        doc_text = buffer.get_text(begin, end, True)
        temp_file.write(doc_text.encode('utf-8'))
        temp_file.seek(0)
        
        line = iter.get_line() + 1
        column = iter.get_line_offset()

        result = None
        try:
            launcher = Ide.SubprocessLauncher.new(Gio.SubprocessFlags.STDOUT_PIPE)
            launcher.push_argv(self.get_racer_path())
            launcher.push_argv(subcommand)
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

    def get_matches(self, context):
        proc_result = self.init_racer(context, "complete-with-snippet")
        if proc_result == "" or proc_result is None:
            return []

        completion = []
        
        for line in proc_result.split('\n'):
            if line.startswith("MATCH "):
                line_items = re.split(self.regex, line)

                _text = line_items[1]
                _snippet = line_items[2]
                #_pos = line_items[3] line_item[4]
                _path = line_items[5]
                _type = line_items[6]
                _cxt = line_items[7]
                _doc = line_items[8]
                
                _doc = _doc.replace('\\;', ';')
                _doc = _doc.replace('\\n', '\n')
                _doc = _doc.replace('\\"', '"')
                _doc = _doc.replace('\\\\', '\\')
                 
                completion.append((_text,_snippet,_path,_type,_cxt,_doc))
                
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
        proposals = []

        for _text, _snippet, _path, _type, _cxt, _doc in Bracer.racer.get_matches(context):
            proposal = CompletionProposal(self, context, _text, _doc, _type)
            proposals.append(proposal)
        
        context.add_proposals(self, proposals, True)
            
    def do_match(self, context):
        _, iter = context.get_iter()
        iter.backward_char()
        ch = iter.get_char()
        if not (ch in (':', '.', '&') or ch.isalnum()):
            return False
        buffer = iter.get_buffer()
        if Ide.CompletionProvider.context_in_comment_or_string(context):
            return False
        return True
        
    def do_activate_proposal(self, provider, proposal):
        return False, None       
            
class CompletionProposal(GObject.Object, GtkSource.CompletionProposal):
    def __init__(self, provider, context, completion, info, icon_type, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.provider = provider
        self.context = context
        self.completion = completion
        self.complete = completion
        self.info = info
        self.icon_type = icon_type

    def do_get_label(self):
        return self.completion

    def do_get_markup(self):
        return self.completion

    def do_get_text(self):
        return self.complete
        
    def do_get_info(self):
        textbuffer = Bracer.dock_text_widget.get_buffer()
        textbuffer.set_text(self.info)
        return None

    def do_get_gicon(self):
        icon_names = {  "Module":       "lang-class-symbolic",
                        "Struct":       "lang-class-symbolic",
                        "StructField":  "lang-class-symbolic",
                        "Trait":        "lang-namespace-symbolic",
                        "Function":     "lang-function-symbolic",
                        "Let":          "lang-variable-symbolic",
                        "Enum":         "lang-namespace-symbolic",
                        "Crate":        "lang-class-symbolic"  }
            
        return Gio.ThemedIcon.new(icon_names[self.icon_type])

    def do_hash(self):
        return hash(self.completion)

    def do_equal(self, other):
        return False

    def do_changed(self):
        pass
        
class BracerWorkbenchAddin(GObject.Object, Ide.WorkbenchAddin):
    def do_load(self, workbench):
        print('Builder Workbench Addin: Load Bracer plugin workbench')

        editor = workbench.get_perspective_by_name('editor')
        dock_pane = Ide.EditorPerspective.get_bottom_edge(editor)
        
        dock_text_widget = Gtk.TextView(visible=True, expand=True)
        
        scrolled = Gtk.ScrolledWindow(visible=True)
        scrolled.add(dock_text_widget)
        
        dock_widget = Dazzle.DockWidget(title='Rust Documentation', visible=True, expand=True)
        dock_widget.add(scrolled)
        
        Ide.LayoutPane.add(dock_pane, dock_widget)

        Bracer.dock_text_widget = dock_text_widget
        Bracer.dock_widget = dock_widget

    def do_unload(self, workbench):
        print('Builder Workbench Addin: Unload Bracer plugin workbench')

class BracerApplicationAddin(GObject.Object, Ide.ApplicationAddin):        
    def do_load(self, application):
        print('Builder Application Addin: Load Bracer plugin')
        
        # Set racer
        Bracer.racer = Racer()
        
    def do_unload(self, application):
        print('Builder Application Addin: Unload Bracer plugin')
        
class BracerPreferencesAddin(GObject.Object, Ide.PreferencesAddin):
    ids = []
    def do_load(self, prefs):
        print('Builder Preferences Addin: Load Bracer plugin preferences')
        self.prefs = prefs
        
        # Create a new page for bracer
        self.prefs.add_page('bracer', _('Bracer Preferences'), 100)
        
        # Show Bracer & Racer versions
        self.show_version()
        
    def do_unload(self, prefs):
        print('Builder Preferences Addin: Unload Bracer plugin preferences')
        if self.ids:
            for id in self.ids:
                prefs.remove_id(id)
                
    def show_version(self):
        self.prefs.add_list_group('bracer', 'version', _('Versions'), Gtk.SelectionMode.NONE, 100)
        
        # Bracer
        bracerv = Bracer.version
        bracer = self.create_version_view('Bracer', bracerv)
        
        # Racer
        racerv = Bracer.racer.version()
        racer = self.create_version_view('Racer', racerv)
        
        bracer_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, expand=True, visible=True)
        bracer_box.pack_start(bracer, True, True, 0)
        racer_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, expand=True, visible=True)
        racer_box.pack_start(racer, True, True, 0)
        
        self.ids.append(self.prefs.add_custom('bracer', 'version', bracer_box, None, 1000))
        self.ids.append(self.prefs.add_custom('bracer', 'version', racer_box, None, 1000))
        
    def create_version_view(self, label, version):
        custom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12, expand=True, visible=True)
        
        title = Gtk.Label(halign='start', expand=True, visible=True, label=label)
        subtitle = Gtk.Label(halign='start', expand=True, visible=True)
        subtitle.get_style_context().add_class('dim-label')
        subtitle.set_markup(version)
        
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, expand=True, visible=True)
        vbox.pack_start(title, True, True, 0)
        vbox.pack_start(subtitle, True, True, 0)
        
        custom.pack_start(vbox, True, True, 0)
        
        pack = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, expand=True, visible=True)
        pack.pack_start(custom, True, True, 0)
        
        return pack

