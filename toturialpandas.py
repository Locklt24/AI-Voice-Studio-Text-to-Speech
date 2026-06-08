import pandas as pd
import mysql.connector
data = {
    "Tên": ["An", "Bình", "Cường"],
    "Tuổi": [20, 21, 22],
    "Điểm": [8.5, 7.0, 9.0]
}

df = pd.DataFrame(data)

print(df)