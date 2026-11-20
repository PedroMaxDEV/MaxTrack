"""Run explicitly on Windows with Tcl/Tk; does not open webcam or global hotkeys."""
import json
from pathlib import Path
import tempfile
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import maxtrack

with tempfile.TemporaryDirectory() as directory:
    maxtrack.CONFIG=Path(directory)/'config.json'
    maxtrack.BASE=Path(directory)
    with patch.object(maxtrack.App,'restart'), patch.object(maxtrack.keyboard,'GlobalHotKeys'):
        app=maxtrack.App()
        app.root.update_idletasks()
        def verify_layout(widget):
            for child in widget.winfo_children():
                if child.winfo_ismapped():
                    right=child.winfo_rootx()+child.winfo_width()
                    bottom=child.winfo_rooty()+child.winfo_height()
                    assert right<=app.root.winfo_rootx()+app.root.winfo_width()+2, str(child)
                    assert bottom<=app.root.winfo_rooty()+app.root.winfo_height()+2, str(child)
                    verify_layout(child)
        verify_layout(app.root)
        app.root.withdraw()
        try:
            app.vars['sensitivity_x'].set(2.2)
            app.sync()
            app.profile_name.set('ATS');app.switch_profile()
            app.vars['sensitivity_x'].set(3.3)
            app.sync();app.persist()
            app.profile_name.set('ETS2');app.switch_profile()
            assert app.settings['sensitivity_x']==2.2
            app.profile_name.set('ATS');app.switch_profile()
            assert app.settings['sensitivity_x']==3.3
            app.root.after(850,app.root.quit)
            app.root.mainloop()
            saved=json.loads(maxtrack.CONFIG.read_text())
            assert saved['profiles']['ETS2']['sensitivity_x']==2.2
            assert saved['profiles']['ATS']['sensitivity_x']==3.3
            print('PASS: Tk widgets, profile switching, autosave, close; camera/hotkeys mocked')
        finally:app.close()
