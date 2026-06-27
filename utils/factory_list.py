from pathlib import Path
from os.path import abspath
import os
datapath = Path(str(abspath(__file__))).parent.parent/"Data"/"Factories"
factories = [{"id":id+1, "name": f} for id, f in enumerate(os.listdir(datapath))]