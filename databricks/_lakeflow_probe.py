print("Lakeflow probe running")
df = spark.sql("SELECT 1 AS ok")
df.show()
