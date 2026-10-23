Copy these two files here (from RIDtoDPT\ui\sounds):
  copy_successfully.wav
  copy_failed.wav
Without them KeyForMe uses standard Windows beeps.
When building the one-file EXE, bundle this folder with PyInstaller:
  --add-data "app\rid_export\sounds;app\rid_export\sounds"
