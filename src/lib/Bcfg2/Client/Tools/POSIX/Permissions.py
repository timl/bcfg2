import os
import sys
from Bcfg2.Client.POSIX import POSIXTool

class POSIXPermissions(POSIXTool):
    __req__ = ['name', 'perms', 'owner', 'group']
    
