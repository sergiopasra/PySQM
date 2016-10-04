# PySQM plotting program
# ____________________________
#
# Copyright (c) Miguel Nievas <miguelnievas[at]ucm[dot]es>
#
# This file is part of PySQM.
#
# PySQM is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# PySQM is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with PySQM.  If not, see <http://www.gnu.org/licenses/>.
# ____________________________


import os
import sys


class ConfigFile(object):
    def __init__(self, path="config.py"):
        # Guess the selected dir and config filename
        # Should accept:
        # - absolute path (inc. filename)
        # - relative path (inc. filename)
        # - absolute path (exc. filename)
        # - relative path (exc. filename)
        # - shortcouts like ~ . etc
        self.path = path

    def read_config_file(self, path):
        # Get the absolute path
        abspath = os.path.abspath(path)
        # Is a dir? Then add config.py (default filename)
        if os.path.isdir(abspath):
            abspath += "/config.py"
        # split directory and filename
        directory = os.path.dirname(abspath)
        filename = os.path.basename(abspath)

        old_syspath = sys.path
        sys.path.append(directory)
        # FIXME: this will not work in Python 3
        exec ("import %s as config" % filename.split(".")[0])
        self.config = config


# Create an object (by default empty) accessible from everywhere
# After read_config_file is called, GlobalConfig.config will be accessible
GlobalConfig = ConfigFile()
