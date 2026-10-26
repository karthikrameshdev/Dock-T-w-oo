# Runtime import is webrtcvad; the maintained distribution is webrtcvad-wheels.
from PyInstaller.utils.hooks import copy_metadata
datas=copy_metadata('webrtcvad-wheels')
hiddenimports=['_webrtcvad']
