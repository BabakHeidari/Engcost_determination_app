from pathlib import Path
from os.path import abspath

parent_path = Path(str(abspath(__file__))).parent.parent/"Data"
product_path = str(parent_path / "Overall" / "ProductsLater")
material_path = str(parent_path / "Overall" / "material_costs")
factories_path = str(parent_path / "Overall" / "factories")
sample_data = str(parent_path / "Overall" / "sample_data")
sample_product = str(parent_path / "Overall" / "sample_product")
