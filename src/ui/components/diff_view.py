"""
NervaOS Diff View Widget - File change visualization

A widget for displaying file diffs with:
- Side-by-side or unified view
- Syntax highlighting for changes
- Accept/Reject buttons
- Line-by-line navigation
"""

from typing import Optional, Callable

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Pango, GLib


class DiffView(Gtk.Box):
    """
    A diff viewer widget for showing file changes.
    
    Args:
        diff_text: The unified diff text
        on_accept: Callback when changes are accepted
        on_reject: Callback when changes are rejected
    """
    
    def __init__(
        self,
        diff_text: str,
        on_accept: Optional[Callable] = None,
        on_reject: Optional[Callable] = None
    ):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        
        self._diff_text = diff_text
        self._on_accept = on_accept
        self._on_reject = on_reject
        
        self.add_css_class('diff-view')
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Build the diff view UI"""
        # Header
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header.set_margin_start(12)
        header.set_margin_end(12)
        header.set_margin_top(8)
        header.set_margin_bottom(8)
        
        title = Gtk.Label(label="Proposed Changes")
        title.add_css_class('heading')
        title.set_hexpand(True)
        title.set_xalign(0)
        header.append(title)
        
        # View toggle
        view_toggle = Gtk.ToggleButton(label="Unified")
        view_toggle.set_active(True)
        header.append(view_toggle)
        
        self.append(header)
        
        # Diff content
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        
        self._content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._content_box.add_css_class('diff-content')
        
        self._render_unified_diff()
        
        scroll.set_child(self._content_box)
        self.append(scroll)
        
        # Action buttons
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        actions.set_halign(Gtk.Align.END)
        actions.set_margin_start(12)
        actions.set_margin_end(12)
        actions.set_margin_top(12)
        actions.set_margin_bottom(12)
        
        reject_btn = Gtk.Button(label="Reject")
        reject_btn.add_css_class('destructive-action')
        reject_btn.connect('clicked', self._on_reject_clicked)
        actions.append(reject_btn)
        
        accept_btn = Gtk.Button(label="Apply Changes")
        accept_btn.add_css_class('suggested-action')
        accept_btn.connect('clicked', self._on_accept_clicked)
        actions.append(accept_btn)
        
        self.append(actions)
    
    def _render_unified_diff(self):
        """Render the diff in unified format"""
        lines = self._diff_text.split('\n')
        
        for line in lines:
            row = DiffLine(line)
            self._content_box.append(row)
    
    def _on_accept_clicked(self, button):
        """Handle accept button click"""
        if self._on_accept:
            self._on_accept()
    
    def _on_reject_clicked(self, button):
        """Handle reject button click"""
        if self._on_reject:
            self._on_reject()


class DiffLine(Gtk.Box):
    """A single line in a diff view"""
    
    def __init__(self, line: str):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        
        self._line = line
        
        # Determine line type
        if line.startswith('+++') or line.startswith('---'):
            self.add_css_class('diff-header')
        elif line.startswith('+'):
            self.add_css_class('diff-added')
        elif line.startswith('-'):
            self.add_css_class('diff-removed')
        elif line.startswith('@@'):
            self.add_css_class('diff-hunk')
        else:
            self.add_css_class('diff-context')
        
        # Line content
        label = Gtk.Label(label=line)
        label.set_xalign(0)
        label.set_selectable(True)
        label.add_css_class('monospace')
        label.set_margin_start(8)
        label.set_margin_top(2)
        label.set_margin_bottom(2)
        
        self.append(label)


class InlineDiff(Gtk.Box):
    """
    Inline diff widget showing changes within a text.
    Highlights added and removed portions.
    """
    
    def __init__(self, original: str, modified: str):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        
        self.add_css_class('inline-diff')
        
        # Original version
        orig_frame = Gtk.Frame()
        orig_frame.set_label("Original")
        
        orig_label = Gtk.Label(label=original)
        orig_label.set_wrap(True)
        orig_label.set_xalign(0)
        orig_label.set_margin_start(8)
        orig_label.set_margin_end(8)
        orig_label.set_margin_top(8)
        orig_label.set_margin_bottom(8)
        orig_label.add_css_class('diff-removed')
        orig_frame.set_child(orig_label)
        
        self.append(orig_frame)
        
        # Arrow indicator
        arrow = Gtk.Image.new_from_icon_name('go-down-symbolic')
        arrow.set_pixel_size(16)
        arrow.add_css_class('dim-label')
        arrow.set_halign(Gtk.Align.CENTER)
        self.append(arrow)
        
        # Modified version
        mod_frame = Gtk.Frame()
        mod_frame.set_label("Modified")
        
        mod_label = Gtk.Label(label=modified)
        mod_label.set_wrap(True)
        mod_label.set_xalign(0)
        mod_label.set_margin_start(8)
        mod_label.set_margin_end(8)
        mod_label.set_margin_top(8)
        mod_label.set_margin_bottom(8)
        mod_label.add_css_class('diff-added')
        mod_frame.set_child(mod_label)
        
        self.append(mod_frame)


class FileOperationResult(Gtk.Box):
    """
    Widget showing the result of a file operation with undo option.
    """
    
    def __init__(
        self,
        file_path: str,
        operation: str,
        success: bool,
        on_undo: Optional[Callable] = None
    ):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        
        self.add_css_class('file-operation-result')
        self.set_margin_start(12)
        self.set_margin_end(12)
        self.set_margin_top(8)
        self.set_margin_bottom(8)
        
        # Status icon
        if success:
            icon = Gtk.Image.new_from_icon_name('emblem-ok-symbolic')
            icon.add_css_class('success')
        else:
            icon = Gtk.Image.new_from_icon_name('dialog-error-symbolic')
            icon.add_css_class('error')
        
        self.append(icon)
        
        # Info
        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        info_box.set_hexpand(True)
        
        path_label = Gtk.Label(label=file_path)
        path_label.set_xalign(0)
        path_label.add_css_class('heading')
        path_label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        info_box.append(path_label)
        
        operation_label = Gtk.Label(label=operation)
        operation_label.set_xalign(0)
        operation_label.add_css_class('dim-label')
        info_box.append(operation_label)
        
        self.append(info_box)
        
        # Undo button
        if success and on_undo:
            undo_btn = Gtk.Button(label="Undo")
            undo_btn.set_valign(Gtk.Align.CENTER)
            undo_btn.connect('clicked', lambda b: on_undo())
            self.append(undo_btn)
