import pandas as pd
from pathlib import Path
from paths import parent_path, product_path
import os

df = pd.DataFrame(columns=["Product_Name", 
                           "Factory" ,"Category", "Subcategory"])#, "Product_ID", 

results = []

for root, dirs, files in os.walk(parent_path/"Factories"):
    for file in files:
        if file.endswith(".json"):
            results.append([root, file.replace(".json", "")])

for i, r in enumerate(results):
    df.loc[i, "Product_Name"] = r[1]
    df.loc[i, "Factory"] = r[0].split("\\")[-3]
    df.loc[i, "Category"] = r[0].split("\\")[-2]
    df.loc[i, "Subcategory"] = r[0].split("\\")[-1]

# print(df.columns)
df.to_excel(product_path+".xlsx")
df.to_json(product_path+".json")