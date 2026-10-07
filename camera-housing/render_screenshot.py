import os
import FreeCADGui as Gui

OUT_DIR = os.getcwd()
FCSTD_PATH = os.path.join(OUT_DIR, "camera_housing.FCStd")

Gui.showMainWindow()
doc = App.openDocument(FCSTD_PATH)
Gui.ActiveDocument = Gui.getDocument(doc.Name)

for obj in doc.Objects:
    if hasattr(obj, "Shape"):
        vobj = Gui.ActiveDocument.getObject(obj.Name)
        vobj.Visibility = True

Gui.ActiveDocument.ActiveView.viewIsometric()
Gui.SendMsgToActiveView("ViewFit")

img_path = os.path.join(OUT_DIR, "assembly_preview.png")
Gui.ActiveDocument.ActiveView.saveImage(img_path, 1200, 900, "White")
print("Saved image:", img_path)
