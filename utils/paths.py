from utils.runtime_paths import RuntimePaths

parent_path = RuntimePaths.from_environment().data
product_path = str(parent_path / "Overall" / "ProductsLater")
material_path = str(parent_path / "Overall" / "material_costs")
factories_path = str(parent_path / "Overall" / "factories")
sample_data = str(parent_path / "Overall" / "sample_data")
sample_product = str(parent_path / "Overall" / "sample_product")
