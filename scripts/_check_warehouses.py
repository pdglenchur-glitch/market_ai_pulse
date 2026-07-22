import os
from databricks.sdk import WorkspaceClient

client = WorkspaceClient(host=os.environ["DATABRICKS_HOST"], token=os.environ["DATABRICKS_TOKEN"])
for wh in client.warehouses.list():
    print(wh.id, wh.name, wh.state, wh.odbc_params.hostname if wh.odbc_params else None, wh.odbc_params.path if wh.odbc_params else None)
