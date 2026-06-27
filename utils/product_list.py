import pandas as pd
# from pathlib import Path
# from os.path import abspath
from utils.product_sheet_updater import product_path

# parent_path = Path(str(abspath(__file__))).parent.parent/"Data"
# product_path = str(parent_path)+r"\Overall\ProductsLater.xlsx"

df = pd.read_excel(product_path)
CATEGORIES = df.loc[:, 'Category'].unique()
SUBCATEGORIES = df.loc[:, 'Subcategory'].unique()
FACTORIES = df.loc[:, 'Factory'].unique()
PRODUCT_NAMES = df.loc[:, 'Product_Name'].unique()
# print(list(FACTORIES))
# print(CATEGORIES, SUBCATEGORIES, FACTORIES, PRODUCT_NAMES)