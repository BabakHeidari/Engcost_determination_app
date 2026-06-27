import pandas as pd
import json
from pathlib import Path
from os.path import abspath

def xlsx_to_json_convertor(excel_path: str, if_sheet=False, sheet_name=None, if_subfield=False):

    if if_sheet == True:
        df = pd.read_excel(excel_path, sheet_name)
    else:
        df = pd.read_excel(excel_path)

    cols = list(df.columns)
    data = {col: df[col].tolist() for col in cols}

    payload = {
        "_order": cols,   # <‑‑ explicit order
        "data": data      # <‑‑ actual data
    }

    name = excel_path.split("\\")[-1]
    
    if if_subfield==False:
        json_file_path = (
            Path(abspath(excel_path)).parent / f"{name.replace('.xlsx', '')}.json"
        )
    elif if_subfield==True:
        json_file_path = (
            Path(abspath(excel_path)).parent / f"{name.replace('.xlsx', f'_{sheet_name}')}.json"
        )

    with open(json_file_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=4)

def to_json(file_path:str, data):
    with open(f"{file_path}", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


if __name__ == "__main__":
    excel_path = input("Enter the file path: ")
    xlsx_to_json_convertor(excel_path)
