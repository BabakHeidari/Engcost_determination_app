# import sqlite3

# # class DB_mngmt:
# #     def __init__(self, db_name:str):
# #         self.db_name = db_name
# #         self.conn = sqlite3.connect(self.db_name)
# #         self.cursor = self.conn.cursor()

# #     def commit(self):
# #         self.conn.commit()
# #         self.conn.close()

# #     def create_table(self, table_name:str, columns:list, column_types:list, column_options:list):
# #         self.cursor.

# # a = DB_mngmt("saba.db")
# # a.commit()

# from os import path
# from pathlib import Path
# dbpath = Path(str(path.abspath(__file__))).parent.parent/"Data"/"Overall"
# conn = sqlite3.connect(f"{dbpath}/saba.db")
# cursor = conn.cursor()
# cursor.execute("""CREATE TABLE product (
#                 product_id      INTEGER PRIMARY KEY AUTOINCREMENT,
#                 product_name        ,
#                 factory     ,
#                 category
#                 subcategory
#                 );""")

# cursor.execute("""CREATE TABLE product_recipe (
#                 recipe_id      INTEGER PRIMARY KEY AUTOINCREMENT,
#                 product_id      ,
#                         ,
#                 factory     ,
#                 category
#                 subcategory
#                 );""")

