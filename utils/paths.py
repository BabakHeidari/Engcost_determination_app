import pandas as pd
from pathlib import Path
from os.path import abspath

parent_path = Path(str(abspath(__file__))).parent.parent/"Data"
product_path = str(parent_path)+r"\Overall\ProductsLater"
material_path = str(parent_path)+r"\Overall\material_costs"
factories_path = str(parent_path)+r"\Overall\factories"
sample_data = str(parent_path)+r"\Overall\sample_data"
sample_product = str(parent_path)+r"\Overall\sample_product"

